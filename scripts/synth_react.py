"""Modal-wrapped ReAct multi-step trace synthesis.

Generates Thought/Action/Observation/Final Answer training traces for the
mycology agent. Tool names in Action: lines come from crowe_mycelium.tools.TOOLS
so the student learns to call the same surface the runtime exposes.

Observations are plausible-but-fabricated — downstream inference replaces them
with real tool results. The student only needs to learn the *pattern*.

Cost guide (Modal pricing, 2026):
  A10G  ~$1.10/hr  — ReAct chains are ~3-5x longer than single Q&A, so
                     expect ~1-2K traces/hr with Qwen2.5-7B
"""
import json
from datetime import datetime
from pathlib import Path

import modal

app = modal.App("crowe-mycelium-synth-react")

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

SCENARIO_SEEDS = [
    "diagnosing and halting a Trichoderma outbreak mid-flush in a commercial Lion's Mane room",
    "optimizing yield across the first three flushes of a Pleurotus ostreatus block run",
    "diagnosing a failed Hericium erinaceus cultivar that colonized but never pinned",
    "comparing Pleurotus ostreatus vs. Pleurotus eryngii for a specific climate and substrate",
    "planning a commercial scale-up from 50 to 500 blocks/week, including HVAC and labor",
    "identifying an unknown specimen using cap morphology, spore print, and habitat clues",
    "computing compound cost-per-pound across three substrate recipes with varying bran ratios",
    "rescuing a contaminated grain spawn jar that shows isolated green spots on day 9",
    "troubleshooting low BE (biological efficiency) on a previously-reliable cultivar",
    "evaluating whether to switch from masters mix to straw-based substrate for an oyster line",
    "diagnosing cobweb mold spreading across pinning Lion's Mane blocks",
    "computing CO2 ppm targets and FAE schedule for a new 200 sqft fruiting chamber",
]


# Template the teacher fills in. The {tools} placeholder is the runtime tool
# surface from crowe_mycelium.tools — keeps action names grounded.
PROMPT_TEMPLATE = """You are creating multi-step ReAct training data for a mycology expert agent.

AVAILABLE TOOLS (the agent can only call these):
{tools}

Write ONE realistic, multi-step scenario about: {scenario}

The output must follow this exact ReAct format with 2-5 Thought/Action/Observation steps before the Final Answer:

Thought: <reasoning about what to do first>
Action: <tool_name>(<args>)
Observation: <plausible tool result>
Thought: <reasoning about next step given the observation>
Action: <tool_name>(<args>)
Observation: <plausible tool result>
... (continue 2-5 steps total)
Final Answer: <synthesized expert recommendation drawing on the observations>

Rules:
- Every Action MUST call one of the tools listed above by its exact name.
- Observations should be plausible but fabricated (numbers, readings, lookups).
- Final Answer should be 100-400 words and actionable.
- The instruction should be a realistic question requiring at least 2 tool calls to answer well.

Output ONLY this JSON object on a single line, nothing else:
{{"instruction": "<the user question>", "output": "<the full Thought/Action/Observation/.../Final Answer text>"}}"""


