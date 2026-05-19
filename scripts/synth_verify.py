"""Modal-wrapped self-verification synthetic data generation.

Teaches the student to PAUSE-CHECK-REVISE: each example contains a plausible-
but-flawed <first_draft>, a self-<verify> critique, and a corrected <final>.
Trains against the confident-hallucination failure mode observed in base
Gemma 3 4B / Gemma 4 E4B (e.g. "fungi use the Calvin cycle", "wheat straw is
best for Lion's Mane").

Usage:
    modal run scripts/synth_verify.py --total 1000 --shard-size 500
    modal run scripts/synth_verify.py --total 20000 --shard-size 2000 --yes
"""
import json
from datetime import datetime
from pathlib import Path

import modal

app = modal.App("crowe-mycelium-synth-verify")

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

# Error categories typical of small generalist models on mycology.
ERROR_CATEGORIES = [
    "fungi photosynthesize / use the Calvin cycle / contain chlorophyll",
    "wrong fruiting or incubation temperature (off by 5-15C)",
    "wrong substrate recommendation (e.g. wheat straw for Lion's Mane)",
    "confusing Hericium species (erinaceus vs coralloides vs americanum)",
    "wrong toxin attribution (muscarine vs amatoxin vs ibotenic acid)",
    "wrong pharmacology (psilocybin vs psilocin as active form; MAO claims)",
    "wrong taxonomy (calling a polypore a gilled mushroom, or vice versa)",
    "wrong biological efficiency math (BE formula or interpretation)",
    "wrong compound location (hericenones in mycelium vs erinacines in fruit body)",
    "wrong contamination ID (Trichoderma vs Penicillium color/morphology)",
    "conflating mushrooms with plants (roots, leaves, seeds, transpiration)",
    "wrong sterilization parameters (time, temp, pressure for PC vs tyndallization)",
]


PROMPT_TEMPLATE = """You are creating training data that teaches a small language model to CATCH ITS OWN MISTAKES before answering mycology questions.

Generate ONE training example with four parts:

(a) A realistic question a mushroom grower or mycology student might ask.
(b) A FIRST DRAFT answer that sounds confident but contains 1-2 SPECIFIC factual errors of this type: {error_cat}. The error must be concrete (a wrong number, wrong species, wrong compound, wrong mechanism) -- not vague.
(c) A SELF-CRITIQUE that explicitly identifies the error in (b), names what was wrong, and cites the correct fact.
(d) A REVISED final answer (100-500 words) that is accurate and complete.

The first draft must be plausible enough that a non-expert would believe it. The critique must point to a SPECIFIC error, not a generic "let me reconsider".

Output ONLY this JSON object on a single line, nothing else:
{{"instruction": "<the question>", "first_draft": "<the flawed first answer>", "verify": "<self-critique naming the specific error and correct fact>", "final": "<the corrected accurate answer>"}}"""


