#!/usr/bin/env python3
"""Extract a text-only Gemma 4 model from the multimodal checkpoint.

Multimodal Gemma 4 wraps the language model under ``language_model.*`` and
adds vision_tower + audio_tower siblings. mlx-lm's ``gemma4`` class expects
the multimodal structure; its ``gemma4_text`` class expects a flat text-only
namespace.

For LoRA fine-tuning on cultivation prose, we only need the text path. This
script:

1. Reads the multimodal model from
   ``mlx-community/gemma-4-e4b-it-4bit`` (cached locally).
2. Extracts ``text_config`` and rewrites the top-level config to
   ``Gemma4ForCausalLM`` + ``model_type: gemma4_text``.
3. Filters the safetensors to keep only ``language_model.*`` keys.
4. Strips the ``language_model.`` prefix so keys map onto mlx-lm's
   ``gemma4_text`` model class.
5. Copies the tokenizer files unchanged.
6. Writes the result to a local directory mlx-lm can load directly.

Usage:
    python scripts/extract_text_model.py
    python scripts/extract_text_model.py --src <path> --dst <path>
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


DEFAULT_SRC_HUB = "/Volumes/Elements/huggingface-cache/hub/models--mlx-community--gemma-4-e4b-it-4bit/snapshots"
DEFAULT_DST = "/Volumes/Elements/gemma-4-e4b-text-mlx"


def _find_snapshot(hub_root: Path) -> Path:
    snapshots = list(hub_root.iterdir())
    if not snapshots:
        raise SystemExit(f"no snapshot in {hub_root}")
    return snapshots[0]


def extract(src: Path, dst: Path) -> int:
    if not src.exists():
        raise SystemExit(f"source missing: {src}")
    dst.mkdir(parents=True, exist_ok=True)

    print(f"  src: {src}")
    print(f"  dst: {dst}")
    print()

    # 1. Rewrite config.json
    src_cfg = json.loads((src / "config.json").read_text())
    text_cfg = src_cfg.get("text_config", {})
    if not text_cfg:
        raise SystemExit("source config.json has no text_config block")

    new_cfg = dict(text_cfg)
    # mlx-lm dispatches on model_type. ``gemma4_text`` exists as a file in
    # mlx_lm.models; that's the loader we want.
    new_cfg["model_type"] = "gemma4_text"
    new_cfg["architectures"] = ["Gemma4ForCausalLM"]
    # Some text_config blocks omit tokenizer-relevant fields that live at top
    # level in HF configs; carry them forward.
    for k in ("bos_token_id", "eos_token_id", "pad_token_id", "torch_dtype",
              "dtype", "transformers_version"):
        if k in src_cfg and k not in new_cfg:
            new_cfg[k] = src_cfg[k]
    # Preserve quantization metadata so mlx-lm reads the 4-bit weights right.
    if "quantization" in src_cfg:
        new_cfg["quantization"] = src_cfg["quantization"]
    (dst / "config.json").write_text(json.dumps(new_cfg, indent=2) + "\n")
    print(f"  config.json written ({len(new_cfg)} keys, model_type={new_cfg['model_type']})")

    # 2. Filter + rename safetensors. Using PyTorch's safetensors backend
    #    because numpy can't round-trip bf16 and MLX's save_safetensors
    #    pushes all tensors through Metal at once (GPU timeout). PyTorch
    #    streams writes directly to disk via memmap.
    import torch
    from safetensors import safe_open
    from safetensors.torch import save_file as save_pt

    shards = sorted(src.glob("*.safetensors"))
    print(f"  source shards: {len(shards)}")

    kept = 0
    dropped = 0
    total = 0
    new_weights: dict = {}

    for shard in shards:
        with safe_open(str(shard), framework="pt") as f:
            for key in f.keys():
                total += 1
                if key.startswith("language_model."):
                    new_key = key[len("language_model."):]
                    tensor = f.get_tensor(key)
                    new_weights[new_key] = tensor
                    kept += 1
                else:
                    dropped += 1

    print(f"  scanned {total} keys, kept {kept}, dropped {dropped}")
    print(f"  writing combined model.safetensors via torch backend...")
    save_pt(new_weights, str(dst / "model.safetensors"), metadata={"format": "pt"})
    print(f"  wrote model.safetensors ({(dst / 'model.safetensors').stat().st_size / 1e9:.2f} GB)")

    # 3. Copy tokenizer files unchanged.
    tokenizer_files = [
        "tokenizer.json", "tokenizer_config.json",
        "special_tokens_map.json", "generation_config.json",
        "chat_template.json", "processor_config.json",
    ]
    for fname in tokenizer_files:
        src_file = src / fname
        if src_file.exists():
            shutil.copy2(src_file, dst / fname)
            print(f"  copied {fname}")

    print()
    print(f"  text-only model ready at: {dst}")
    print(f"  use in mlx-lm with: --model {dst}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path,
                        help="Source snapshot dir; default: mlx-community gemma-4-e4b-it-4bit cache")
    parser.add_argument("--dst", type=Path, default=Path(DEFAULT_DST))
    args = parser.parse_args()

    if args.src is None:
        hub = Path(DEFAULT_SRC_HUB)
        args.src = _find_snapshot(hub)

    return extract(args.src, args.dst)


if __name__ == "__main__":
    raise SystemExit(main())
