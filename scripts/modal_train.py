"""Modal-wrapped Unsloth QLoRA training.

Uploads shard files (from local shards/) into a Modal Volume, runs Unsloth
training on a Modal A10/A100, saves the LoRA adapter to a Volume, and
downloads it back to local runs/.

Usage:
    modal run scripts/modal_train.py --shards "shards/*.jsonl"
    modal run scripts/modal_train.py --shards "shards/magpie_0000.jsonl" --max-steps 5 --gpu A10G

Costs (Modal pricing, 2026):
  A10G  ~$1.10/hr   — Gemma 3 4B QLoRA: ~200-400 steps/min
  A100  ~$2.00/hr   — ~600-1000 steps/min
"""
import glob, json, shutil
from datetime import datetime
from pathlib import Path

import modal

app = modal.App("crowe-mycelium-train")
runs_volume = modal.Volume.from_name("crowe-mycelium-runs", create_if_missing=True)
data_volume = modal.Volume.from_name("crowe-mycelium-shards", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "build-essential")
    .pip_install(
        "torch>=2.7",
        "transformers>=4.50,<5",
        "trl<0.21",
        "peft", "bitsandbytes", "datasets", "accelerate",
        "huggingface-hub", "sentencepiece", "protobuf", "scipy",
        "unsloth", "unsloth_zoo",
    )
)


@app.function(
    image=image, gpu="A10G", timeout=14400,
    volumes={"/runs": runs_volume, "/data": data_volume},
    secrets=[modal.Secret.from_name("huggingface")],
)
def train(run_name: str, model: str, max_seq_length: int = 2048,
          batch_size: int = 2, grad_accum: int = 8,
          lora_r: int = 16, lora_alpha: int = 32, lr: float = 2e-4,
          epochs: int = 1, max_steps: int = -1, warmup: int = 10,
          save_steps: int = 100) -> dict:
    """Remote training entrypoint. Expects shards already uploaded to /data."""
    import os, glob
    import torch
    from unsloth import FastLanguageModel, is_bfloat16_supported
    from trl import SFTTrainer
    from transformers import TrainingArguments
    from datasets import load_dataset

    shard_files = sorted(glob.glob("/data/*.jsonl"))
    if not shard_files:
        raise SystemExit(f"No shards in /data")
    print(f"[modal-train] {len(shard_files)} shards available")

    print(f"[modal-train] Loading {model}...")
    m, tok = FastLanguageModel.from_pretrained(
        model_name=model, max_seq_length=max_seq_length,
        dtype=None, load_in_4bit=True,
    )
    m = FastLanguageModel.get_peft_model(
        m, r=lora_r, target_modules=[
            "q_proj","k_proj","v_proj","o_proj","gate_proj","up_proj","down_proj",
        ],
        lora_alpha=lora_alpha, lora_dropout=0, bias="none",
        use_gradient_checkpointing="unsloth", random_state=42,
    )

    ds = load_dataset("json", data_files=shard_files, split="train")
    print(f"[modal-train] {len(ds)} examples")

    if "text" not in ds.column_names:
        def fmt(ex):
            msgs = [
                {"role": "user", "content": ex["instruction"]},
                {"role": "assistant", "content": ex["output"]},
            ]
            return {"text": tok.apply_chat_template(msgs, tokenize=False)}
        ds = ds.map(fmt, remove_columns=ds.column_names)

    out_dir = f"/runs/{run_name}"
    os.makedirs(out_dir, exist_ok=True)

    trainer = SFTTrainer(
        model=m, tokenizer=tok, train_dataset=ds,
        dataset_text_field="text", max_seq_length=max_seq_length,
        dataset_num_proc=2, packing=False,
        args=TrainingArguments(
            per_device_train_batch_size=batch_size,
            gradient_accumulation_steps=grad_accum,
            warmup_steps=warmup, num_train_epochs=epochs,
            max_steps=max_steps if max_steps > 0 else -1,
            learning_rate=lr,
            fp16=not is_bfloat16_supported(),
            bf16=is_bfloat16_supported(),
            logging_steps=10, optim="paged_adamw_8bit",
            weight_decay=0.01, lr_scheduler_type="linear", seed=42,
            output_dir=out_dir, save_strategy="steps",
            save_steps=save_steps, report_to=[],
        ),
    )

    result = trainer.train()

    adapter_dir = f"{out_dir}/final"
    m.save_pretrained(adapter_dir)
    tok.save_pretrained(adapter_dir)

    meta = {
        "model": model, "shards": shard_files, "examples": len(ds),
        "epochs": epochs, "max_steps": max_steps,
        "lora_r": lora_r, "lora_alpha": lora_alpha,
        "batch_size": batch_size, "grad_accum": grad_accum,
        "effective_batch": batch_size * grad_accum,
        "lr": lr, "max_seq_length": max_seq_length,
        "final_loss": float(result.training_loss),
        "global_steps": int(result.global_step),
        "completed_at": datetime.utcnow().isoformat(timespec="seconds"),
        "gpu": torch.cuda.get_device_name(0),
    }
    with open(f"{out_dir}/run_meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    runs_volume.commit()
    print(f"[modal-train] adapter saved to volume at {out_dir}/final")
    return meta


@app.function(image=image, volumes={"/data": data_volume})
def upload_shards(shard_contents: dict) -> int:
    """Receive {filename: jsonl_bytes} mapping, write to /data volume."""
    import os
    n = 0
    for name, content in shard_contents.items():
        path = f"/data/{os.path.basename(name)}"
        with open(path, "wb") as f:
            f.write(content)
        n += 1
    data_volume.commit()
    return n


@app.function(image=image, volumes={"/runs": runs_volume})
def list_runs() -> list:
    import os
    return sorted(os.listdir("/runs")) if os.path.isdir("/runs") else []


@app.function(image=image, volumes={"/runs": runs_volume})
def download_adapter(run_name: str) -> dict:
    """Return adapter files as {relative_path: bytes}."""
    import os
    base = f"/runs/{run_name}/final"
    if not os.path.isdir(base):
        return {}
    out = {}
    for root, _, files in os.walk(base):
        for fn in files:
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, base)
            with open(p, "rb") as f:
                out[rel] = f.read()
    return out


