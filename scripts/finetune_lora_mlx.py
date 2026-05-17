"""Gemma 4 Mycelium LoRA fine-tune via Apple MLX — runs on this Mac.

Strict-security path: HF_TOKEN literally never leaves this machine. The
adapter is trained on Apple Silicon (M1/M2/M3/M4) using Apple's MLX
framework + mlx-lm's built-in LoRA trainer. Output is a small adapter
file (~30MB) that can be merged back into the base model + converted to
GGUF for Ollama distribution.

Why this works on Mac:
- MLX is purpose-built for Apple's unified-memory architecture; the M-series
  GPU can hold Gemma 4 E4B (4B effective params, ~9GB at 4-bit) in
  shared RAM without OOM on 32GB+ Macs.
- mlx-lm's LoRA trainer is a drop-in replacement for HF transformers'
  trainer with 80-90% of the same hyperparam surface.

One-time setup (you only do this once per Mac):
    .venv/bin/pip install mlx-lm
    # Accept Gemma 4 terms on HF first (one click in browser):
    # https://huggingface.co/google/gemma-4-e4b
    huggingface-cli login   # paste HF_TOKEN from ~/.env.secrets, OR:
    # ./.venv/bin/python -c "from huggingface_hub import login; \
    #   import re, pathlib; \
    #   t=re.search(r'^(?:export\s+)?HF_TOKEN=(.+)$', \
    #     pathlib.Path('~/.env.secrets').expanduser().read_text(), \
    #     re.M).group(1).strip(); login(t)"

Train:
    python scripts/finetune_lora_mlx.py                 # 3 epochs, default
    python scripts/finetune_lora_mlx.py --iters 1000    # explicit iteration count
    python scripts/finetune_lora_mlx.py --batch-size 1  # if 16GB Mac is tight

Wall time on M2 Max (12-core GPU, 32GB unified RAM): ~6-8 hours for
3 epochs over the ~3k example corpus. M3 Max / M4 Max: ~3-4 hours.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
MLX_DATA_DIR = REPO_ROOT / "mlx_data"
ADAPTER_DIR = REPO_ROOT / "adapters" / "gemma-4-mycelium-e4b"
BASE_MODEL = "/Volumes/Elements/gemma-4-e4b-text-mlx"

# Gemma chat template — same identity-and-role anchor used by the Modelfile.
SYSTEM = (
    "You are Gemma 4 Mycelium, an offline cultivation intelligence built "
    "on Gemma 4 by Crowe Logic. Ground every claim in commercial mycology "
    "practice. Be direct and concrete."
)


def _ensure_deps() -> None:
    """Install mlx-lm if not already present in the venv."""
    try:
        import mlx_lm  # noqa
        return
    except ImportError:
        pass
    print("  installing mlx-lm into venv (one-time, ~150MB)...")
    venv_pip = REPO_ROOT / ".venv" / "bin" / "pip"
    pip = str(venv_pip) if venv_pip.exists() else sys.executable + " -m pip"
    subprocess.check_call(f"{pip} install -q -U mlx-lm".split())


def _ensure_hf_auth() -> None:
    """Bootstrap HF auth from ~/.env.secrets if not already logged in.

    ``huggingface_hub`` 1.x removed ``HfFolder``; use ``get_token()`` from
    the top-level module (or fall back to ``HF_TOKEN`` env-var detection,
    which the hub library checks automatically on unauthenticated calls).
    """
    try:
        from huggingface_hub import get_token, login
    except ImportError:  # very-old hub
        from huggingface_hub import login
        def get_token():
            return os.environ.get("HF_TOKEN")
    if get_token() or os.environ.get("HF_TOKEN"):
        return
    env_path = Path.home() / ".env.secrets"
    if not env_path.exists():
        raise SystemExit(
            "Not logged in to HuggingFace and ~/.env.secrets missing. "
            "Run: huggingface-cli login"
        )
    for line in env_path.read_text().splitlines():
        m = re.match(r"^(?:export\s+)?HF_TOKEN=(.+)$", line.strip())
        if m:
            token = m.group(1).strip().strip('"').strip("'")
            login(token=token, add_to_git_credential=False)
            print(f"  HF auth bootstrapped from ~/.env.secrets ({len(token)} chars)")
            return
    raise SystemExit("HF_TOKEN not found in ~/.env.secrets")


def _convert_corpus_for_mlx() -> None:
    """mlx-lm expects ``train.jsonl`` + ``valid.jsonl`` in a folder, with each
    line a ``{"text": "..."}`` record.

    Our ``data/instruct.jsonl`` is ``{"instruction", "output", ...}``. Apply
    the Gemma chat template here so the trainer sees ready-to-tokenize text
    and we keep one canonical chat-format definition (this one).
    """
    instruct_path = DATA_DIR / "instruct.jsonl"
    if not instruct_path.exists():
        raise SystemExit(
            "data/instruct.jsonl missing — run: python scripts/prepare_corpus.py"
        )
    MLX_DATA_DIR.mkdir(parents=True, exist_ok=True)
    records = []
    with instruct_path.open() as f:
        for line in f:
            ex = json.loads(line)
            # Gemma 4 chat template — explicit turn markers so the model
            # learns the response structure, not just raw content.
            text = (
                "<start_of_turn>user\n"
                f"{SYSTEM}\n\n{ex['instruction']}<end_of_turn>\n"
                "<start_of_turn>model\n"
                f"{ex['output']}<end_of_turn>"
            )
            records.append({"text": text})

    # 95/5 train/valid split. Stable shuffle so re-runs give identical splits
    # — important because mlx-lm checkpoints can be resumed mid-training.
    import random
    rng = random.Random(0xc0ffee)
    rng.shuffle(records)
    split = max(1, int(len(records) * 0.05))
    valid = records[:split]
    train = records[split:]

    (MLX_DATA_DIR / "train.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in train) + "\n"
    )
    (MLX_DATA_DIR / "valid.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in valid) + "\n"
    )
    print(f"  mlx corpus: {len(train)} train + {len(valid)} valid in {MLX_DATA_DIR}")


def train(args: argparse.Namespace) -> int:
    _ensure_deps()
    _ensure_hf_auth()
    _convert_corpus_for_mlx()

    if ADAPTER_DIR.exists() and not args.resume:
        print(f"  WARN: {ADAPTER_DIR} exists. Use --resume to continue or delete it.")
    ADAPTER_DIR.mkdir(parents=True, exist_ok=True)

    # mlx_lm exposes its LoRA trainer via a module-level CLI. We invoke it
    # directly rather than re-implementing — that way upstream improvements
    # land in our pipeline for free.
    cmd = [
        sys.executable, "-m", "mlx_lm", "lora",
        "--model", BASE_MODEL,
        "--train",
        "--data", str(MLX_DATA_DIR),
        "--adapter-path", str(ADAPTER_DIR),
        "--iters", str(args.iters),
        "--batch-size", str(args.batch_size),
        "--num-layers", str(args.lora_layers),
        "--steps-per-eval", str(args.eval_every),
        "--learning-rate", str(args.learning_rate),
        "--save-every", str(args.save_every),
        "--seed", str(0xc0ffee),  # = 12648430; mlx-lm wants a decimal int
        "--grad-checkpoint",      # essential to fit Gemma 4 E4B in unified RAM
    ]
    if args.resume:
        cmd.append("--resume-adapter-file")
        cmd.append(str(ADAPTER_DIR / "adapters.safetensors"))
    print(f"  running: {' '.join(cmd)}")
    return subprocess.call(cmd)


def fuse(args: argparse.Namespace) -> int:
    """Merge the LoRA adapter into the base model weights (post-training).

    Output: a full-weight HF checkpoint ready for GGUF conversion + Ollama
    packaging (see scripts/export_to_ollama.sh).
    """
    _ensure_deps()
    out = REPO_ROOT / "merged-gemma-4-mycelium-e4b"
    if out.exists():
        shutil.rmtree(out)
    cmd = [
        sys.executable, "-m", "mlx_lm", "fuse",
        "--model", BASE_MODEL,
        "--adapter-path", str(ADAPTER_DIR),
        "--save-path", str(out),
    ]
    print(f"  running: {' '.join(cmd)}")
    rc = subprocess.call(cmd)
    if rc == 0:
        print(f"\n  merged weights at: {out}")
        print("  next: convert to GGUF + build Ollama image with scripts/export_to_ollama.sh")
    return rc


def chat(args: argparse.Namespace) -> int:
    """Interactive chat against the local adapter — sanity-check before fusing."""
    _ensure_deps()
    cmd = [
        sys.executable, "-m", "mlx_lm", "generate",
        "--model", BASE_MODEL,
        "--adapter-path", str(ADAPTER_DIR),
        "--prompt", args.prompt,
        "--max-tokens", str(args.max_tokens),
    ]
    return subprocess.call(cmd)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    train_p = sub.add_parser("train", help="Run the LoRA fine-tune (default).")
    train_p.add_argument("--iters", type=int, default=1000,
                         help="Total training iterations (default 1000 ≈ 3 epochs on 3k examples).")
    train_p.add_argument("--batch-size", type=int, default=2)
    train_p.add_argument("--lora-layers", type=int, default=16,
                         help="Number of transformer layers to attach LoRA to (16 is the mlx-lm default).")
    train_p.add_argument("--learning-rate", type=float, default=2e-4)
    train_p.add_argument("--eval-every", type=int, default=100)
    train_p.add_argument("--save-every", type=int, default=200)
    train_p.add_argument("--resume", action="store_true",
                         help="Continue from the last adapter checkpoint at $ADAPTER_DIR.")

    fuse_p = sub.add_parser("fuse", help="Merge adapter into base weights.")

    chat_p = sub.add_parser("chat", help="One-shot generation against the adapter.")
    chat_p.add_argument("prompt", help="Cultivation question to probe the adapter.")
    chat_p.add_argument("--max-tokens", type=int, default=200)

    args = parser.parse_args()
    if args.cmd == "train":
        return train(args)
    if args.cmd == "fuse":
        return fuse(args)
    if args.cmd == "chat":
        return chat(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
