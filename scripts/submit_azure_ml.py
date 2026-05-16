#!/usr/bin/env python3
"""Submit the Gemma 4 Mycelium LoRA fine-tune as an Azure ML job.

Why Azure ML instead of Kaggle: HF_TOKEN never leaves Crowe-controlled
infrastructure. The token reads from ~/.env.secrets at submit time and
passes through Azure ML's encrypted environment-variable channel into a
job that runs on a Crowe-owned compute target. The trained adapter
lands in the workspace's blob storage (same security boundary as the
foundry's model deployments).

Defaults target the `crowelm-mlws-eastus2` workspace on the
`Crowe Mycology LLC` subscription (4ea8ab04-...). Compute is an auto-
scaling cluster with min=0 (no idle cost), so the only spend is the
~3-hour training run itself.

Usage:
    python scripts/submit_azure_ml.py                # full submit
    python scripts/submit_azure_ml.py --gpu t4       # use cheap T4 (~$0.50/hr)
    python scripts/submit_azure_ml.py --gpu a100     # use A100 80GB (~$3.67/hr)
    python scripts/submit_azure_ml.py --status JOB   # poll a running job
    python scripts/submit_azure_ml.py --logs JOB     # stream logs
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from azure.ai.ml import MLClient, command, Input, Output
from azure.ai.ml.entities import AmlCompute, Environment
from azure.ai.ml.constants import AssetTypes
from azure.identity import DefaultAzureCredential


REPO_ROOT = Path(__file__).resolve().parents[1]
SUBSCRIPTION_ID = os.environ.get("AZURE_ML_SUBSCRIPTION_ID", "4ea8ab04-9d53-46cf-9d80-de7d625ba88a")
RESOURCE_GROUP = os.environ.get("AZURE_ML_RESOURCE_GROUP", "rg-crowelm-prod")
WORKSPACE = os.environ.get("AZURE_ML_WORKSPACE_NAME", "crowelm-mlws-eastus2")

GPU_PROFILES = {
    "t4":   {"size": "Standard_NC4as_T4_v3",       "cluster": "gemma-train-t4",   "max_nodes": 1},
    "a10":  {"size": "Standard_NV12ads_A10_v5",    "cluster": "gemma-train-a10",  "max_nodes": 1},
    "a100": {"size": "Standard_NC24ads_A100_v4",   "cluster": "gemma-train-a100", "max_nodes": 1},
    "h100": {"size": "Standard_NC40ads_H100_v5",   "cluster": "gemma-train-h100", "max_nodes": 1},
}

JOB_NAME_PREFIX = "gemma-4-mycelium-lora"


def _ml_client() -> MLClient:
    return MLClient(
        credential=DefaultAzureCredential(),
        subscription_id=SUBSCRIPTION_ID,
        resource_group_name=RESOURCE_GROUP,
        workspace_name=WORKSPACE,
    )


def _read_hf_token() -> str:
    """Source HF_TOKEN from ~/.env.secrets without echoing.

    The token is held in memory only for the duration of the submit call;
    it ships into the Azure ML job via the encrypted environment_variables
    channel and is never written to a local file or logged.
    """
    if "HF_TOKEN" in os.environ:
        return os.environ["HF_TOKEN"]
    env_path = Path.home() / ".env.secrets"
    if not env_path.exists():
        raise SystemExit(f"HF_TOKEN not found in env and {env_path} does not exist")
    for line in env_path.read_text().splitlines():
        m = re.match(r"^(?:export\s+)?HF_TOKEN=(.+)$", line.strip())
        if m:
            return m.group(1).strip().strip('"').strip("'")
    raise SystemExit(f"HF_TOKEN not found in {env_path}")


def _ensure_compute(client: MLClient, profile: dict) -> str:
    """Create or reuse an auto-scaling compute cluster.

    ``min_instances=0`` ensures the cluster scales to zero between runs —
    no idle billing. ``idle_time_before_scale_down=120`` (2 min) keeps the
    cluster warm just long enough to retry a failed job without provisioning
    overhead.
    """
    name = profile["cluster"]
    try:
        existing = client.compute.get(name)
        print(f"  reusing compute {name} ({existing.size}, max {existing.max_instances})")
        return name
    except Exception:
        pass
    print(f"  creating compute {name} (size={profile['size']}, min=0, max={profile['max_nodes']})")
    cluster = AmlCompute(
        name=name,
        size=profile["size"],
        min_instances=0,
        max_instances=profile["max_nodes"],
        idle_time_before_scale_down=120,
        tier="Dedicated",
    )
    client.compute.begin_create_or_update(cluster).result()
    print(f"  compute ready")
    return name


def _ensure_environment(client: MLClient) -> str:
    """Return a curated environment reference that has PyTorch + CUDA.

    Azure ML's curated 'AzureML-acpt-pytorch-2.2-cuda12.1' image gives us
    Python 3.10 + PyTorch 2.2 + CUDA 12.1. The training script's
    `_ensure_deps()` adds transformers-from-main + peft/trl/bitsandbytes
    on first run inside the container.
    """
    return "azureml://registries/azureml/environments/acft-hf-nlp-gpu/labels/latest"


def submit(gpu: str, epochs: int, hf_repo: str | None) -> str:
    """Submit a fresh training job. Returns the job name."""
    client = _ml_client()
    profile = GPU_PROFILES[gpu]

    cluster_name = _ensure_compute(client, profile)
    environment = _ensure_environment(client)

    hf_token = _read_hf_token()
    print(f"  HF_TOKEN sourced ({len(hf_token)} chars), passed via encrypted env-var channel")

    env_vars = {
        "HF_TOKEN": hf_token,
        "BASE_MODEL": os.environ.get("BASE_MODEL", "google/gemma-4-e4b"),
        "LOAD_4BIT": "true",
        "OUTPUT_DIR": "./outputs/lora-gemma-4-mycelium-e4b",
        "INSTRUCT_JSONL": "./data/instruct.jsonl",
        "NUM_EPOCHS": str(epochs),
        "PUSH_TO_HF": "true" if hf_repo else "false",
    }
    if hf_repo:
        env_vars["HF_REPO"] = hf_repo

    # The job mounts the local repo as code. The corpus is regenerated
    # inside the job from the committed source files via prepare_corpus.py
    # — keeps the upload tiny (~MB), no JSONL transfer needed.
    cmd = (
        "set -e && "
        "python -m pip install -q -U pip && "
        "python scripts/prepare_corpus.py && "
        "python scripts/finetune_lora.py && "
        "echo '=== adapter contents ===' && "
        "ls -la outputs/lora-gemma-4-mycelium-e4b/"
    )

    # NOTE: code= snapshots the repo root at submit time. Anything in
    # .gitignore (including data/, .venv/, kaggle-secrets/) is excluded
    # via the .amlignore equivalent — see _build_amlignore() below.
    _ensure_amlignore()

    job = command(
        code=str(REPO_ROOT),
        command=cmd,
        environment=environment,
        environment_variables=env_vars,
        compute=cluster_name,
        display_name=f"{JOB_NAME_PREFIX}-{gpu}",
        experiment_name="gemma-4-mycelium",
        outputs={"adapter": Output(type=AssetTypes.URI_FOLDER, mode="rw_mount")},
    )
    submitted = client.jobs.create_or_update(job)
    print(f"  job submitted: {submitted.name}")
    print(f"  studio URL: {submitted.studio_url}")
    return submitted.name


def _ensure_amlignore() -> None:
    """Write a minimal .amlignore so the code upload skips heavy directories."""
    amlignore = REPO_ROOT / ".amlignore"
    desired = """\
