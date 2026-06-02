# Crowe Mycelium CLI — Quality & Brand Foundation (Phase 1.5a)

**Date:** 2026-06-02
**Status:** Design approved, ready for implementation planning
**Scope:** Phase 1.5a only. Sits between Phase 1 (core peer redesign, shipped) and Phase 2 (RAG). Lays the messages-based foundation that the two follow-on sub-phases (1.5b agentic web search, 1.5c deep mode) plug into; each of those gets its own spec → plan → build.

---

## 1. Background & motivation

Phase 1 shipped the backend/renderer/branding abstractions and merged `crowelm-cloud`/`crowelm-mycelium` into one tool. A live `crowelm-cloud` session immediately exposed four substantive defects (not cosmetics):

1. **Garbled identity.** Asked "lions mane", the model answered *"Lycoperdon perlatum — a fine-tune of Google's Gemma 4 by Crowe Logic…"* — wrong species name **and** a foundation-model blurt. Two root causes:
   - `system_prompt.txt:4` literally instructs the model to introduce itself as *"a fine-tune of Google's Gemma 4"*. Self-inflicted brand leak.
   - `backends/cloud.py:flatten_messages` collapses the whole transcript into one `User:/Assistant:` string and drops the system message, then calls the single-prompt `smoke` Modal fn. Multi-turn role separation is destroyed, so the model degrades and confabulates.
2. **Mangled multiline paste.** `cli.py:69` reads input with bare `console.input()` (line-at-a-time). A pasted multi-line block gets shredded and the `[cloud · modal] you ▸` prompt tag interleaves into the captured text.
3. **`search web` → 86 s hang.** The model has no tools; it can't search. It silently grinds on a slow T4 instead of saying so.
4. **Branding below peer bar.** Single-line hero; no wordmark, no status HUD, no turn separators — `crowe-logic`/`deepparallel` both lead with a block wordmark + HUD.

**Goal of 1.5a:** brand-correct the model's conversational identity, fix cloud multi-turn (real `messages`, not flatten) + bump the GPU, make paste/multiline input not shred, handle capability requests honestly instead of hanging, add live token streaming, and bring branding to deepparallel-grade — **all on a messages-based backend foundation** that 1.5b/1.5c build on.

## 2. Decisions captured (from brainstorming)

- **Decompose into 1.5a / 1.5b / 1.5c.** 1.5a is the quality+brand+foundation core (this spec). 1.5b = real agentic web search. 1.5c = deep mode (multi-sample + judge). All three were requested; sequencing keeps each verifiable.
- **Crowe-first conversational identity.** The model presents as *"Crowe Mycelium, Crowe Logic's cultivation intelligence."* It never volunteers Gemma/base-model details in answers. Gemma attribution stays where Phase 1 put it — the dim footer + `/info` + NOTICE/README. **Gemma's license requires the model *name* and a "Built with Gemma" notice on product surfaces; it does NOT require the model to announce "Gemma" in conversation.** So Crowe-first chat is fully compliant.
- **Capability-honesty is model-driven, not CLI keyword-matching.** The system prompt tells the model it cannot browse/use tools, so it declines instantly and offers what it *can* do. No brittle CLI guessing about whether a prompt "is" a tool request. (Real `/search` arrives in 1.5b.)
- **CLI owns the system prompt.** It is sent in the `messages` array, overriding the Modelfile-baked default — so the brand-corrected identity takes effect **without** rebaking the 9.6 GB image. (Hedge below if Ollama ignores a supplied system over the Modelfile default.)
- **GPU bump T4 → L4.** Rides the same Modal redeploy; ~2–3× faster, kills the slow-grind feel.
- **Live token streaming.** Answers type out progressively. The renderer's block-streaming design already supports this; the work is making the Modal cloud fn a generator and consuming it with `remote_gen()`.
- **Version bumps to 0.3.0.**

## 3. Architecture / changed surfaces

```
crowe_mycelium/
  system_prompt.txt        # REWRITE — Crowe-first identity + capability-honesty
  backends/
    base.py                # stream_chat already returns Iterator[str] — unchanged contract
    cloud.py               # drop flatten; send real messages; consume Modal generator (remote_gen)
    local.py               # raise truncating num_predict default (quality nudge)
  prompt.py                # NEW — prompt-toolkit PromptSession (paste-safe, slash-complete, history)
  wordmark.py              # NEW — ASCII block wordmark + status HUD + narrow-terminal fallback
  branding.py              # hero() delegates to wordmark; turn separators / model gutter helpers
  cli.py                   # _chat_loop uses prompt.read_input(); HUD on start
scripts/
  serve_ollama_modal.py    # NEW chat(messages, temperature) generator fn; GPU="L4"; smoke kept
```

The `Backend.stream_chat(messages, temperature) -> Iterator[str]` contract is **unchanged** — Phase 1 already shaped it as a streaming iterator. 1.5a makes the cloud implementation actually yield tokens instead of one chunk.

## 4. Section 1 — Quality core (the substance)

### 4.1 Brand-correct identity (`system_prompt.txt` rewrite)
- Replace the line-4 identity rule. New identity: **"Crowe Mycelium, Crowe Logic's cultivation intelligence."** The model never volunteers Gemma/base-model details. If a user *explicitly* asks about infrastructure, it may give one brief honest line — but that is never its default self-intro, and it never blurts a base-model name unprompted.
- Add an explicit **capability-honesty rule:** *"You cannot browse the web, run tools, or access live data. If asked to search or use tools, say so in one sentence and offer what you can do from knowledge."* — kills the 86 s grind on "search web".
- Keep the existing operating-style and safety blocks (lines 8–18) intact.

