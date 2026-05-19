"""Magpie-style synthetic instruction generator (local, Unsloth teacher).

Magpie technique: feed the chat template's user-turn opener with NO content,
let the instruction-tuned teacher generate both the user question AND its
own answer. Surprisingly high-quality, no seed prompts needed.

Output: JSONL shards in shards/ — one shard per N examples. Each shard is
self-contained and small enough to commit to git (<50 MB).

Reference: https://arxiv.org/abs/2406.08464

Usage:
    python scripts/synth_magpie.py --total 1000 --shard-size 500
    python scripts/synth_magpie.py --total 100000 --shard-size 10000 --model unsloth/Llama-3.1-8B-Instruct-bnb-4bit
"""
import argparse, hashlib, json, random, re
from datetime import datetime
from pathlib import Path

import torch
from unsloth import FastLanguageModel

# Domain seeds steer ~30% of generations toward Crowe Logic territory.
DOMAIN_SEEDS = [
    "mycology and mushroom cultivation",
    "Lion's Mane (Hericium erinaceus) commercial production",
    "psilocybin mushroom biology and pharmacology",
    "mycelium substrate sterilization and inoculation",
    "fruiting chamber humidity and CO2 management",
    "contamination identification (Trichoderma, bacterial blotch, cobweb)",
    "mushroom species identification by morphology",
    "bioactive compounds in medicinal fungi (hericenones, erinacines, beta-glucans)",
    "spawn production and grain colonization",
    "small-batch commercial mushroom farming economics",
]


def hash_example(ex):
    return hashlib.md5((ex["instruction"] + "||" + ex["output"]).encode()).hexdigest()


_END_PATTERNS = [
    (r"<\|im_end\|>", r"<\|im_start\|>assistant\s*", r"<\|im_end\|>|<\|endoftext\|>"),
    (r"<end_of_turn>", r"<start_of_turn>model\s*", r"<end_of_turn>|<eos>"),
    (r"<\|eot_id\|>", r"<\|start_header_id\|>assistant<\|end_header_id\|>\s*", r"<\|eot_id\|>"),
]


def parse_magpie(new_text):
    """Parse generated-only text (no prompt prefix) for instruction + response."""
    for u_end, a_start, a_end in _END_PATTERNS:
        pat = rf"^(.*?){u_end}\s*{a_start}(.*?)(?:{a_end}|$)"
        m = re.match(pat, new_text, re.S)
        if m:
            return m.group(1).strip(), m.group(2).strip()
    return None, None


def magpie_prefix(model_name: str, tok) -> str:
    ml = model_name.lower()
    if "qwen" in ml:
        sys_p = "You are Qwen, created by Alibaba Cloud. You are a helpful assistant."
        return f"<|im_start|>system\n{sys_p}<|im_end|>\n<|im_start|>user\n"
    if "gemma" in ml:
        return "<start_of_turn>user\n"
    if "llama" in ml:
        return "<|begin_of_text|><|start_header_id|>user<|end_header_id|>\n\n"
    prefix = tok.apply_chat_template([{"role": "user", "content": ""}], tokenize=False)
    for end in ["<|im_end|>", "<end_of_turn>", "<|eot_id|>"]:
        if end in prefix:
            prefix = prefix.split(end, 1)[0].rstrip() + "\n"
            break
    return prefix


def quality_ok(instruction, output):
    if not instruction or not output:
        return False
    if len(instruction) < 10 or len(output) < 30:
        return False
    if len(instruction) > 1500 or len(output) > 4000:
        return False
    if instruction.lower().startswith(("i can't", "i'm sorry", "as an ai")):
        return False
    return True


