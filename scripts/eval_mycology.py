"""Crowe Logic mycology eval harness.

Runs eval/questions.jsonl against a model (optionally with a LoRA adapter).
MCQ questions are auto-scored. Open-ended questions can be LLM-as-judge scored
or left for manual review.

Usage:
    python scripts/eval_mycology.py
    python scripts/eval_mycology.py --adapter runs/unsloth-latest/final
    python scripts/eval_mycology.py --adapter runs/unsloth-latest/final --use-judge
"""
import argparse, json
from datetime import datetime
from pathlib import Path

import torch
from unsloth import FastLanguageModel

REPO_ROOT = Path(__file__).resolve().parent.parent
QUESTIONS = REPO_ROOT / "eval" / "questions.jsonl"
RESULTS_DIR = REPO_ROOT / "eval" / "results"

_loaded = {}


def get_model(name, adapter):
    key = (name, adapter)
    if key in _loaded:
        return _loaded[key]
    model, tok = FastLanguageModel.from_pretrained(
        model_name=name, max_seq_length=2048, load_in_4bit=True,
    )
    if adapter:
        model.load_adapter(adapter)
    FastLanguageModel.for_inference(model)
    _loaded[key] = (model, tok)
    return model, tok


def query(name, adapter, prompt, max_new_tokens=300):
    model, tok = get_model(name, adapter)
    msgs = [{"role": "user", "content": prompt}]
    inputs = tok.apply_chat_template(
        msgs, return_tensors="pt", add_generation_prompt=True,
    ).to("cuda")
    with torch.no_grad():
        out = model.generate(
            inputs, max_new_tokens=max_new_tokens, do_sample=False,
            pad_token_id=tok.eos_token_id,
        )
    return tok.decode(out[0][inputs.shape[1]:], skip_special_tokens=True).strip()


def grade_mcq(answer, expected):
    letter = next((c for c in answer.strip().upper() if c in "ABCDE"), None)
    return 1.0 if letter == expected.upper() else 0.0


def grade_open_with_judge(question, reference, candidate, judge_model):
    prompt = (
        f"You are grading a domain-expert answer.\n\n"
        f"Question: {question}\n\n"
        f"Reference answer: {reference}\n\n"
        f"Candidate answer: {candidate}\n\n"
        f"Grade 0-10 for correctness and completeness. Reply with ONLY the number."
    )
    resp = query(judge_model, None, prompt, max_new_tokens=10)
    try:
        score = float(resp.strip().split()[0])
        return max(0.0, min(10.0, score)) / 10.0
    except Exception:
        return None


def main(args):
    questions = [json.loads(l) for l in open(QUESTIONS, encoding="utf-8") if l.strip()]
    print(f"[eval] {len(questions)} questions")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results = []

    for q in questions:
        ans = query(args.model, args.adapter, q["question"])
        if q["type"] == "mcq":
            score = grade_mcq(ans, q["expected"])
        elif args.use_judge:
            score = grade_open_with_judge(
                q["question"], q["expected"], ans, args.judge_model,
            )
        else:
            score = None
        results.append({**q, "answer": ans, "score": score})
        tag = f"{score:.2f}" if score is not None else "  - "
        print(f"  [{q['category']:12s}] {tag}  {q['question'][:55]}")

    scored = [r for r in results if r["score"] is not None]
    avg = sum(r["score"] for r in scored) / len(scored) if scored else 0.0

    by_cat = {}
    for r in scored:
        by_cat.setdefault(r["category"], []).append(r["score"])
    by_cat = {c: sum(v) / len(v) for c, v in by_cat.items()}

    out = {
        "model": args.model,
        "adapter": args.adapter,
        "judge_model": args.judge_model if args.use_judge else None,
        "n_questions": len(questions),
        "n_scored": len(scored),
        "avg_score": avg,
        "by_category": by_cat,
        "completed_at": datetime.now().isoformat(timespec="seconds"),
        "results": results,
    }
    stem = (args.adapter or args.model).replace("/", "_").replace("\\", "_")
    fp = RESULTS_DIR / f"{stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    fp.write_text(json.dumps(out, indent=2))
    print(f"\n[eval] avg = {avg:.3f}  ({len(scored)}/{len(questions)} auto-scored)")
    for c, s in by_cat.items():
        print(f"       {c:14s} {s:.3f}")
    print(f"[eval] wrote {fp}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="unsloth/gemma-3-4b-it-bnb-4bit")
    p.add_argument("--adapter", default=None, help="path to LoRA adapter directory")
    p.add_argument("--use-judge", action="store_true")
    p.add_argument("--judge-model", default="unsloth/Llama-3.1-8B-Instruct-bnb-4bit")
    main(p.parse_args())
