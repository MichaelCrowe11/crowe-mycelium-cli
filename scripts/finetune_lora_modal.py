"""Gemma 4 Mycelium LoRA fine-tune via Modal Labs.

Modal is the right shape for a one-shot hackathon training run:
- Free tier: $30/mo of compute, enough for one A10 LoRA run with margin.
- HF_TOKEN passes through ``modal.Secret`` — encrypted at rest, scoped
  to the function that reads it, never serialized into any artifact.
- Modal handles GPU provisioning, image build, and result download.
  We just write a Python function and call it.

One-time setup (your terminal, not this script):
    pip install modal
    modal setup            # opens GitHub OAuth in browser, ~30s
    # The local kaggle.json + HF_TOKEN flow stays the same — Modal
    # gets HF_TOKEN via modal.Secret, never via the network.

Push the secret (one-time, programmatic):
    python scripts/finetune_lora_modal.py --create-secret

Train:
    python scripts/finetune_lora_modal.py                 # A10, 3 epochs
    python scripts/finetune_lora_modal.py --gpu A100      # faster, more $$
    python scripts/finetune_lora_modal.py --epochs 5      # longer run
    python scripts/finetune_lora_modal.py --no-push       # skip HF upload

Cost on A10 (default): ~$1.10/hr × ~2-3 hours = ~$3.30 total. T4 cheaper
(~$0.50/hr) but slower; A100 faster (~$3.20/hr) for ~1.5 hours = ~$4.80.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

import modal


APP_NAME = "crowe-mycelium-lora"
SECRET_NAME = "crowe-mycelium-secrets"
HF_REPO_DEFAULT = "crowelogic/gemma-4-mycelium-e4b-lora"
MODEL_BASE = "google/gemma-4-e4b"

# Modal image: starts from the PyTorch CUDA 12.1 base + transformers from
# main (Gemma 4 not yet in a tagged release) + the LoRA stack.
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git")
    .pip_install(
        "torch>=2.5.0",
        "transformers @ git+https://github.com/huggingface/transformers.git",
        "peft>=0.13.0",
        "trl>=0.12.0",
        "bitsandbytes>=0.44.0",
        "datasets>=3.0.0",
        "accelerate>=1.0.0",
        "sentencepiece",
        "protobuf",
        "huggingface_hub",
    )
)

app = modal.App(APP_NAME, image=image)

# Persistent volume for the adapter output — survives function execution
# and is downloadable to the local machine on demand.
volume = modal.Volume.from_name("crowe-mycelium-adapters", create_if_missing=True)


def _read_hf_token() -> str:
    """Source HF_TOKEN from ~/.env.secrets without echo."""
    if os.environ.get("HF_TOKEN"):
        return os.environ["HF_TOKEN"]
    env_path = Path.home() / ".env.secrets"
    if not env_path.exists():
        raise SystemExit("HF_TOKEN not in env and ~/.env.secrets missing")
    for line in env_path.read_text().splitlines():
        m = re.match(r"^(?:export\s+)?HF_TOKEN=(.+)$", line.strip())
        if m:
            return m.group(1).strip().strip('"').strip("'")
    raise SystemExit("HF_TOKEN not found in ~/.env.secrets")


@app.function(
    gpu="A10",
    timeout=4 * 3600,                       # 4 hours, generous ceiling
    volumes={"/adapters": volume},
    secrets=[modal.Secret.from_name(SECRET_NAME)],
)
def train_remote(
    instruct_jsonl_bytes: bytes,
    epochs: int = 3,
    base_model: str = MODEL_BASE,
    hf_repo: str | None = None,
) -> dict:
    """The actual training function — runs in a Modal container with one A10.

    Inputs travel into the container as function args; HF_TOKEN comes in via
    the secret. Outputs are written to ``/adapters/<run_id>`` on the Modal
    volume so the local side can pull them back after the call returns.
    """
    import json
    import time
    from pathlib import Path as _P

    import torch
    from huggingface_hub import login
    from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from datasets import load_dataset
    from trl import SFTTrainer, SFTConfig

    run_id = time.strftime("%Y%m%d-%H%M%S")
    output_dir = _P("/adapters") / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    # HF auth — the secret was injected as env var by Modal.
    hf_token = os.environ["HF_TOKEN"]
    login(token=hf_token, add_to_git_credential=False)
    print(f"[{run_id}] HF authed")

    # Stage the corpus the local side shipped to us.
    corpus_path = output_dir / "instruct.jsonl"
    corpus_path.write_bytes(instruct_jsonl_bytes)
    print(f"[{run_id}] corpus: {len(instruct_jsonl_bytes):,} bytes")

    # Load base model in 4-bit (QLoRA on A10 with 24GB VRAM headroom).
    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        quantization_config=bnb,
        device_map="auto",
        torch_dtype=torch.bfloat16,
        trust_remote_code=True,
        attn_implementation="eager",
    )
    model.config.use_cache = False
    model.gradient_checkpointing_enable()
    model = prepare_model_for_kbit_training(model)
    print(f"[{run_id}] loaded {base_model}")

    # LoRA adapter.
    model = get_peft_model(model, LoraConfig(
        r=16, lora_alpha=32, lora_dropout=0.05, bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
    ))
    model.print_trainable_parameters()

    # Dataset → Gemma chat template.
    SYSTEM = (
        "You are Gemma 4 Mycelium, an offline cultivation intelligence built "
        "on Gemma 4 by Crowe Logic. Ground every claim in commercial mycology "
        "practice. Be direct and concrete."
    )
    ds = load_dataset("json", data_files=str(corpus_path), split="train")
    def fmt(ex):
        msgs = [
            {"role": "user", "content": f"{SYSTEM}\n\n{ex['instruction']}"},
            {"role": "assistant", "content": ex["output"]},
        ]
        return {"text": tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=False)}
    ds = ds.map(fmt, remove_columns=ds.column_names)
    print(f"[{run_id}] dataset: {len(ds)} examples")

    trainer = SFTTrainer(
        model=model,
        args=SFTConfig(
            output_dir=str(output_dir / "checkpoints"),
            num_train_epochs=epochs,
            per_device_train_batch_size=2,
            gradient_accumulation_steps=8,
            gradient_checkpointing=True,
            optim="paged_adamw_8bit",
            learning_rate=2e-4,
            lr_scheduler_type="cosine",
            warmup_ratio=0.03,
            weight_decay=0.01,
            max_grad_norm=0.3,
            bf16=True,
            logging_steps=10,
            save_steps=200,
            save_total_limit=2,
            report_to="none",
            max_seq_length=2048,
            packing=False,
            dataset_text_field="text",
        ),
        train_dataset=ds,
        tokenizer=tokenizer,
    )
    trainer.train()
    trainer.save_model(str(output_dir / "adapter"))
    tokenizer.save_pretrained(str(output_dir / "adapter"))
    print(f"[{run_id}] adapter saved to {output_dir / 'adapter'}")

    # Manifest for the local side to know what landed.
    manifest = {
        "run_id": run_id,
        "base_model": base_model,
        "epochs": epochs,
        "examples": len(ds),
        "adapter_path": f"/adapters/{run_id}/adapter",
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    # Optional HF push.
    if hf_repo:
        from huggingface_hub import HfApi, create_repo
        create_repo(hf_repo, repo_type="model", exist_ok=True, private=False)
        trainer.model.push_to_hub(hf_repo, use_auth_token=hf_token)
        tokenizer.push_to_hub(hf_repo, use_auth_token=hf_token)
        manifest["hf_repo"] = hf_repo
        print(f"[{run_id}] pushed to https://huggingface.co/{hf_repo}")

    volume.commit()
    return manifest


@app.function(volumes={"/adapters": volume})
def list_adapters() -> list[str]:
    from pathlib import Path as _P
    return sorted([str(p.name) for p in _P("/adapters").iterdir() if p.is_dir()])


# ── Local entrypoints ─────────────────────────────────────────────────────


def create_secret():
    """One-shot: push HF_TOKEN from ~/.env.secrets into Modal as a secret."""
    token = _read_hf_token()
    # Use the modal CLI for secret create (the SDK secret-create API requires
    # internal credentials). The CLI inherits the user's `modal setup` token.
    proc = subprocess.run(
        ["modal", "secret", "create", SECRET_NAME, f"HF_TOKEN={token}"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        # If it already exists, try update (delete + recreate).
        if "already exists" in (proc.stderr or "") or "AlreadyExists" in (proc.stderr or ""):
            print(f"  secret {SECRET_NAME} exists — recreating")
            subprocess.run(["modal", "secret", "delete", SECRET_NAME], check=False)
            proc = subprocess.run(
                ["modal", "secret", "create", SECRET_NAME, f"HF_TOKEN={token}"],
                capture_output=True, text=True,
            )
    if proc.returncode != 0:
        print(f"  failed: {proc.stderr}", file=sys.stderr)
        return 1
    print(f"  secret '{SECRET_NAME}' set in Modal (HF_TOKEN, {len(token)} chars)")
    return 0


@app.local_entrypoint()
def main(
    gpu: str = "A10",
    epochs: int = 3,
    no_push: bool = False,
    hf_repo: str = HF_REPO_DEFAULT,
):
    """Submit a training run.

    Run with: `modal run scripts/finetune_lora_modal.py::main --gpu A10`
    """
    # Patch the function's GPU choice on the fly (Modal binds GPU at @function,
    # so we reuse the same function and accept the binding for now).
    if gpu != "A10":
        print(f"  NOTE: function bound to A10 at decoration time. To use {gpu},")
        print(f"        edit the @app.function(gpu=...) line and re-deploy.")

    instruct_path = Path(__file__).resolve().parents[1] / "data" / "instruct.jsonl"
    if not instruct_path.exists():
        raise SystemExit(f"corpus missing — run: python scripts/prepare_corpus.py")
    instruct_bytes = instruct_path.read_bytes()
    print(f"  shipping corpus: {len(instruct_bytes):,} bytes")

    target_repo = None if no_push else hf_repo
    manifest = train_remote.remote(
        instruct_jsonl_bytes=instruct_bytes,
        epochs=epochs,
        hf_repo=target_repo,
    )
    print()
    print(f"  manifest: {manifest}")
    print(f"  pull adapter back with:")
    print(f"    modal volume get crowe-mycelium-adapters {manifest['run_id']}/adapter ./lora-output")


if __name__ == "__main__":
    # When invoked directly (not via `modal run`), expose the CLI helpers.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--create-secret", action="store_true",
                        help="Push HF_TOKEN from ~/.env.secrets into Modal as a secret.")
    parser.add_argument("--list", action="store_true",
                        help="List adapters in the persistent volume.")
    args = parser.parse_args()
    if args.create_secret:
        raise SystemExit(create_secret())
    if args.list:
        # Need to deploy first to run list_adapters; cheaper to use the
        # `modal volume ls` CLI directly:
        subprocess.run(["modal", "volume", "ls", "crowe-mycelium-adapters"])
        raise SystemExit(0)
    # No flag: show usage.
    parser.print_help()