.venv/
.git/
__pycache__/
*.pyc
data/
kaggle-dataset/
kaggle-secrets/
lora-gemma-4-mycelium-e4b/
checkpoint-*/
*.gguf
*.safetensors
*.bin
*.log
"""
    if not amlignore.exists() or amlignore.read_text() != desired:
        amlignore.write_text(desired)


def status(job_name: str) -> None:
    client = _ml_client()
    job = client.jobs.get(job_name)
    print(f"  name: {job.name}")
    print(f"  status: {job.status}")
    print(f"  studio: {job.studio_url}")
    if job.status in {"Failed", "Canceled"} and getattr(job, "error", None):
        print(f"  error: {job.error}")


def logs(job_name: str) -> None:
    client = _ml_client()
    client.jobs.stream(job_name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gpu", choices=GPU_PROFILES.keys(), default="t4",
                        help="GPU SKU. t4 (cheap, slow) | a10 | a100 (fast) | h100 (fastest).")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--hf-repo", default="crowelogic/gemma-4-mycelium-e4b-lora",
                        help="HuggingFace repo to push adapter to (set --no-push to skip).")
    parser.add_argument("--no-push", action="store_true",
                        help="Skip pushing the adapter to HuggingFace at end of training.")
    parser.add_argument("--status", metavar="JOB", help="Poll status of a running job.")
    parser.add_argument("--logs", metavar="JOB", help="Stream logs from a running job.")
    args = parser.parse_args()

    if args.status:
        status(args.status)
        return 0
    if args.logs:
        logs(args.logs)
        return 0

    hf_repo = None if args.no_push else args.hf_repo
    name = submit(args.gpu, args.epochs, hf_repo)
    print()
    print(f"Poll:  python {sys.argv[0]} --status {name}")
    print(f"Logs:  python {sys.argv[0]} --logs {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