def main(args):
    print(f"[magpie] Teacher: {args.model}")
    model, tok = FastLanguageModel.from_pretrained(
        model_name=args.model,
        max_seq_length=2048,
        dtype=None,
        load_in_4bit=True,
    )
    FastLanguageModel.for_inference(model)

    # Magpie opener: model-specific chat prefix ending mid user-turn.
    user_open = magpie_prefix(args.model, tok)
    tok.padding_side = "left"

    shards_dir = Path(args.out_dir)
    shards_dir.mkdir(parents=True, exist_ok=True)

    seen = set()
    for f in shards_dir.glob("*.jsonl"):
        for line in open(f, encoding="utf-8"):
            try:
                seen.add(hash_example(json.loads(line)))
            except Exception:
                pass
    print(f"[magpie] {len(seen)} existing examples (dedup baseline)")

    shard_idx = 0
    while (shards_dir / f"magpie_{shard_idx:04d}.jsonl").exists():
        shard_idx += 1

    pending = []
    total = 0
    rng = random.Random(args.seed)

    while total < args.total:
        # 30% domain-seeded, 70% open
        prompts = []
        for _ in range(args.batch):
            if rng.random() < 0.3:
                seed = rng.choice(DOMAIN_SEEDS)
                prompts.append(user_open + f" Ask about {seed}.")
            else:
                prompts.append(user_open)

        inputs = tok(prompts, return_tensors="pt", padding=True).to("cuda")
        prompt_len = inputs["input_ids"].shape[1]
        with torch.no_grad():
            out = model.generate(
                **inputs,
                max_new_tokens=args.max_new_tokens,
                do_sample=True, temperature=0.9, top_p=0.95,
                pad_token_id=tok.eos_token_id,
            )
        for i in range(out.shape[0]):
            new_tokens = out[i][prompt_len:]
            text = tok.decode(new_tokens, skip_special_tokens=False)
            instr, resp = parse_magpie(text)
            if not quality_ok(instr, resp):
                continue
            ex = {
                "instruction": instr,
                "output": resp,
                "source": "magpie",
                "teacher": args.model,
                "ts": datetime.now().isoformat(timespec="seconds"),
            }
            h = hash_example(ex)
            if h in seen:
                continue
            seen.add(h)
            pending.append(ex)
            total += 1

            if len(pending) >= args.shard_size:
                fp = shards_dir / f"magpie_{shard_idx:04d}.jsonl"
                with open(fp, "w", encoding="utf-8") as fo:
                    for e in pending:
                        fo.write(json.dumps(e, ensure_ascii=False) + "\n")
                update_manifest(shards_dir, fp.name, len(pending), args.model)
                print(f"[magpie] Wrote {fp.name} ({len(pending)} ex, cum {total})")
                pending = []
                shard_idx += 1

    if pending:
        fp = shards_dir / f"magpie_{shard_idx:04d}.jsonl"
        with open(fp, "w", encoding="utf-8") as fo:
            for e in pending:
                fo.write(json.dumps(e, ensure_ascii=False) + "\n")
        update_manifest(shards_dir, fp.name, len(pending), args.model)
        print(f"[magpie] Wrote final {fp.name} ({len(pending)} ex, cum {total})")


def update_manifest(shards_dir, shard_name, n_examples, teacher):
    mf = shards_dir / "manifest.json"
    data = {"shards": []}
    if mf.exists():
        try:
            data = json.loads(mf.read_text())
        except Exception:
            pass
    data["shards"].append({
        "file": shard_name,
        "examples": n_examples,
        "teacher": teacher,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    })
    data["total_examples"] = sum(s["examples"] for s in data["shards"])
    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    mf.write_text(json.dumps(data, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="unsloth/Qwen2.5-7B-Instruct-bnb-4bit")
    p.add_argument("--out-dir", default="shards")
    p.add_argument("--total", type=int, default=1000)
    p.add_argument("--shard-size", type=int, default=500)
    p.add_argument("--batch", type=int, default=4)
    p.add_argument("--max-new-tokens", type=int, default=512)
    p.add_argument("--seed", type=int, default=42)
    main(p.parse_args())
