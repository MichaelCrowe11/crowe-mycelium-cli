"""Modal-wrapped synthetic tool-use trace generation.

Mirrors scripts/modal_synth.py but emits training examples whose `output`
contains a full <tool_call>/<observation>/<final> trace so the student learns
the tool-calling protocol.

Usage:
    modal run scripts/synth_tooluse.py --total 1000 --shard-size 500 --yes
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import modal

# Make crowe_mycelium importable both locally and inside the Modal image.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
from crowe_mycelium.tools import TOOLS, tools_as_prompt_text  # noqa: E402

app = modal.App("crowe-mycelium-synth-tooluse")

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
    .add_local_python_source("crowe_mycelium")
)

TOOL_NAMES = [t["name"] for t in TOOLS]

PROMPT_TEMPLATE = """You are creating ONE tool-use training example for a mushroom-cultivation expert assistant.

{tools_block}

Produce a realistic interaction where the user asks something that requires calling the tool: **{tool_name}**.

The assistant's `output` MUST follow this exact structure on a single line (no code fences):
<thought>brief reasoning why this tool is needed</thought><tool_call>{{"name":"{tool_name}","arguments":{{...valid args...}}}}</tool_call><observation>{{...plausible JSON result the tool would return...}}</observation><final>natural-language answer to the user, grounded in the observation, 60-250 words</final>

Output ONLY this JSON object on a single line, nothing else:
{{"instruction": "<the user's question>", "output": "<the full thought/tool_call/observation/final trace>"}}"""


@app.function(
    image=image, gpu="A10G", timeout=3600,
    secrets=[modal.Secret.from_name("huggingface")],
)
def generate_shard(model: str, n_examples: int, batch_size: int = 4,
                   max_new_tokens: int = 1024, seed: int = 42) -> list:
    """Tool-use trace generation on a remote GPU."""
    import hashlib, json as _json, random, re
    import torch
    from unsloth import FastLanguageModel

    print(f"[tooluse-synth] Loading {model}...")
    m, tok = FastLanguageModel.from_pretrained(
        model_name=model, max_seq_length=2560, dtype=None, load_in_4bit=True,
    )
    FastLanguageModel.for_inference(m)
    tok.padding_side = "left"

    tools_block = tools_as_prompt_text()

    def parse_json_obj(text):
        mm = re.search(r'\{\s*"instruction"\s*:.*?"output"\s*:.*\}', text, re.S)
        if mm:
            try:
                obj = _json.loads(mm.group(0))
                return obj.get("instruction"), obj.get("output")
            except Exception:
                pass
        i_m = re.search(r'"instruction"\s*:\s*"((?:[^"\\]|\\.)*)"', text, re.S)
        o_m = re.search(r'"output"\s*:\s*"((?:[^"\\]|\\.)*)"', text, re.S)
        if i_m and o_m:
            try:
                return _json.loads(f'"{i_m.group(1)}"'), _json.loads(f'"{o_m.group(1)}"')
            except Exception:
                return i_m.group(1), o_m.group(1)
        return None, None

    def extract_tool_call(out):
        m = re.search(r"<tool_call>(.*?)</tool_call>", out, re.S)
        if not m: return None
        try:
            obj = _json.loads(m.group(1).strip())
            if not isinstance(obj, dict) or "name" not in obj or "arguments" not in obj:
                return None
            return obj
        except Exception:
            return None

    def extract_final(out):
        m = re.search(r"<final>(.*?)</final>", out, re.S)
        return m.group(1).strip() if m else ""

    def has_observation(out):
        return "<observation>" in out and "</observation>" in out

    def ok(instr, out):
        if not instr or not out: return False
        if len(instr) < 10 or len(instr) > 1500: return False
        if "<tool_call>" not in out: return False
        tc = extract_tool_call(out)
        if not tc: return False
        if tc["name"] not in TOOL_NAMES: return False
        if not has_observation(out): return False
        if len(extract_final(out)) < 50: return False
        return True

    rng = random.Random(seed)
    seen = set()
    out_examples = []
    attempts = 0
    max_attempts = n_examples * 5

    while len(out_examples) < n_examples and attempts < max_attempts:
        tool_names = [rng.choice(TOOL_NAMES) for _ in range(batch_size)]
        msgs_batch = [
            [{"role": "user", "content": PROMPT_TEMPLATE.format(
                tools_block=tools_block, tool_name=tn,
            )}]
            for tn in tool_names
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
            tc = extract_tool_call(resp)
            out_examples.append({
                "instruction": instr.strip(),
                "output": resp.strip(),
                "source": "tooluse",
                "tool": tc["name"],
                "teacher": model,
                "ts": datetime.utcnow().isoformat(timespec="seconds"),
            })
            if len(out_examples) >= n_examples:
                break
        print(f"[tooluse-synth] kept {len(out_examples)}/{n_examples} (attempted {attempts})")

    if attempts >= max_attempts:
        print(f"[tooluse-synth] WARNING: hit attempt cap at {max_attempts}.")
    return out_examples


@app.local_entrypoint()
def main(total: int = 1000, shard_size: int = 500,
         model: str = "unsloth/Qwen2.5-7B-Instruct-bnb-4bit",
         gpu: str = "A10G", batch_size: int = 4, parallel: int = 4,
         seed: int = 42, yes: bool = False):
    """Local entrypoint: invokes remote generation in parallel, saves shards locally."""
    repo_root = Path(__file__).resolve().parent.parent
    shards_dir = repo_root / "shards"
    shards_dir.mkdir(exist_ok=True)

    n_shards = (total + shard_size - 1) // shard_size
    existing = list(shards_dir.glob("tooluse_*.jsonl"))
    next_idx = (max((int(p.stem.split("_")[1]) for p in existing), default=-1) + 1)

    print(f"[tooluse-synth] {total} examples across {n_shards} shards, "
          f"starting at tooluse_{next_idx:04d}, parallel={parallel}")
    if not yes:
        print("[tooluse-synth] DRY RUN — re-run with --yes to actually generate.")
        return

    # Build per-shard args. Use .starmap for parallel fan-out across shards.
    args = []
    remaining = total
    for s in range(n_shards):
        n = min(shard_size, remaining)
        args.append((model, n, batch_size, 1024, seed + s))
        remaining -= n

    shard_idx = 0
    for examples in generate_shard.starmap(args):
        fp = shards_dir / f"tooluse_{next_idx + shard_idx:04d}.jsonl"
        with open(fp, "w", encoding="utf-8") as f:
            for ex in examples:
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")
        update_manifest(shards_dir, fp.name, len(examples), model, source="tooluse")
        print(f"[tooluse-synth] wrote {fp.name} ({len(examples)} ex)")
        shard_idx += 1

    print(f"[tooluse-synth] done. Next step: scripts/shard_and_push.ps1")


def update_manifest(shards_dir, shard_name, n_examples, teacher, source="tooluse"):
    mf = shards_dir / "manifest.json"
    data = {"shards": []}
    if mf.exists():
        try: data = json.loads(mf.read_text())
        except: pass
    data.setdefault("shards", []).append({
        "file": shard_name, "examples": n_examples, "teacher": teacher,
        "source": source,
        "created_at": datetime.utcnow().isoformat(timespec="seconds"),
    })
    data["total_examples"] = sum(s["examples"] for s in data["shards"])
    data["updated_at"] = datetime.utcnow().isoformat(timespec="seconds")
    mf.write_text(json.dumps(data, indent=2))
