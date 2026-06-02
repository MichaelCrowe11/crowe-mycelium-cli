# Crowe Mycelium CLI — Core Peer Redesign (Phase 1)

**Date:** 2026-06-02
**Status:** Design approved, ready for implementation planning
**Scope:** Phase 1 of a 5-phase redesign. This spec covers Phase 1 only; later phases are summarized for context and get their own spec → plan → build cycles.

---

## 1. Background & motivation

`crowe-mycelium` is the standalone CLI for **Gemma 4 Mycelium**, Crowe Logic's open-source mycology-cultivation model (a ~4B Gemma 4 E4B fine-tune). Today it is a single 183-line `cli.py`: Click-based, four commands (`chat`/`run`/`info`/`models`), a single local-Ollama backend, minimal branding, no thinking indicator, no markdown rendering, and four slash commands.

By contrast, the sibling CLIs `crowe-logic` and `deepparallel` share a mature design language the mycology CLI lacks:

- a brand mark (`◆`) + brand-specific palette,
- an animated "thinking" crest so waits are never silent,
- markdown **block-streaming** (settle-per-block, no ghosting),
- a **renderer abstraction** (Plain for pipes, Rich for terminals),
- a **backend/deployment abstraction** with routing/fallback,
- a rich slash-command palette and mode/state shown in the prompt.

Separately, over the course of building out this model the artifact now has **three homes** — local Ollama (on the Elements drive), an always-warm **Modal cloud** endpoint, and the Ollama registry — reached today by two ad-hoc scripts (`crowelm-mycelium`, `crowelm-cloud`). The redesign unifies those into one tool.

**Goal of Phase 1:** bring `crowe-mycelium` up to full peer status with `crowe-logic`/`deepparallel` — both the *look* (design language) and the *brains* (backend abstraction + routing) — and fold the two scripts into one CLI.

## 2. Decisions captured (from brainstorming)

- **Redesign scope:** Full peer — adopt the design language **and** a backend abstraction unifying local + cloud (+ registry).
- **Auto-routing policy:** **cloud-first, local fallback.** The Modal endpoint is kept always-warm (`min_containers=1`), so it is the consistent default; local Ollama is the offline safety net.
- **Domain features (later phases):** grounded answers (RAG), cultivation context + grow log, domain quick-commands.
- **Capability stance:** **multimodal cultivation specialist**, model-true — vision (photo diagnosis), voice I/O (Whisper in / cloned-Mike ElevenLabs out), safe domain tools. **No general coding from this model.**
- **Hybrid brain (later phase):** add an *escalation* path that borrows a capable Foundry model for agentic/hard-coding tasks; mycology stays the default. **Phase 1 must bake in the escalation seam.**
- **Gemma attribution:** model name must retain "Gemma" (legal — Gemma Terms of Use). UI keeps a **clean Crowe-first hero**; required "Built with Gemma" notice lives in a dim **footer + `/info`** plus NOTICE/README/LICENSE.

## 3. Roadmap (context — only Phase 1 is in scope here)

| Phase | Name | Delivers |
|------|------|----------|
| **1** | **Core peer redesign** *(this spec)* | backend abstraction (local/cloud/auto) + renderer (Plain/Rich) + design language + `serve` — folds the two scripts into one tool |
| 2 | Grounding (RAG) | retrieve + cite from the Crowe Logic Knowledge Lake / SOP library |
| 3 | Cultivation workflow | `--species/--stage` context, grow-log journaling, quick-commands (`species`, `contam`, `ref`) |
| 4 | Multimodal | voice I/O first; vision last (needs a new serving path — own spike) |
| 5 | Hybrid brain | detect / `/escalate` coding+agentic tasks → borrow a Foundry model |

## 4. Architecture

Evolve the existing `crowe_mycelium` package — do **not** start fresh. It already has `branding.py`, `model.py`, `provenance.py`, `registry.json`, `system_prompt.txt`. Refactor the monolithic `cli.py` into focused modules mirroring how `deepparallel` separates agent / backend / renderer / branding.

