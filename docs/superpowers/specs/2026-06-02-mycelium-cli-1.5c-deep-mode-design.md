# Crowe Mycelium CLI 1.5c — Deep Mode (web-aware ensemble)

**Date:** 2026-06-02
**Status:** Design approved, ready for implementation planning
**Scope:** Phase 1.5c only. Composes 1.5a (streaming backend/renderer) + 1.5b (web search) into an ensemble-reasoning command. Sibling of the shipped 1.5b; the last of the 1.5x line before P2 RAG.

---

## 1. Background & motivation

The model is a 4B Gemma fine-tune — strong on cultivation but, like any small model, prone to a confident wrong answer on a hard call (a tricky contamination differential, a stalled-pinning diagnosis). The fix is **ensemble + judge**: draw several independent answers and reconcile them, surfacing agreement as confidence. This mirrors the DeepParallel pattern, applied to a single model via temperature-diverse self-consistency.

1.5c adds `/deep` — the single most thorough thing the CLI can do. It **composes** the prior phases: optionally grounds in web search (1.5b), samples N answers (1.5a streaming backend), and reconciles them with a judge pass. It reinvents nothing.

## 2. Decisions captured (from brainstorming)

- **`/deep` = web-aware knowledge ensemble.** Default is a knowledge ensemble (hard diagnoses); it **auto-grounds in web search when the query needs live info** (`needs_live_info` from 1.5b). `/deep web <q>` forces grounding regardless.
- **N=3 samples** at a higher temperature (0.8) for diversity, over the model's own knowledge (or the grounded context). Env-overridable.
- **Judge pass** = one final model call (low temp 0.3) that reconciles the N candidates into one best answer + an agreement/confidence note.
- **Samples are hidden** — only the reconciled answer renders (cleaner). Progress shows via a labeled crest (`deliberating · sample 2/3`).
- **Sequential sampling** (~30-40s on the warm L4) — acceptable for an explicit `/deep`; live progress means it's never a silent wait.
- **Graceful degrade** — if a sample errors, judge over whatever succeeded; if all fail, error. If grounding search yields nothing, ensemble over knowledge.
- **YAGNI:** no parallel sampling, no varied-angle prompts, no multi-model judge, no `/deep` auto-trigger (it's always explicit).

## 3. Architecture / new + changed surfaces

```
crowe_mycelium/
  deep.py                  # NEW — collect_sample, build_judge_messages, run_deep (orchestrator)
  render/thinking.py       # MODIFY — crest_frame(tick, elapsed, label="thinking")
  render/base.py           # MODIFY — abstract deliberate(label, fn)
  render/rich.py           # MODIFY — deliberate(): labeled crest while fn runs, returns fn()
  render/plain.py          # MODIFY — deliberate(): run fn silently (label to stderr)
  session.py               # MODIFY — dispatch "/deep <query>" (and "/deep web <query>")
  cli.py                   # MODIFY — `deep` action → deep.run_deep(...)
```

### 3.1 `deep.py`
- `collect_sample(backend, messages, temperature) -> str` — consumes `backend.stream_chat(messages, temperature)` to a full string (`"".join(...)`). Pure given an injected backend.
- `build_judge_messages(system, query, candidates) -> list[dict]` — builds the reconciliation prompt:
  - system message = the model's system prompt (unchanged).
  - user message = the original question + the N numbered candidate answers + an instruction: *"Reconcile these N independent answers into one best answer. Where they agree, state it confidently; where they diverge, choose the most evidence-grounded option and flag the uncertainty. End with one line: `agreement: <k>/<n> aligned[ — diverged on <topic>]`."*
- `run_deep(query, backend, system, history, settings, renderer, build_messages, *, force_web=False) -> None` — the orchestrator:
  1. **Ground:** if `force_web or needs_live_info(query)` → `results = build_searcher(settings).search(query)` (catch `NotImplementedError` → `results = []`); `user_turn = format_grounding(query, results) if results else query`.
  2. **Sample:** `n = deep_samples()`, `temp = deep_temperature()`; for `i in range(n)`: `sample = renderer.deliberate(f"deliberating · sample {i+1}/{n}", lambda: collect_sample(backend, build_messages(history, system, user_turn), temp))`; collect non-empty samples.
  3. **Degrade:** if no samples → `renderer.error("deep mode: no answers produced.")`, return.
  4. **Judge:** `judge_messages = build_judge_messages(system, query, candidates)`; `reply = renderer.render_stream(backend.stream_chat(judge_messages, 0.3))`.
  5. **Render extras:** if `results` → `console.print(f"[grey50]{sources_text(results)}[/]")`.
  6. **History:** append `("user", query)` + `("assistant", reply)` (store the original query, not the grounded turn).
- Config helpers: `deep_samples()` reads `CROWE_MYCELIUM_DEEP_SAMPLES` (default 3, min 2); `deep_temperature()` reads `CROWE_MYCELIUM_DEEP_TEMPERATURE` (default 0.8).

`build_messages` is passed in from `cli.py` (its existing `_build_messages`) so `deep.py` never imports `cli` (no circular import).

### 3.2 Renderer `deliberate(label, fn)`
- `render/thinking.py`: `crest_frame(tick, elapsed, label="thinking")` — the hardcoded "thinking" becomes the `label` param (default keeps existing behavior + tests).
- `render/base.py`: add abstract `deliberate(self, label: str, fn) -> str`.
- `render/rich.py`: `deliberate` runs `fn` in a background thread (like `render_stream`'s crest loop) showing `crest_frame(tick, elapsed, label=label)`; returns `fn()`'s result; re-raises a thread error after the Live closes. No markdown print (samples are hidden).
- `render/plain.py`: `deliberate` = print the label to stderr once, then `return fn()` (no animation).

### 3.3 `session.py`
- Add to `dispatch_slash`: a line starting with `/deep` → `SlashResult(True, "deep", <rest>)`. The CLI parses `web ` off the front of the arg to set `force_web`.

### 3.4 `cli.py`
- New `deep` slash branch: parse `arg`; if it starts with `web `, `force_web=True` and strip it; if the remaining query is empty → `branding.info("usage: /deep <question>  (or /deep web <question>)")`; else `deep.run_deep(query, backend, system, history, settings, renderer, _build_messages, force_web=force_web)` + `branding.turn_separator()`.

## 4. Error handling

- A sample raising mid-stream → caught in `collect_sample`'s caller (the `deliberate` thread surfaces it); `run_deep` skips that sample and continues. If ALL samples fail → `renderer.error(...)`, return (no judge call).
- Judge call raising → `renderer.error(str(e))`, return (caught in `run_deep`).
- Grounding search failing / `NotImplementedError` / empty → ungrounded ensemble (no crash).

## 5. Testing (TDD)

- **`collect_sample`** — injected fake backend yielding `["a", "b"]` → returns `"ab"`.
- **`build_judge_messages`** — contains all N candidates (numbered), the original query, the reconcile instruction, and the `agreement:` line directive; system message preserved.
- **`run_deep` happy path** — fake backend that returns N distinct samples then a judge answer; fake renderer recording `deliberate`/`render_stream` calls; assert N `deliberate` calls + 1 `render_stream` (judge) + history gets `(user, query)`/`(assistant, judge_reply)`. Inject `build_messages` + a fake searcher via env (`CROWE_MYCELIUM_SEARCH_PROVIDER` unset → DDG, but no network: pass a query that isn't `needs_live_info` so no search runs).
- **`run_deep` grounded path** — a `needs_live_info` query + an injected searcher returning results → assert grounding applied (the messages built include the grounding block) and `sources_text` rendered.
- **`run_deep` degrade** — all samples empty/raise → `renderer.error` called, no judge call.
- **`deep_samples`/`deep_temperature`** — env overrides + defaults + floors.
- **`crest_frame(label=...)`** — custom label appears; default still says "thinking".
- **dispatch** — `/deep how do I diagnose green mold` → `("deep", "how do I diagnose green mold")`; `/deep web oyster prices` → arg `"web oyster prices"`; bare `/deep` → empty arg.

To keep `run_deep` testable, the searcher is obtained via `build_searcher(settings)` — tests pass a query that doesn't trigger `needs_live_info` (knowledge path, no network), and a separate test injects a fake searcher by monkeypatching `deep.build_searcher`.

## 6. Acceptance criteria

1. `/deep <hard cultivation question>` draws 3 samples (visible `deliberating · sample i/3` progress), then streams ONE reconciled answer ending with an `agreement: k/3` line.
2. `/deep` on a live-info question (e.g. "current oyster prices") auto-grounds in web search, reconciles, and prints a Sources list + the agreement line.
3. `/deep web <q>` forces a web search even when the query wouldn't auto-trigger.
4. A failed sample doesn't crash `/deep` — it reconciles over the rest; all-fail yields a clean error.
5. `crest_frame` still satisfies the existing thinking-crest test (default label "thinking").
6. Full suite green, ruff clean, version bumps to **0.5.0**, no new dependency.

## 7. Out of scope (later)

- P2 RAG (Knowledge Lake grounding) — the next phase; deeper than web.
- Parallel sampling, varied-angle/persona prompts, multi-model judging, a `/deep` auto-trigger.
- Re-ranking / full-page fetch for the grounded path (a 1.5b hardening item, independent).

## 8. Risks

- **Latency:** 3 sequential samples + judge ≈ 30-40s on the warm L4. Mitigated by the labeled progress crest (never a silent wait) and being explicit (`/deep` only).
- **Self-consistency limits:** a small model may agree on a wrong answer (shared blind spot). The agreement line is a *confidence signal*, not a correctness guarantee — the judge prompt is instructed to flag uncertainty, not manufacture false confidence.
- **Judge format drift:** the model may not always emit the exact `agreement:` line. Acceptable — it's a nicety; the reconciled answer is the product. (No parsing depends on it.)
