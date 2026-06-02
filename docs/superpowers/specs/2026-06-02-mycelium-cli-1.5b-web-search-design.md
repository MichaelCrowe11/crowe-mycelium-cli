# Crowe Mycelium CLI 1.5b — Agentic Web Search (`/search`)

**Date:** 2026-06-02
**Status:** Design approved, ready for implementation planning
**Scope:** Phase 1.5b only. Builds on 1.5a's messages-based backend. Sibling of 1.5c (deep mode), which gets its own spec → plan → build.

---

## 1. Background & motivation

1.5a made the model *honest* about having no tools (it says "I cannot browse the web" instead of hanging 86 s). 1.5b gives it real web search so it can answer questions about current/live information (prices, news, recent cultivars) grounded in fetched sources, with citations.

**Architecture decision — CLI-orchestrated (probe-confirmed).** A live probe (2026-06-02) sent the deployed/local model an Ollama `tools` request; Ollama 0.24.0 returned `400` (the model's custom Modelfile has no tool-capable chat template). So **model-driven tool calling is not viable on this stack** without rebaking the 9.6 GB model with a tool template (high cost, uncertain payoff on a 4B). Instead, the **CLI** runs the search, injects results into the prompt as grounding, and the model answers over them. This is reliable and testable.

**Provider decision — keyless DuckDuckGo, pluggable.** Azure's native web search (Bing Search v7) is **retired** — provisioning via `az` was attempted live and returned `ApiSetDisabledForCreation: Bing Search APIs are retired` (the `Microsoft.Bing` provider was registered but no resource could be created; nothing to clean up). Azure's successor "Grounding with Bing Search" only works inside a Foundry Agent with an Azure-hosted model, so it can't ground *our* model. The user has no Brave/Tavily keys. Decision: a keyless **DuckDuckGo** backend (verified working) behind a provider-agnostic `Searcher` seam, so a Brave/Tavily key can drop in later via env var without a rewrite.

**Keyless DuckDuckGo path — verified live.** The `ddgs` library failed in this environment (it rotates to a Yahoo backend whose DNS got mangled by Tailscale MagicDNS). But a **direct POST to `https://lite.duckduckgo.com/lite/`** returned HTTP 200 with parseable results. So v1 hits that endpoint directly with `httpx` and parses the HTML — **no `ddgs` dependency**. Verified parser: result anchors are `<a ... href="URL" class='result-link'>TITLE</a>` (single-quoted class, href before class) and snippets are `<td ... class='result-snippet'>...</td>`.

## 2. Decisions captured (from brainstorming)

- **Architecture:** CLI-orchestrated (model can't self-trigger tools — probe-confirmed).
- **Provider:** keyless DuckDuckGo via direct `lite.duckduckgo.com/lite/`; provider-agnostic `Searcher` seam reserves Brave/Tavily for later (v1 implements DDG only).
- **Trigger:** BOTH — explicit `/search <query>` AND a conservative auto-detect that *offers* to search ("…search the web? [Y/n]"), never searches silently.
- **Results:** top 5 — title + snippet + URL. **No full-page fetch** in v1.
- **Citations:** inline `[n]` markers (model instructed) + a dim **Sources** list (`[n] url`) printed by the CLI after every search answer, regardless of whether the model cited.
- **Graceful degrade:** 0 results / network / parse error → dim notice + ungrounded answer. Keyed provider selected but key absent → fall back to DDG.
- **Scope guard (YAGNI):** no full-page fetch, no multi-hop/iterative search, no re-ranking.

## 3. Architecture / new + changed surfaces

```
crowe_mycelium/
  search.py        # NEW — SearchResult, Searcher ABC, DuckDuckGoSearcher, build_searcher()
  grounding.py     # NEW — format_grounding(results) + sources_text(results); needs_live_info(text)
  session.py       # MODIFY — dispatch a "/search <query>" prefix (today: exact-match only)
  cli.py           # MODIFY — handle /search in chat loop; auto-detect offer; render Sources
```

### 3.1 `search.py`
- `@dataclass(frozen=True) SearchResult: title: str; url: str; snippet: str`
- `class Searcher(ABC)` with `search(self, query: str, max_results: int = 5) -> list[SearchResult]`.
- `class DuckDuckGoSearcher(Searcher)`:
  - `__init__(self, fetch: Callable[[str], str] | None = None)` — `fetch` is an injectable seam returning raw HTML for a query (default posts to `lite.duckduckgo.com/lite/`); tests inject a fixture-returning fake so no network is hit.
  - `search(...)` parses the HTML (verified regexes), zips links with snippets, returns up to `max_results` `SearchResult`s. Returns `[]` on parse failure (caller degrades).
- `build_searcher(settings) -> Searcher` — factory. Reads `CROWE_MYCELIUM_SEARCH_PROVIDER` (default `"duckduckgo"`). v1 only constructs `DuckDuckGoSearcher`; brave/tavily branches raise a clear "provider not yet implemented; set CROWE_MYCELIUM_SEARCH_PROVIDER=duckduckgo or add a key" — the seam exists, the impl is deferred.

### 3.2 `grounding.py`
- `needs_live_info(text: str) -> bool` — conservative keyword heuristic (`current`, `latest`, `today`, `this week`, `right now`, `as of`, `price`, `cost`, `news`, `weather`, 4-digit years ≥ 2025). Used for the auto-detect offer.
- `format_grounding(query: str, results: list[SearchResult]) -> str` — the injected context block: instructs the model to answer the question using ONLY the results below and cite as `[n]`, followed by `[1] title — snippet (url)` lines.
- `sources_text(results: list[SearchResult]) -> str` — the dim `Sources:\n[1] url\n…` footer string.

### 3.3 `session.py`
- Add prefix handling: if a line starts with `/search ` (with an argument), return `SlashResult(True, "search", arg=<query>)`. A bare `/search` (no query) returns a help-y `SlashResult(True, "search", arg="")` so the loop can prompt for a query. Keep all existing exact-match commands working.

### 3.4 `cli.py` (`_chat_loop`)
- On `SlashResult.action == "search"`: if `arg` empty, `branding.info("usage: /search <query>")` and continue; else run the **search flow** (below).
- Auto-detect: for a normal (non-slash) user message, if `needs_live_info(user_msg)` is true, ask via the prompt-toolkit session "This looks like it needs current data — search the web? [Y/n] " — on yes, run the search flow with `user_msg` as the query; on no, fall through to the normal answer.
- **Search flow** (shared helper `_run_search(query, backend, renderer, history, settings)`):
  1. `searcher = build_searcher(settings)`; `results = searcher.search(query)`.
  2. If `not results`: `renderer.notice("web search unavailable — answering from knowledge.")`, then answer the original query ungrounded (normal path).
  3. Else build messages with the grounding block appended to the user turn, stream the answer via the renderer (unchanged crest+stream), then `console.print(sources_text(results))` (dim).
  4. Append the *original* user query + the answer to history (not the bulky grounding block — keeps multi-turn context clean).

## 4. Error handling

- Network/timeout/parse error inside `DuckDuckGoSearcher.search` → caught, returns `[]` → CLI degrades to ungrounded answer + notice. (`search` never raises to the loop.)
- DDG rate-limit (non-200 / empty) → `[]` → same graceful degrade.
- Keyed-provider env set but unimplemented/keyless → factory raises a clear message caught in the loop as a notice; falls back to DDG only if provider is `duckduckgo`.

## 5. Testing (TDD)

- **Parser:** `DuckDuckGoSearcher(fetch=lambda q: FIXTURE_HTML).search("x")` → asserts N `SearchResult`s with expected title/url/snippet from a saved DDG-lite HTML fixture. No network.
- **Empty/garbage HTML:** `fetch` returns `"<html></html>"` → `search` returns `[]`.
- **`needs_live_info`:** true for "current oyster price", "news 2026"; false for "how do I fruit lion's mane".
- **`format_grounding` / `sources_text`:** include each url and `[n]` markers; instruct citation.
- **Dispatch:** `dispatch_slash("/search oyster prices")` → `SlashResult(True, "search", "oyster prices")`; `dispatch_slash("/search")` → action search, empty arg; existing commands still dispatch.
- **Degrade:** a `Searcher` whose `search` returns `[]` → the flow takes the ungrounded branch (assert notice emitted; testable by checking the messages built omit grounding).

## 6. Acceptance criteria

1. `/search <query>` fetches real DDG results, the model answers grounded with `[n]` citations, and a dim Sources list follows.
2. Asking a clearly-live question (e.g. "current oyster wholesale price") triggers the **offer**; declining answers normally; accepting runs the search flow.
3. A normal cultivation question (no live-info signal) does NOT trigger the offer.
4. With network/DDG unavailable, `/search` degrades to an ungrounded answer + a dim notice — no traceback.
5. Sources list always prints when results were used, even if the model didn't cite.
6. `build_searcher` defaults to DuckDuckGo; the Brave/Tavily seam exists (factory branch) but is explicitly deferred.
7. Full suite green, ruff clean, no new runtime dependency (`ddgs` NOT added; uses `httpx` already present).
8. Version bumps to 0.4.0.

## 7. Out of scope (later)

- **1.5c** deep mode (multi-sample + judge).
- Model-driven tool calling (would need a rebaked tool-template model).
- Brave/Tavily backends (seam reserved; add when a key exists).
- Full-page fetch + readability extraction; multi-hop/iterative search; result re-ranking.

## 8. Risks

- **DDG HTML drift / rate-limiting:** the lite endpoint is unofficial; markup could change or throttle. Mitigation: parser returns `[]` on mismatch → graceful degrade; the `Searcher` seam lets a keyed provider replace it cleanly. Parser pinned to verified single-quoted `class='result-link'` / `class='result-snippet'` structure.
- **Tailscale MagicDNS** mangled the `ddgs` library's Yahoo backend in one shell; avoided entirely by hitting `lite.duckduckgo.com` directly (its DNS resolved fine).
- **Auto-detect false positives:** mitigated by *offering* (never silent) and a conservative keyword set.