```
crowe_mycelium/
├── cli.py              # Click group + REPL loop — THIN, delegates to session/runtime
├── config.py           # Settings dataclass; resolve env > .env > defaults
├── session.py          # REPL state, slash-command dispatch, history-lite
├── backends/
│   ├── base.py         # Backend ABC: stream_chat(), health(), name/label
│   ├── local.py        # LocalOllamaBackend (Elements readability guard)
│   ├── cloud.py        # CloudModalBackend (deployed Modal endpoint)
│   └── router.py       # AutoBackend: cloud-first → local fallback
│                       #   + ESCALATION SEAM (Phase 5 ForgeBrain slots here)
├── render/
│   ├── base.py         # Renderer ABC
│   ├── plain.py        # PlainRenderer — pipe-safe (answer→stdout, diag→stderr)
│   ├── rich.py         # RichRenderer — markdown block-streaming + panels
│   └── thinking.py     # emerald "cultivation" thinking crest (kills silent waits)
├── branding.py         # ◆ mark, wordmark, emerald palette  (extend existing)
├── model.py            # (existing) → becomes LocalOllamaBackend's guts
├── provenance.py       # (existing) Gemma attribution
├── registry.json       # (existing)
└── system_prompt.txt   # (existing)
```

**Two clean seams (the core of the redesign):**

- **`Backend` ABC** — local, cloud, and (Phase 5) borrowed-brain are interchangeable behind one `stream_chat(messages) -> Iterator[str]` interface plus `health() -> bool` and `name`/`label`. The router owns the cloud-first → local → (later) escalate logic. The UI never knows which backend answered. The Phase 5 escalation backend is *just another `Backend`* plus a routing rule, so it slots in without reworking Phase 1.
- **`Renderer` ABC** — the REPL/one-shot loop is UI-agnostic. `RichRenderer` for TTYs, `PlainRenderer` for pipes/scripts. This is what keeps `crowe-mycelium run "x" | jq` clean.

**Folding in the two scripts** (the unification):
- `crowelm-cloud`  → thin shim → `crowe-mycelium --cloud …`
- `crowelm-mycelium` → thin shim → `crowe-mycelium --local …`
- Both stay on PATH for muscle memory but delegate to the one tool. (The current `~/.local/bin/crowelm-cloud` `--chat` + idle-closeout behavior is preserved by mapping to `crowe-mycelium chat --cloud`.)

## 5. Commands (Phase 1)

| Command | Purpose | Notes |
|---------|---------|-------|
| `crowe-mycelium` *(default)* | interactive chat (Rich) | everyday entry |
| `chat` | explicit chat | `--local` / `--cloud` / `--auto` |
| `run "prompt"` | one-shot | auto-switches to **Plain** when piped (`not sys.stdout.isatty()`) |
| `info` | model + reachable backends + settings (+ Gemma attribution line) | |
| `models` | registered model(s) | |
| `doctor` | diagnose local (Elements/Ollama) **and** cloud (Modal) reachability | borrowed from `deepparallel doctor` |
| `serve` | OpenAI-compat `/v1` gateway | **stretch within Phase 1** — lets the mycology chat app point at it |

## 6. Backend routing

- **Default `auto`:** try cloud → on failure fall back to local **if** Elements is mounted and Ollama is up.
- **Override:** `--local` / `--cloud` flags; live `/local` `/cloud` `/auto` in the REPL.
- **Prompt tag always names the active backend** (`[cloud · modal]` / `[local · offline]`) — routing is never ambiguous.
- `CloudModalBackend` targets the deployed `crowe-mycelium-serve` Modal app (the `smoke` function path used by `crowelm-cloud`, account-auth, no proxy token; or the `/v1` endpoint when configured).
- `LocalOllamaBackend` carries the readability guard from `scripts/run-mycelium.sh` (an `ls $STORE/blobs` I/O touch) so a stale/unmounted Elements drive is detected up front.

## 7. Design language (the "look")

- **◆ mark + emerald palette** — cultivation green, distinct from crowe-logic's gold and deepparallel's cyan.
- **Emerald thinking crest while generating**, with **elapsed seconds** — directly fixes the silent-wait problem (a cold/slow backend is never mistaken for a freeze).
- **Markdown block-streaming** — deepparallel's settle-per-block strategy: paragraphs / lists / code fences render once they settle, never overwriting (no ghosting).
- **Rich slash palette:** `/help /quit /reset /info /local /cloud /auto /think /timeout /model /doctor`.
- **Clean Crowe-first hero** + dim `built with Gemma · Gemma Terms apply` footer.

