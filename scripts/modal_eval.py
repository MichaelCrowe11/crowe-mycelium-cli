"""Modal-wrapped eval: scores a base model and/or a LoRA adapter against
eval/questions.jsonl. Adapters live on the crowe-mycelium-runs Volume.

Usage:
    modal run scripts/modal_eval.py                                        # baseline
    modal run scripts/modal_eval.py --adapter-run unsloth-20260519-004814  # base+adapter
    modal run scripts/modal_eval.py --adapter-run <run> --use-judge        # LLM-judge open Qs
    modal run scripts/modal_eval.py --compare unsloth-20260519-004814      # base AND adapter side-by-side
"""
import json
from datetime import datetime
from pathlib import Path

import modal

app = modal.App("crowe-mycelium-eval")
runs_volume = modal.Volume.from_name("crowe-mycelium-runs", create_if_missing=True)

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
    image=image, gpu="A10G", timeout=3600,
    volumes={"/runs": runs_volume},
    secrets=[modal.Secret.from_name("huggingface")],
)
def evaluate(model: str, adapter_run: str | None, questions: list,
             max_new_tokens: int = 400, use_judge: bool = False,
             judge_model: str = "unsloth/Qwen2.5-7B-Instruct-bnb-4bit") -> dict:
    import re, torch
    from unsloth import FastLanguageModel

    print(f"[eval] loading base model {model}")
    m, tok = FastLanguageModel.from_pretrained(
        model_name=model, max_seq_length=2048, load_in_4bit=True,
    )
    if adapter_run:
        adapter_path = f"/runs/{adapter_run}/final"
        print(f"[eval] loading adapter from {adapter_path}")
        m.load_adapter(adapter_path)
    FastLanguageModel.for_inference(m)

    # Gemma 3 wraps the text tokenizer in a multimodal processor — unwrap it
    text_tok = getattr(tok, "tokenizer", tok)

    def ask(prompt: str, max_new: int = max_new_tokens) -> str:
        msgs = [{"role": "user", "content": prompt}]
        rendered = text_tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        enc = text_tok(rendered, return_tensors="pt")
        input_ids = enc["input_ids"].to("cuda")
        attention_mask = enc.get("attention_mask")
        if attention_mask is not None:
            attention_mask = attention_mask.to("cuda")
        prompt_len = input_ids.shape[1]
        with torch.no_grad():
            out = m.generate(
                input_ids=input_ids, attention_mask=attention_mask,
                max_new_tokens=max_new, do_sample=False,
                pad_token_id=text_tok.eos_token_id,
            )
        return text_tok.decode(out[0][prompt_len:], skip_special_tokens=True).strip()

    def grade_mcq(ans, expected):
        letter = next((c for c in ans.strip().upper() if c in "ABCDE"), None)
        return 1.0 if letter == expected.upper() else 0.0

    judge_cache = {"loaded": False}

    def grade_open(q, reference, candidate):
        if not use_judge:
            return None
        # Lazy-load judge model on same GPU after main model done (or use same model)
        prompt = (
            "You are grading a domain-expert answer.\n\n"
            f"Question: {q}\n\n"
            f"Reference answer: {reference}\n\n"
            f"Candidate answer: {candidate}\n\n"
            "Grade 0-10 for correctness and completeness. Reply with ONLY the number."
        )
        resp = ask(prompt, max_new=10)
        try:
            return max(0.0, min(10.0, float(resp.strip().split()[0]))) / 10.0
        except Exception:
            return None

    results = []
    for q in questions:
        ans = ask(q["question"])
        if q["type"] == "mcq":
            score = grade_mcq(ans, q["expected"])
        else:
            score = grade_open(q["question"], q["expected"], ans)
        results.append({**q, "answer": ans, "score": score})
        tag = f"{score:.2f}" if score is not None else "  - "
        print(f"  [{q['category']:12s}] {tag}  {q['question'][:60]}")

    scored = [r["score"] for r in results if r["score"] is not None]
    avg = sum(scored) / len(scored) if scored else 0.0

    by_cat = {}
    for r in results:
        if r["score"] is None:
            continue
        by_cat.setdefault(r["category"], []).append(r["score"])
    by_cat = {c: sum(v) / len(v) for c, v in by_cat.items()}

    return {
        "model": model,
        "adapter_run": adapter_run,
        "use_judge": use_judge,
        "n_questions": len(results),
        "n_scored": len(scored),
        "avg_score": avg,
        "by_category": by_cat,
        "results": results,
        "completed_at": datetime.utcnow().isoformat(timespec="seconds"),
    }


@app.local_entrypoint()
def main(
    model: str = "unsloth/gemma-4-E4B-it-unsloth-bnb-4bit",
    adapter_run: str = "",
    compare: str = "",
    use_judge: bool = False,
):
    """Run eval. With --compare RUN, run twice (base and base+adapter) and diff scores."""
    repo_root = Path(__file__).resolve().parent.parent
    qs = [json.loads(l) for l in open(repo_root / "eval" / "questions.jsonl", encoding="utf-8") if l.strip()]
    print(f"[eval] {len(qs)} questions")

    results_dir = repo_root / "eval" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    if compare:
        # Run baseline first, then with adapter, then print diff
        print("[eval] Running BASELINE (no adapter)...")
        base = evaluate.remote(model=model, adapter_run=None, questions=qs, use_judge=use_judge)
        print(f"[eval] baseline avg: {base['avg_score']:.3f}")
        print("[eval] Running WITH ADAPTER...")
        adapted = evaluate.remote(model=model, adapter_run=compare, questions=qs, use_judge=use_judge)
        print(f"[eval] adapter avg: {adapted['avg_score']:.3f}")

        delta = adapted["avg_score"] - base["avg_score"]
        print(f"\n=== COMPARISON ===")
        print(f"Base    : {base['avg_score']:.3f}")
        print(f"Adapter : {adapted['avg_score']:.3f}")
        print(f"Delta   : {'+' if delta >= 0 else ''}{delta:.3f}")
        print(f"\nBy category:")
        for c in sorted(set(list(base['by_category']) + list(adapted['by_category']))):
            b = base['by_category'].get(c, 0.0)
            a = adapted['by_category'].get(c, 0.0)
            d = a - b
            print(f"  {c:14s} base={b:.3f}  adapter={a:.3f}  Δ={'+' if d>=0 else ''}{d:.3f}")

        out = {"comparison": True, "base": base, "adapter": adapted,
               "delta_avg": delta, "completed_at": datetime.utcnow().isoformat(timespec="seconds")}
        stem = f"compare_{compare.replace('/','_')}"
    else:
        out = evaluate.remote(model=model, adapter_run=(adapter_run or None),
                              questions=qs, use_judge=use_judge)
        print(f"\n[eval] avg = {out['avg_score']:.3f} ({out['n_scored']}/{out['n_questions']} auto-scored)")
        for c, s in out["by_category"].items():
            print(f"  {c:14s} {s:.3f}")
        stem = (adapter_run or model).replace("/", "_").replace("\\", "_")

    fp = results_dir / f"{stem}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    fp.write_text(json.dumps(out, indent=2))
    print(f"[eval] wrote {fp}")