@app.function(
    image=image, gpu="A10G", timeout=3600,
    secrets=[modal.Secret.from_name("huggingface")],
)
def generate_shard(model: str, n_examples: int, batch_size: int = 4,
                   max_new_tokens: int = 1200, seed: int = 42) -> list:
    """Remote: generate self-verification traces on an A10G."""
    import hashlib, json as _json, random, re
    import torch
    from unsloth import FastLanguageModel

    print(f"[synth-verify] Loading {model}...")
    m, tok = FastLanguageModel.from_pretrained(
        model_name=model, max_seq_length=4096, dtype=None, load_in_4bit=True,
    )
    FastLanguageModel.for_inference(m)
    tok.padding_side = "left"

    def parse_json_obj(text):
        # Strict-ish: find the first balanced-looking object containing our keys.
        m = re.search(
            r'\{\s*"instruction"\s*:.*?"first_draft"\s*:.*?"verify"\s*:.*?"final"\s*:.*?\}',
            text, re.S,
        )
        if m:
            try:
                obj = _json.loads(m.group(0))
                return (obj.get("instruction"), obj.get("first_draft"),
                        obj.get("verify"), obj.get("final"))
            except Exception:
                pass
        # Loose fallback: extract each key independently.
        keys = ("instruction", "first_draft", "verify", "final")
        vals = []
        for k in keys:
            km = re.search(rf'"{k}"\s*:\s*"((?:[^"\\]|\\.)*)"', text, re.S)
            if not km:
                return None, None, None, None
            try:
                vals.append(_json.loads(f'"{km.group(1)}"'))
            except Exception:
                vals.append(km.group(1))
        return tuple(vals)

    def assemble(first_draft, verify, final):
        return (
            f"<first_draft>Initial response: {first_draft.strip()}</first_draft>\n"
            f"<verify>Let me check this. {verify.strip()}</verify>\n"
            f"<final>Revised answer: {final.strip()}</final>"
        )

    def ok(instr, fd, vf, fn):
        if not all((instr, fd, vf, fn)): return False
        if len(instr) < 10 or len(instr) > 1500: return False
        if len(fd) < 60 or len(fd) > 3000: return False
        if len(vf) < 30 or len(vf) > 3000: return False
        if len(fn) < 100 or len(fn) > 5000: return False
        if instr.lower().startswith(("i can't", "i'm sorry", "as an ai")): return False
        # Critique must look like a critique, not a vague hedge.
        vl = vf.lower()
        cues = ("incorrect", "wrong", "error", "actually", "in fact",
                "should be", "rather than", "instead", "mistake", "not ", "but ")
        if not any(c in vl for c in cues): return False
        return True

    rng = random.Random(seed)
    seen = set()
    out = []
    attempts = 0
    max_attempts = n_examples * 5  # verification traces are harder to elicit

    while len(out) < n_examples and attempts < max_attempts:
        cats = [rng.choice(ERROR_CATEGORIES) for _ in range(batch_size)]
        msgs_batch = [
            [{"role": "user", "content": PROMPT_TEMPLATE.format(error_cat=c)}]
            for c in cats
        ]
        prompts = [tok.apply_chat_template(b, tokenize=False, add_generation_prompt=True)
                   for b in msgs_batch]

        inputs = tok(prompts, return_tensors="pt", padding=True).to("cuda")
        prompt_len = inputs["input_ids"].shape[1]
        with torch.no_grad():
            gen = m.generate(
                **inputs, max_new_tokens=max_new_tokens,
                do_sample=True, temperature=0.9, top_p=0.95,
                pad_token_id=tok.eos_token_id,
            )
        for i in range(gen.shape[0]):
            attempts += 1
            new_tokens = gen[i][prompt_len:]
            text = tok.decode(new_tokens, skip_special_tokens=True)
            instr, fd, vf, fn = parse_json_obj(text)
            if not ok(instr, fd, vf, fn):
                continue
            output = assemble(fd, vf, fn)
            # Final filter: must contain all three tags (assemble guarantees, but
            # belt-and-suspenders if assemble logic ever changes).
            if not ("<first_draft>" in output and "<verify>" in output
                    and "<final>" in output):
                continue
            h = hashlib.md5((instr + "||" + output).encode()).hexdigest()
            if h in seen:
                continue
            seen.add(h)
            out.append({
                "instruction": instr.strip(),
                "output": output,
                "source": "verify",
                "error_category": cats[i],
                "teacher": model,
                "ts": datetime.utcnow().isoformat(timespec="seconds"),
            })
            if len(out) >= n_examples:
                break
        print(f"[synth-verify] kept {len(out)}/{n_examples} (attempted {attempts})")

    if attempts >= max_attempts:
        print(f"[synth-verify] WARNING: hit attempt cap at {max_attempts}. "
              f"Teacher may be malformatting JSON or refusing the critique frame.")
    return out


@app.local_entrypoint()
def main(total: int = 1000, shard_size: int = 500,
         model: str = "unsloth/Qwen2.5-7B-Instruct-bnb-4bit",
         batch_size: int = 4, seed: int = 42,
         max_new_tokens: int = 1200, yes: bool = False):
    """Local entrypoint: invoke remote generation, save verify_NNNN.jsonl shards."""
    repo_root = Path(__file__).resolve().parent.parent
    shards_dir = repo_root / "shards"
    shards_dir.mkdir(exist_ok=True)

    n_shards = (total + shard_size - 1) // shard_size
    existing = list(shards_dir.glob("verify_*.jsonl"))
    next_idx = (max((int(p.stem.split("_")[1]) for p in existing), default=-1) + 1)

    print(f"[synth-verify] plan: {total} examples across {n_shards} shards, "
          f"starting at verify_{next_idx:04d}, teacher={model}")
    if not yes:
        resp = input("[synth-verify] proceed? [y/N] ").strip().lower()
        if resp not in ("y", "yes"):
            print("[synth-verify] aborted.")
            return

    remaining = total
    for s in range(n_shards):
        n = min(shard_size, remaining)
        examples = generate_shard.remote(
            model=model, n_examples=n, batch_size=batch_size,
            max_new_tokens=max_new_tokens, seed=seed + s,
        )
        fp = shards_dir / f"verify_{next_idx + s:04d}.jsonl"
        with open(fp, "w", encoding="utf-8") as f:
            for ex in examples:
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")
        update_manifest(shards_dir, fp.name, len(examples), model)
        print(f"[synth-verify] wrote {fp.name} ({len(examples)} ex)")
        remaining -= n

    print(f"[synth-verify] done. Next step: scripts/shard_and_push.ps1")


def update_manifest(shards_dir, shard_name, n_examples, teacher):
    mf = shards_dir / "manifest.json"
    data = {"shards": []}
    if mf.exists():
        try: data = json.loads(mf.read_text())
        except: pass
    data.setdefault("shards", []).append({
        "file": shard_name, "examples": n_examples, "teacher": teacher,
        "source": "verify",
        "created_at": datetime.utcnow().isoformat(timespec="seconds"),
    })
    data["total_examples"] = sum(s["examples"] for s in data["shards"])
    data["updated_at"] = datetime.utcnow().isoformat(timespec="seconds")
    mf.write_text(json.dumps(data, indent=2))