Welcome + turn (mockup):

```
  ◆ Crowe Logic · Mycelium                       cultivation
  ───────────────────────────────────────────────────────────
  backend: auto (cloud-first)   ·   /help for commands

[cloud · modal] you ▸ is this trichoderma?
  ⬢ ⠿ thinking · 6s
myc ▸ Green, powdery spread from a single point is the classic
      **Trichoderma** signature. Act now:
        1. Bag and remove the block — don't open it near others
        2. Drop room RH and increase FAE

  built with Gemma · Gemma Terms apply
```

Pipe-safe Plain mode:

```
$ crowe-mycelium run --cloud "CO2 for oyster fruiting?" | tee notes.txt
600–1200 ppm during fruiting to drive pinning and flush development.
```

## 8. Data flow

```
input ─▶ session (slash-dispatch │ prompt)
       ─▶ router.stream_chat(messages)
            auto:  cloud.health()? ─yes▶ cloud.stream_chat
                                    ─no ▶ local (if Elements up) ─▶ local.stream_chat
            explicit (--local/--cloud): bypass router
       ─▶ token iterator
       ─▶ renderer    Rich: block-stream + emerald crest
                      Plain: tokens ▶ stdout (pipe-safe)
       ─▶ display + history-lite
```

## 9. Error handling

- **Cloud fails** (timeout / HTTP / network) → auto-fall back to local; surface a dim `⚠ cloud unreachable → local`.
- **Local unavailable** (Elements unmounted / Ollama down) → readability-guard message. If `auto` and cloud is *also* down → one clear dual-failure message (`plug in Elements, or check the Modal app`).
- **Slow / cold** → thinking crest with elapsed seconds; never a silent wait.
- **Ctrl-C / Ctrl-D** → cancel current generation / exit gracefully.
- **Plain mode** → errors to **stderr**, answer to **stdout** (pipes stay clean).

## 10. Testing (pytest + ruff, per repo conventions)

- `FakeBackend` (deterministic token stream) drives renderer / REPL / router tests with no network.
- **Router:** cloud-down → local chosen; both-down → correct error. (unit)
- **Config:** env > .env > defaults resolution. (unit)
- **PlainRenderer:** golden output + stdout/stderr separation (pipe-safe).
- **RichRenderer:** block-settling accumulator (no ghosting mid-fence).
- **doctor:** mocked reachability probes for local + cloud.

## 11. Gemma attribution (compliance)

- Model name **must** begin with "Gemma" (`Gemma 4 Mycelium` / `gemma-4-mycelium-e4b`) — non-negotiable per Gemma Terms of Use; appears in `info`, `models`, `registry.json`.
- "Built with Gemma" notice: dim welcome footer + `/info` + existing NOTICE / README / LICENSE.
- This is the one intentional override of the user's general "don't expose the tech stack" preference, because Gemma branding is a legal requirement, not a stack leak.

## 12. Out of scope (Phase 1)

- RAG grounding / citations (Phase 2).
- `--species/--stage` context, grow log, mycology quick-commands (Phase 3).
- Voice I/O and vision (Phase 4).
- Borrowed-brain escalation routing logic (Phase 5) — Phase 1 only provides the seam.
- Retraining, model changes, or new serving paths (vision serving is a Phase 4 spike).

## 13. Risks & open questions

- **`serve` gateway scope:** marked a stretch within Phase 1; if it expands the surface too much, defer to Phase 1.5. Decide during planning.
- **`CloudModalBackend` transport:** `smoke`-function call (account-auth, simplest, matches `crowelm-cloud`) vs the proxy-auth `/v1` HTTP endpoint. Default to the `smoke` path for parity; `/v1` is needed only if `serve`/external clients require it.
- **History-lite depth:** Phase 1 keeps in-REPL history only (no persistence / replay). Persistence is deferred unless planning shows it's cheap.
- **Cloud cost coupling:** the always-warm cloud (`min_containers=1`, ~$425/mo) is an existing decision; this CLI does not change it, but `doctor`/`info` should surface that the cloud backend is a paid always-on resource.
```