@app.function(
    image=image, gpu="A10G", timeout=3600,
    secrets=[modal.Secret.from_name("huggingface")],
)
def generate_shard(model: str, n_examples: int, batch_size: int = 4,
                   max_new_tokens: int = 1536, seed: int = 42) -> list:
    """Prompt-based ReAct trace generation on a remote GPU."""
    import hashlib, json as _json, random, re
    import torch
    from unsloth import FastLanguageModel
    from crowe_mycelium.tools import tools_as_prompt_text

    print(f"[modal-react] Loading {model}...")
    m, tok = FastLanguageModel.from_pretrained(
        model_name=model, max_seq_length=4096, dtype=None, load_in_4bit=True,
    )
    FastLanguageModel.for_inference(m)
    tok.padding_side = "left"

    tools_text = tools_as_prompt_text()

    def ok(instr, out):
        if not instr or not out: return False
        if len(instr) < 20: return False
        if len(out) < 300: return False
        # Structural ReAct checks
        if len(re.findall(r"(?m)^\s*Thought:", out)) < 2: return False
        if len(re.findall(r"(?m)^\s*Action:", out)) < 2: return False
        if len(re.findall(r"(?m)^\s*Observation:", out)) < 1: return False
        if "Final Answer:" not in out: return False
        return True

    def parse_json_obj(text):
        m = re.search(r'\{\s*"instruction"\s*:.*?"output"\s*:.*?\}', text, re.S)
        if m:
            try:
                obj = _json.loads(m.group(0))
                return obj.get("instruction"), obj.get("output")
            except Exception:
                pass
        # Fallback: loose key extraction (tolerant of unescaped newlines in output)
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
    max_attempts = n_examples * 5  # ReAct is harder to format — give more headroom

    while len(out) < n_examples and attempts < max_attempts:
        scenarios = [rng.choice(SCENARIO_SEEDS) for _ in range(batch_size)]
        msgs_batch = [
            [{"role": "user", "content": PROMPT_TEMPLATE.format(tools=tools_text, scenario=s)}]
            for s in scenarios
        ]
        prompts = [tok.apply_chat_template(b, tokenize=False, add_generation_prompt=True) for b in msgs_batch]

        inputs = tok(prompts, return_tensors="pt", padding=True).to("cuda")
        prompt_len = inputs["input_ids"].shape[1]
        with torch.no_grad():
            gen = m.generate(
                **inputs, max_new_tokens=max_new_tokens,
                do_sample=True, temperature=0.8, top_p=0.95,
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
                "source": "react",
                "scenario": scenarios[i],
                "teacher": model,
                "ts": datetime.utcnow().isoformat(timespec="seconds"),
            })
            if len(out) >= n_examples:
                break
        print(f"[modal-react] kept {len(out)}/{n_examples} (attempted {attempts})")

    if attempts >= max_attempts:
        print(f"[modal-react] WARNING: hit attempt cap at {max_attempts}. Teacher may be malformatting ReAct.")
    return out


@app.local_entrypoint()
def main(total: int = 1000, shard_size: int = 500,
         model: str = "unsloth/Qwen2.5-7B-Instruct-bnb-4bit",
         gpu: str = "A10G", batch_size: int = 4, seed: int = 42,
         max_new_tokens: int = 1536, yes: bool = False):
    """Local entrypoint: invokes remote ReAct generation, saves shards locally."""
    repo_root = Path(__file__).resolve().parent.parent
    shards_dir = repo_root / "shards"
    shards_dir.mkdir(exist_ok=True)

    n_shards = (total + shard_size - 1) // shard_size
    existing = list(shards_dir.glob("react_*.jsonl"))
    next_idx = (max((int(p.stem.split("_")[1]) for p in existing), default=-1) + 1)

    print(f"[modal-react] plan: {total} traces across {n_shards} shards "
          f"(batch_size={batch_size}, max_new_tokens={max_new_tokens}), "
          f"starting at react_{next_idx:04d}")

    if not yes:
        print("[modal-react] DRY RUN — pass --yes to actually run on Modal.")
        return

    remaining = total
    for s in range(n_shards):
        n = min(shard_size, remaining)
        examples = generate_shard.remote(
            model=model, n_examples=n, batch_size=batch_size,
            max_new_tokens=max_new_tokens, seed=seed + s,
        )
        fp = shards_dir / f"react_{next_idx + s:04d}.jsonl"
        with open(fp, "w", encoding="utf-8") as f:
            for ex in examples:
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")
        update_manifest(shards_dir, fp.name, len(examples), model)
        print(f"[modal-react] wrote {fp.name} ({len(examples)} ex)")
        remaining -= n

    print(f"[modal-react] done. Next step: scripts/shard_and_push.ps1")


def update_manifest(shards_dir, shard_name, n_examples, teacher):
    mf = shards_dir / "manifest.json"
    data = {"shards": []}
    if mf.exists():
        try: data = json.loads(mf.read_text())
        except: pass
    data.setdefault("shards", []).append({
        "file": shard_name, "examples": n_examples, "teacher": teacher,
        "source": "react",
        "created_at": datetime.utcnow().isoformat(timespec="seconds"),
    })
    data["total_examples"] = sum(s["examples"] for s in data["shards"])
    data["updated_at"] = datetime.utcnow().isoformat(timespec="seconds")
    mf.write_text(json.dumps(data, indent=2))