@app.local_entrypoint()
def main(shards: str = "shards/*.jsonl",
         model: str = "unsloth/gemma-3-4b-it-bnb-4bit",
         run_name: str = None,
         max_steps: int = -1, epochs: int = 1,
         batch_size: int = 2, grad_accum: int = 8,
         lora_r: int = 16, lora_alpha: int = 32, lr: float = 2e-4,
         max_seq_length: int = 2048, warmup: int = 10, save_steps: int = 100):
    repo_root = Path(__file__).resolve().parent.parent
    files = sorted(glob.glob(str(repo_root / shards)))
    if not files:
        raise SystemExit(f"No shards matched {shards}")

    if run_name is None:
        run_name = f"unsloth-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"

    print(f"[modal-train] uploading {len(files)} shards to Modal Volume...")
    contents = {Path(f).name: open(f, "rb").read() for f in files}
    n = upload_shards.remote(contents)
    print(f"[modal-train] uploaded {n} shards. starting training as run '{run_name}'...")

    meta = train.remote(
        run_name=run_name, model=model, max_seq_length=max_seq_length,
        batch_size=batch_size, grad_accum=grad_accum,
        lora_r=lora_r, lora_alpha=lora_alpha, lr=lr,
        epochs=epochs, max_steps=max_steps, warmup=warmup, save_steps=save_steps,
    )
    print(f"[modal-train] training done. final_loss={meta['final_loss']:.4f}")

    print(f"[modal-train] downloading adapter...")
    files_map = download_adapter.remote(run_name)
    local_dir = repo_root / "runs" / run_name / "final"
    local_dir.mkdir(parents=True, exist_ok=True)
    for rel, blob in files_map.items():
        p = local_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(blob)
    (repo_root / "runs" / run_name / "run_meta.json").write_text(json.dumps(meta, indent=2))
    print(f"[modal-train] adapter at runs/{run_name}/final/")