### 4.2 Cloud multi-turn — real `messages` + streaming + L4 (`serve_ollama_modal.py`, `backends/cloud.py`)
- **New Modal fn `chat(messages, temperature)`** in `serve_ollama_modal.py`: forwards the full `messages` array (system + history + user) to Ollama `/api/chat` with `stream=True`, **yielding** token deltas as they arrive (a Modal generator function, consumed by the backend via `.remote_gen(...)`). Keep `min_containers=1` (one warm box) and `timeout=600`.
- **GPU = "L4"** on both the warm fn and the image — rides the same `modal deploy`.
- **Keep `smoke(prompt)`** unchanged as the no-proxy-auth `modal run` verification path.
- **`CloudModalBackend.stream_chat`** drops `flatten_messages`; it looks up `chat` and yields from `.remote_gen(messages, temperature)`. `flatten_messages` is deleted (or retained only if a test still references the single-prompt path — verify and remove).
- **CLI owns the system prompt** (already built into `messages` by `_build_messages`), so the brand-corrected `system_prompt.txt` takes effect with no image rebake.
- **Hedge:** if Ollama `/api/chat` ignores a per-request `system` message in favor of the Modelfile-baked one (so the old identity still leaks), fall back to rebaking the image with the new `system_prompt.txt` — same `modal deploy` path. The plan must include a live check of which wins.

## 5. Section 2 — Input & interaction (`prompt.py`)

- New module `prompt.py` wrapping a prompt-toolkit `PromptSession` (the dep is already declared in `pyproject.toml` but currently unused):
  - **Bracketed paste** → a multi-line paste is captured as one submission (no more shredding / tag interleave).
  - **Styled prompt** carrying the backend tag (`[cloud · modal] ▸`), rendered by prompt-toolkit so it never interleaves with output.
  - **Slash completion** — typing `/` offers `/local /cloud /auto /info /reset /doctor /help /quit`.
  - **History** — up/down recall within the session.
- API: `build_session(completer/keybindings)` and `read_input(session, tag) -> str`.
- `cli.py:_chat_loop` calls `read_input(...)` instead of `console.input(...)`. **Falls back to plain `input()` when not a TTY**, so piping/`run` still works.
- **Honest tool/web handling is model-side** (the §4.1 capability rule) — no CLI keyword-matching.

## 6. Section 3 — deepparallel-grade branding (`wordmark.py`)

- **Block-letter emerald wordmark** on chat start, with `◆ cultivation intelligence` tagline; **auto-falls back to the compact `◆ Crowe Mycelium · cultivation`** when the terminal is narrow (mirrors deepparallel).
- **Status HUD line:** `backend <label> (GPU)  ·  model gemma-4-mycelium-e4b  ·  v0.3.0` — the always-visible context `crowe-logic` shows.
- **Polished turn rendering:** answers stay markdown block-streamed behind the emerald thinking crest (kept), with a subtle model gutter (`myc ▸`) and a thin turn separator so the transcript doesn't read as a wall.
- **Notices/errors** as styled dim/red lines (e.g. the existing `⚠ cloud unreachable → local` notice).
- **Dim "built with Gemma" footer** stays (legal, understated).
- Isolated in `wordmark.py` (ASCII art + HUD + narrow-terminal detection) so `branding.py` doesn't bloat.

## 7. Folded-in items (no separate decision)

- **`serve` (OpenAI-compat /v1 gateway)** inherits the fix for free — it routes through the cloud backend, so the new `chat(messages)` path + brand-correct identity flow through it.
- **Local quality nudge:** local defaults are tight (`num_predict=160` can truncate answers). Raise the default so local answers aren't cut short; keep it env-overridable.
- **Streaming makes the renderer earn its keep:** crest shows until the first token, then tokens stream into the settling block.

## 8. Out of scope (later sub-phases)

- **1.5b** — real `/search` → fetch sources → grounded answer with citations (tool-call loop + search provider).
- **1.5c** — `/deep` → multi-sample + judge/merge for hard diagnoses.
- Both build on the 1.5a messages-based backend.

## 9. Acceptance criteria

1. Asking the model "what are you?" yields a **Crowe-first** identity with **no** "Gemma"/base-model blurt; asking "lions mane" returns correct *Hericium erinaceus* guidance with no species/identity confusion.
2. A multi-turn cloud conversation retains context across turns (proves `messages` path, not flatten).
3. "search web" (or any tool request) gets an **instant honest** decline + offer, not an 86 s hang.
4. Pasting a multi-line block into the REPL is captured as **one** submission; the prompt tag never interleaves.
5. Answers **stream token-by-token** on the cloud path.
6. Chat start shows the **block wordmark + status HUD**; narrow terminals get the compact fallback.
7. Piping (`crowe-mycelium run "…" | cat`) still produces clean plain output (TTY fallback intact).
8. Modal redeploy reports **GPU L4**; a warm cloud answer is materially faster than the T4 baseline.
9. `built with Gemma` footer + `/info` attribution intact (Gemma Terms compliance).
10. Full test suite green, ruff clean, version `0.3.0`.

## 10. Risks / open questions

- **Ollama system-message precedence** (§4.2 hedge) — must be verified live; rebake is the fallback.
- **Modal generator streaming latency** — `remote_gen` token deltas should feel live on L4; if buffering dominates, fall back to chunked yields.
- **prompt-toolkit + Rich coexistence** — ensure prompt-toolkit's rendering doesn't fight Rich's live block; isolate input vs. output ownership.
