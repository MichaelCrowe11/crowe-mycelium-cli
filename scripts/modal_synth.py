"""Modal-wrapped Magpie synthetic data generation.

Runs the same Magpie technique as scripts/synth_magpie.py, but on a Modal-
provisioned A10 GPU instead of the local 3080. Pulls results back to local
shards/ directory and updates manifest.json.

Cost guide (Modal pricing, 2026):
  A10G  ~$1.10/hr  — generates ~3-5K examples/hr with Llama 3.1 8B
  A100  ~$2.00/hr  — generates ~8-12K examples/hr

Usage:
    modal run scripts/modal_synth.py --total 1000 --shard-size 500
    modal run scripts/modal_synth.py --total 100000 --shard-size 10000 --gpu A100
"""
import json
from datetime import datetime
from pathlib import Path

import modal

app = modal.App("crowe-mycelium-synth")

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

DOMAIN_SEEDS = [
    "mycology and mushroom cultivation",
    "Lion's Mane (Hericium erinaceus) commercial production",
    "psilocybin mushroom biology and pharmacology",
    "mycelium substrate sterilization and inoculation",
    "fruiting chamber humidity and CO2 management",
    "contamination identification (Trichoderma, bacterial blotch, cobweb)",
    "mushroom species identification by morphology",
    "bioactive compounds in medicinal fungi",
    "spawn production and grain colonization",
    "small-batch commercial mushroom farming economics",
]


PROMPT_TEMPLATE = """You are creating training data for a mushroom-cultivation expert assistant.

Write ONE realistic question a mushroom grower or mycology student might ask about: {topic}

Then write a detailed, accurate expert answer (200-800 words) drawing on real cultivation knowledge, biology, contamination handling, or chemistry as relevant.

Output ONLY this JSON object on a single line, nothing else:
{{"instruction": "<the question>", "output": "<the detailed expert answer>"}}"""


@app.function(
    image=image, gpu="A10G", timeout=3600,
    secrets=[modal.Secret.from_name("huggingface")],
)
def generate_shard(model: str, n_examples: int, batch_size: int = 8,
                   max_new_tokens: int = 1024, seed: int = 42) -> list:
    """Prompt-based domain-focused instruction generation on a remote GPU."""
    import hashlib, json as _json, random, re
    import torch
    from unsloth import FastLanguageModel

    print(f"[modal-synth] Loading {model}...")
    m, tok = FastLanguageModel.from_pretrained(
        model_name=model, max_seq_length=2048, dtype=None, load_in_4bit=True,
    )
    FastLanguageModel.for_inference(m)
    tok.padding_side = "left"

    def ok(i, o):
        if not i or not o: return False
        if len(i) < 10 or len(o) < 80: return False
        if len(i) > 1500 or len(o) > 5000: return False
        if i.lower().startswith(("i can't", "i'm sorry", "as an ai")): return False
        return True

    def parse_json_obj(text):
        # Try strict JSON first
        m = re.search(r'\{\s*"instruction"\s*:.*?"output"\s*:.*?\}', text, re.S)
        if m:
            try:
                obj = _json.loads(m.group(0))
                return obj.get("instruction"), obj.get("output")
            except Exception:
                pass
        # Fallback: loose key extraction
        i_m = re.search(r'"instruction"\s*:\s*"((?:[^"\\]|\\.)*)"', text, re.S)
        o_m = re.search(r'"output"\s*:\s*"((?:[^"\\]|\\.)*)"', text, re.S)
        if i_m and o_m:
            try:
                instr = _json.loads(f'"{i_m.group(1)}"')
                resp = _json.loads(f'"{o_m.group(1)}"')
                return instr, resp
            except Exception:
                return i_m.group(1), o_m.group(1)
        return None, None

    rng = random.Random(seed)
    seen = set()
    out = []
    attempts = 0
    max_attempts = n_examples * 4  # cap so we don't burn forever on a bad teacher

    while len(out) < n_examples and attempts < max_attempts:
        topics = [rng.choice(DOMAIN_SEEDS) for _ in range(batch_size)]
        msgs_batch = [
            [{"role": "user", "content": PROMPT_TEMPLATE.format(topic=t)}]
            for t in topics
        ]
        prompts = [tok.apply_chat_template(b, tokenize=False, add_generation_prompt=True) for b in msgs_batch]

        inputs = tok(prompts, return_tensors="pt", padding=True).to("cuda")
        prompt_len = inputs["input_ids"].shape[1]
        with torch.no_grad():
            gen = m.generate(
                **inputs, max_new_tokens=max_new_tokens,
                do_sample=True, temperature=0.85, top_p=0.95,
                pad_token_id=tok.eos_token_id,
            )
        for i in range(gen.shape[0]):
            attempts += 1
            new_tokens = gen[i][prompt_len:]
            text = tok.decode(new_tokens, skip_special_tokens=True)
            instr, resp = parse_json_obj(text)
            if not ok(instr, resp):
                continue
            h = hashlib.md5((instr + "||" + resp).encode()).hexdigest()
            if h in seen:
                continue
            seen.add(h)
            out.append({
                "instruction": instr.strip(),
                "output": resp.strip(),
                "source": "synth-prompt",
                "topic": topics[i],
                "teacher": model,
                "ts": datetime.utcnow().isoformat(timespec="seconds"),
            })
            if len(out) >= n_examples:
                break
        print(f"[modal-synth] kept {len(out)}/{n_examples} (attempted {attempts})")

    if attempts >= max_attempts:
        print(f"[modal-synth] WARNING: hit attempt cap at {max_attempts}. Teacher may be malformatting JSON.")
    return out


