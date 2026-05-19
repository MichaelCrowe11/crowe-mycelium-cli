"""Unsloth-based local QLoRA trainer for Crowe LM.

Consumes JSONL shards from shards/ (or any glob) and produces a LoRA adapter
in runs/. Designed for the 10 GB RTX 3080: 4-bit weights, paged 8-bit Adam,
unsloth gradient checkpointing. ~2x faster than vanilla peft+trl.

Usage:
    python scripts/finetune_lora_unsloth.py --shards "shards/*.jsonl"
    python scripts/finetune_lora_unsloth.py --shards "shards/magpie_00*.jsonl" --max-steps 100
"""
import argparse, glob, json, os
from datetime import datetime
from pathlib import Path

import torch
from unsloth import FastLanguageModel, is_bfloat16_supported
from trl import SFTTrainer
from transformers import TrainingArguments
from datasets import load_dataset


def main(args):
    print(f"[train] Loading {args.model} in 4-bit...")
    model, tok = FastLanguageModel.from_pretrained(
        model_name=args.model,
        max_seq_length=args.max_seq_length,
        dtype=None,
        load_in_4bit=True,
    )

    model = FastLanguageModel.get_peft_model(
        model,
        r=args.lora_r,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        lora_alpha=args.lora_alpha,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )

    shard_files = sorted(glob.glob(args.shards))
    if not shard_files:
        raise SystemExit(f"[train] No shards matched: {args.shards}")
    print(f"[train] Found {len(shard_files)} shard(s); loading...")
    dataset = load_dataset("json", data_files=shard_files, split="train")
    print(f"[train] {len(dataset)} examples loaded")

    if "text" not in dataset.column_names:
        if "instruction" in dataset.column_names and "output" in dataset.column_names:
            def fmt(ex):
                msgs = [
                    {"role": "user", "content": ex["instruction"]},
                    {"role": "assistant", "content": ex["output"]},
                ]
                return {"text": tok.apply_chat_template(msgs, tokenize=False)}
            dataset = dataset.map(fmt, remove_columns=dataset.column_names)
        else:
            raise SystemExit(f"[train] Need 'text' or 'instruction'+'output' columns; got {dataset.column_names}")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    trainer = SFTTrainer(
        model=model,
        tokenizer=tok,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=args.max_seq_length,
        dataset_num_proc=2,
        packing=False,
        args=TrainingArguments(
            per_device_train_batch_size=args.batch_size,
            gradient_accumulation_steps=args.grad_accum,
            warmup_steps=args.warmup,
            num_train_epochs=args.epochs,
            max_steps=args.max_steps if args.max_steps > 0 else -1,
            learning_rate=args.lr,
            fp16=not is_bfloat16_supported(),
            bf16=is_bfloat16_supported(),
            logging_steps=10,
            optim="paged_adamw_8bit",
            weight_decay=0.01,
            lr_scheduler_type="linear",
            seed=42,
            output_dir=str(out_dir),
            save_strategy="steps",
            save_steps=args.save_steps,
            report_to=[],
        ),
    )

    train_result = trainer.train()

    adapter_dir = out_dir / "final"
    model.save_pretrained(str(adapter_dir))
    tok.save_pretrained(str(adapter_dir))

    meta = {
        "model": args.model,
        "shards": shard_files,
        "examples": len(dataset),
        "epochs": args.epochs,
        "max_steps": args.max_steps,
        "lora_r": args.lora_r,
        "lora_alpha": args.lora_alpha,
        "batch_size": args.batch_size,
        "grad_accum": args.grad_accum,
        "effective_batch": args.batch_size * args.grad_accum,
        "lr": args.lr,
        "max_seq_length": args.max_seq_length,
        "final_loss": float(train_result.training_loss),
        "global_steps": int(train_result.global_step),
        "completed_at": datetime.now().isoformat(),
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu",
    }
    with open(out_dir / "run_meta.json", "w") as f:
        json.dump(meta, f, indent=2)
    print(f"[train] Adapter saved to {adapter_dir}")
    print(f"[train] Final loss: {meta['final_loss']:.4f} | steps: {meta['global_steps']}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--model",
                   default=os.environ.get("BASE_MODEL", "unsloth/gemma-3-4b-it-bnb-4bit"))
    p.add_argument("--shards", default="shards/*.jsonl")
    p.add_argument("--out-dir", default=f"runs/unsloth-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    p.add_argument("--max-seq-length", type=int, default=2048)
    p.add_argument("--batch-size", type=int, default=2)
    p.add_argument("--grad-accum", type=int, default=8)
    p.add_argument("--warmup", type=int, default=10)
    p.add_argument("--epochs", type=int, default=1)
    p.add_argument("--max-steps", type=int, default=-1)
    p.add_argument("--save-steps", type=int, default=100)
    p.add_argument("--lora-r", type=int, default=16)
    p.add_argument("--lora-alpha", type=int, default=32)
    p.add_argument("--lr", type=float, default=2e-4)
    main(p.parse_args())