@app.local_entrypoint()
def main(total: int = 1000, shard_size: int = 500,
         model: str = "unsloth/Qwen2.5-7B-Instruct-bnb-4bit",
         gpu: str = "A10G", batch_size: int = 8, seed: int = 42):
    """Local entrypoint: invokes remote generation, saves shards locally."""
    repo_root = Path(__file__).resolve().parent.parent
    shards_dir = repo_root / "shards"
    shards_dir.mkdir(exist_ok=True)

    n_shards = (total + shard_size - 1) // shard_size
    existing = list(shards_dir.glob("magpie_*.jsonl"))
    next_idx = (max((int(p.stem.split("_")[1]) for p in existing), default=-1) + 1)

    print(f"[modal-synth] generating {total} examples across {n_shards} shards, "
          f"starting at magpie_{next_idx:04d}")

    remaining = total
    for s in range(n_shards):
        n = min(shard_size, remaining)
        examples = generate_shard.remote(
            model=model, n_examples=n, batch_size=batch_size, seed=seed + s,
        )
        fp = shards_dir / f"magpie_{next_idx + s:04d}.jsonl"
        with open(fp, "w", encoding="utf-8") as f:
            for ex in examples:
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")
        update_manifest(shards_dir, fp.name, len(examples), model)
        print(f"[modal-synth] wrote {fp.name} ({len(examples)} ex)")
        remaining -= n

    print(f"[modal-synth] done. Next step: scripts/shard_and_push.ps1")


def update_manifest(shards_dir, shard_name, n_examples, teacher):
    mf = shards_dir / "manifest.json"
    data = {"shards": []}
    if mf.exists():
        try: data = json.loads(mf.read_text())
        except: pass
    data.setdefault("shards", []).append({
        "file": shard_name, "examples": n_examples, "teacher": teacher,
        "created_at": datetime.utcnow().isoformat(timespec="seconds"),
    })
    data["total_examples"] = sum(s["examples"] for s in data["shards"])
    data["updated_at"] = datetime.utcnow().isoformat(timespec="seconds")
    mf.write_text(json.dumps(data, indent=2))
