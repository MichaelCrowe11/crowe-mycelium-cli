# Crowe Mycelium CLI 1.5b — Agentic Web Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add CLI-orchestrated web search (`/search` + an auto-detect offer) so the mycology model answers current-info questions grounded in fetched DuckDuckGo results with citations.

**Architecture:** The model can't emit tool calls on Ollama 0.24.0 (probe-confirmed 400), so the CLI runs the search itself: a provider-agnostic `Searcher` (keyless DuckDuckGo backend hitting `lite.duckduckgo.com/lite/` directly — no `ddgs` lib) returns `SearchResult`s; a `grounding` helper formats them into the user turn with a "cite as [n]" instruction; the answer streams through the existing backend/renderer; the CLI prints a dim Sources list. Degrades to an ungrounded answer on any search failure.

**Tech Stack:** Python 3.10+, httpx (already a dep — NO new dep), Rich, Click, pytest, ruff. Run tests with `.venv/bin/python -m pytest -q`; lint with `.venv/bin/python -m ruff check crowe_mycelium tests`.

---

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `crowe_mycelium/search.py` | `SearchResult`, `Searcher` ABC, `DuckDuckGoSearcher`, `build_searcher()` | Create |
| `crowe_mycelium/grounding.py` | `needs_live_info()`, `format_grounding()`, `sources_text()` | Create |
| `crowe_mycelium/session.py` | dispatch a `/search <query>` prefix | Modify |
| `crowe_mycelium/cli.py` | `/search` handling + auto-detect offer + Sources render | Modify |
| `tests/test_search.py` | searcher parse/empty/factory | Create |
| `tests/test_grounding.py` | heuristic + formatting | Create |
| `tests/test_session.py` | `/search` dispatch | Modify |
| `pyproject.toml`, `crowe_mycelium/__init__.py` | version → 0.4.0 | Modify |

---

### Task 1: Searcher + DuckDuckGo backend

**Files:**
- Create: `crowe_mycelium/search.py`
- Test: `tests/test_search.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_search.py
from crowe_mycelium.search import DuckDuckGoSearcher, SearchResult

# Minimal fixture matching the VERIFIED DDG-lite structure:
# <a ... href="URL" class='result-link'>TITLE</a> (single-quoted class, href first)
# <td ... class='result-snippet'>SNIPPET</td>
FIXTURE = """
<html><body>
<a rel="nofollow" href="https://a.example/1" class='result-link'>Alpha Title</a>
<td class='result-snippet'>Alpha snippet text.</td>
<a rel="nofollow" href="https://b.example/2" class='result-link'>Beta &amp; Title</a>
<td class='result-snippet'>Beta snippet <b>bold</b> text.</td>
</body></html>
"""


def test_parses_results_from_fixture():
    s = DuckDuckGoSearcher(fetch=lambda q: FIXTURE)
    out = s.search("anything", max_results=5)
    assert len(out) == 2
    assert out[0] == SearchResult(
        title="Alpha Title", url="https://a.example/1", snippet="Alpha snippet text."
    )
    # HTML entities decoded, inner tags stripped/collapsed
    assert out[1].title == "Beta & Title"
    assert out[1].snippet == "Beta snippet bold text."


def test_max_results_caps_output():
    s = DuckDuckGoSearcher(fetch=lambda q: FIXTURE)
    assert len(s.search("x", max_results=1)) == 1


def test_empty_or_garbage_html_returns_empty():
    s = DuckDuckGoSearcher(fetch=lambda q: "<html></html>")
    assert s.search("x") == []


def test_fetch_error_returns_empty():
    def boom(q):
        raise RuntimeError("network down")

    s = DuckDuckGoSearcher(fetch=boom)
    assert s.search("x") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_search.py -v`
Expected: FAIL — `crowe_mycelium/search.py` does not exist.

- [ ] **Step 3: Create `crowe_mycelium/search.py`**

```python
"""Web search for grounding the mycology model's answers.

The model can't self-trigger tools on this Ollama stack (probe-confirmed 400 on
a tools request), so the CLI runs search itself. v1 ships a keyless DuckDuckGo
backend that hits the lite HTML endpoint directly (the `ddgs` library rotates to
a Yahoo backend that fails under Tailscale MagicDNS). A provider-agnostic
`Searcher` seam reserves Brave/Tavily for later.
"""

from __future__ import annotations

import html
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Optional

import httpx

DDG_LITE_URL = "https://lite.duckduckgo.com/lite/"

# VERIFIED structure (2026-06-02): single-quoted class, href before class.
_LINK_RE = re.compile(r"<a\s+[^>]*?href=\"([^\"]+)\"[^>]*?class='result-link'[^>]*?>(.*?)</a>", re.S)
_SNIPPET_RE = re.compile(r"class='result-snippet'[^>]*>(.*?)</td>", re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str


def _clean(s: str) -> str:
    """Strip inner tags, decode entities, collapse whitespace."""
    return _WS_RE.sub(" ", html.unescape(_TAG_RE.sub("", s))).strip()


class Searcher(ABC):
    """Returns web results for a query. Backends are interchangeable behind this."""

    @abstractmethod
    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        raise NotImplementedError


class DuckDuckGoSearcher(Searcher):
    """Keyless DuckDuckGo via the lite HTML endpoint.

    `fetch` is an injectable seam (query -> raw HTML) so tests never hit the
    network; the default posts to the lite endpoint.
    """

    def __init__(self, fetch: Optional[Callable[[str], str]] = None):
        self._fetch = fetch or self._default_fetch

    def _default_fetch(self, query: str) -> str:
        r = httpx.post(
            DDG_LITE_URL,
            data={"q": query},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10.0,
        )
        r.raise_for_status()
        return r.text

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        try:
            html_text = self._fetch(query)
        except Exception:
            return []  # caller degrades to an ungrounded answer
        links = _LINK_RE.findall(html_text)
        snippets = [_clean(s) for s in _SNIPPET_RE.findall(html_text)]
        results: list[SearchResult] = []
        for i, (href, title) in enumerate(links[:max_results]):
            results.append(
                SearchResult(
                    title=_clean(title),
                    url=href,
                    snippet=snippets[i] if i < len(snippets) else "",
                )
            )
        return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_search.py -v`
Expected: PASS (all four).

- [ ] **Step 5: Lint + commit**

```bash
.venv/bin/python -m ruff check crowe_mycelium/search.py tests/test_search.py
git add crowe_mycelium/search.py tests/test_search.py
git commit -m "feat(search): keyless DuckDuckGo searcher via lite endpoint (no ddgs dep)"
```

---

### Task 2: build_searcher factory

**Files:**
- Modify: `crowe_mycelium/search.py` (append factory)
- Test: `tests/test_search.py` (append)

- [ ] **Step 1: Append failing tests**

```python
def test_build_searcher_defaults_to_duckduckgo(monkeypatch):
    monkeypatch.delenv("CROWE_MYCELIUM_SEARCH_PROVIDER", raising=False)
    from crowe_mycelium.search import build_searcher, DuckDuckGoSearcher

    assert isinstance(build_searcher(), DuckDuckGoSearcher)


def test_build_searcher_unimplemented_provider_raises(monkeypatch):
    monkeypatch.setenv("CROWE_MYCELIUM_SEARCH_PROVIDER", "brave")
    from crowe_mycelium.search import build_searcher

    import pytest

    with pytest.raises(NotImplementedError, match="duckduckgo"):
        build_searcher()
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_search.py -k build_searcher -v`
Expected: FAIL — `build_searcher` not defined.

- [ ] **Step 3: Append the factory to `crowe_mycelium/search.py`**

```python
def build_searcher(settings=None) -> Searcher:
    """Pick a search backend. v1 implements DuckDuckGo only; the brave/tavily
    branch is the reserved seam (add when a key exists)."""
    import os

    provider = os.environ.get("CROWE_MYCELIUM_SEARCH_PROVIDER", "duckduckgo").lower()
    if provider == "duckduckgo":
        return DuckDuckGoSearcher()
    raise NotImplementedError(
        f"search provider '{provider}' is not implemented yet. "
        f"Set CROWE_MYCELIUM_SEARCH_PROVIDER=duckduckgo (keyless) until a "
        f"Brave/Tavily backend + key is added."
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_search.py -v`
Expected: PASS (all six).

- [ ] **Step 5: Lint + commit**

```bash
.venv/bin/python -m ruff check crowe_mycelium/search.py tests/test_search.py
git add crowe_mycelium/search.py tests/test_search.py
git commit -m "feat(search): build_searcher factory (DDG default, brave/tavily seam reserved)"
```

---

### Task 3: grounding helpers

**Files:**
- Create: `crowe_mycelium/grounding.py`
- Test: `tests/test_grounding.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_grounding.py
from crowe_mycelium.grounding import needs_live_info, format_grounding, sources_text
from crowe_mycelium.search import SearchResult

RESULTS = [
    SearchResult("Oyster prices 2026", "https://a.example/p", "Around $6-12/lb."),
    SearchResult("Market report", "https://b.example/m", "Wholesale trends."),
]


def test_needs_live_info_true_for_live_signals():
    assert needs_live_info("what is the current price of oyster mushrooms")
    assert needs_live_info("latest news on mushroom market")
    assert needs_live_info("oyster prices in 2026")


def test_needs_live_info_false_for_knowledge_questions():
    assert not needs_live_info("how do I fruit lion's mane")
    assert not needs_live_info("what substrate for oysters")


def test_format_grounding_includes_query_results_and_cite_instruction():
    g = format_grounding("oyster price?", RESULTS)
    assert "oyster price?" in g
    assert "[1]" in g and "[2]" in g
    assert "https://a.example/p" in g
    assert "cite" in g.lower()


def test_sources_text_lists_each_url_numbered():
    s = sources_text(RESULTS)
    assert "Sources:" in s
    assert "[1] https://a.example/p" in s
    assert "[2] https://b.example/m" in s
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_grounding.py -v`
Expected: FAIL — `crowe_mycelium/grounding.py` does not exist.

- [ ] **Step 3: Create `crowe_mycelium/grounding.py`**

```python
"""Turn web results into a grounded prompt turn + a Sources footer.

The CLI appends `format_grounding(...)` to the user message so the model answers
over the fetched results and cites them as [n]; `sources_text(...)` is printed
(dim) after the answer so the links are always visible.
"""

from __future__ import annotations

import re

from crowe_mycelium.search import SearchResult

# Conservative live-info signals — used only to OFFER a search, never to search
# silently. Plus any 4-digit year >= 2025.
_LIVE_TERMS = (
    "current",
    "latest",
    "today",
    "this week",
    "right now",
    "as of",
    "price",
    "cost",
    "news",
    "weather",
    "in stock",
    "available now",
)
_YEAR_RE = re.compile(r"\b(20[2-9]\d)\b")


def needs_live_info(text: str) -> bool:
    t = text.lower()
    if any(term in t for term in _LIVE_TERMS):
        return True
    m = _YEAR_RE.search(t)
    return bool(m and int(m.group(1)) >= 2025)


def format_grounding(query: str, results: list[SearchResult]) -> str:
    lines = [
        f"[{i}] {r.title} — {r.snippet} ({r.url})" for i, r in enumerate(results, 1)
    ]
    body = "\n".join(lines)
    return (
        f"{query}\n\n"
        f"Use ONLY these web search results to answer, and cite sources inline as [n]. "
        f"If they don't answer the question, say so plainly.\n\n"
        f"{body}"
    )


def sources_text(results: list[SearchResult]) -> str:
    lines = [f"[{i}] {r.url}" for i, r in enumerate(results, 1)]
    return "Sources:\n" + "\n".join(lines)
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_grounding.py -v`
Expected: PASS (all four).

- [ ] **Step 5: Lint + commit**

```bash
.venv/bin/python -m ruff check crowe_mycelium/grounding.py tests/test_grounding.py
git add crowe_mycelium/grounding.py tests/test_grounding.py
git commit -m "feat(grounding): needs_live_info heuristic + grounding/sources formatting"
```

---

### Task 4: `/search` slash dispatch

**Files:**
- Modify: `crowe_mycelium/session.py`
- Test: `tests/test_session.py` (append)

- [ ] **Step 1: Append failing tests** to `tests/test_session.py`

```python
def test_search_with_query_dispatches_with_arg():
    from crowe_mycelium.session import dispatch_slash

    r = dispatch_slash("/search oyster wholesale prices")
    assert r.handled and r.action == "search"
    assert r.arg == "oyster wholesale prices"


def test_bare_search_dispatches_empty_arg():
    from crowe_mycelium.session import dispatch_slash

    r = dispatch_slash("/search")
    assert r.handled and r.action == "search" and r.arg == ""


def test_existing_commands_still_dispatch():
    from crowe_mycelium.session import dispatch_slash

    assert dispatch_slash("/help").action == "help"
    assert dispatch_slash("/quit").action == "quit"
    assert dispatch_slash("hello").handled is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_session.py -k search -v`
Expected: FAIL — `/search` currently falls through to the `noop` branch (action != "search").

- [ ] **Step 3: Add the prefix branch in `crowe_mycelium/session.py`**

In `dispatch_slash`, add the `/search` prefix check AFTER the exact-match checks (QUIT/SIMPLE/SWITCH) and BEFORE the final `if c.startswith("/"): return SlashResult(True, "noop")`:

```python
    if c == "/search" or c.startswith("/search "):
        return SlashResult(True, "search", c[len("/search"):].strip())
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_session.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add crowe_mycelium/session.py tests/test_session.py
git commit -m "feat(session): dispatch /search <query> prefix command"
```

---

### Task 5: Wire the search flow into the chat loop

**Files:**
- Modify: `crowe_mycelium/cli.py`

> This is integration (interactive offer + Rich render). The testable units (parser, factory, heuristic, formatting, dispatch) are covered in Tasks 1-4. This task wires them and is verified live in Task 6.

- [ ] **Step 1: Add imports to `cli.py`**

Near the other `from crowe_mycelium ...` imports:

```python
from crowe_mycelium import grounding as _grounding
from crowe_mycelium.search import build_searcher
```

- [ ] **Step 2: Add the shared search-flow helper** (module-level function in `cli.py`, above `_chat_loop`):

```python
def _run_search(query, backend, renderer, system, history, settings):
    """Fetch web results, answer grounded with a Sources footer. Degrades to an
    ungrounded answer if search yields nothing."""
    try:
        results = build_searcher(settings).search(query)
    except NotImplementedError as e:
        renderer.notice(str(e))
        results = []
    if not results:
        renderer.notice("web search unavailable — answering from knowledge.")
        user_turn = query
    else:
        user_turn = _grounding.format_grounding(query, results)
    messages = _build_messages(history, system, user_turn)
    reply = renderer.render_stream(backend.stream_chat(messages, settings.temperature))
    if results:
        console.print(f"[grey50]{_grounding.sources_text(results)}[/]")
    # Store the ORIGINAL query (not the bulky grounding block) in history.
    history.append(("user", query))
    history.append(("assistant", reply))
    return reply
```

- [ ] **Step 3: Handle the `search` slash action** in `_chat_loop`. In the slash-dispatch `if res.handled:` block, add a branch alongside the existing ones (e.g. after the `doctor` branch):

```python
            elif res.action == "search":
                if not res.arg:
                    branding.info("usage: /search <query>")
                else:
                    _run_search(res.arg, backend, renderer, system, history, settings)
                continue
```

(Ensure this `continue`s so it doesn't fall through to the normal answer path. If the surrounding structure already `continue`s at the end of the slash block, the inner `continue` is still correct/safe.)

- [ ] **Step 4: Add the auto-detect offer** for normal messages. In `_chat_loop`, after the slash-dispatch block and BEFORE building messages for a normal answer (i.e. right before `messages = _build_messages(history, system, user_msg)`), insert:

```python
        if _grounding.needs_live_info(user_msg):
            try:
                ans = _prompt.read_input(
                    session, "  this looks like it needs current data — search the web? [Y/n] "
                ).strip().lower()
            except (EOFError, KeyboardInterrupt):
                ans = "n"
            if ans in ("", "y", "yes"):
                _run_search(user_msg, backend, renderer, system, history, settings)
                branding.turn_separator()
                continue
```

- [ ] **Step 5: Confirm import + tests**

Run: `.venv/bin/python -c "import crowe_mycelium.cli"` → expect no error.
Run: `.venv/bin/python -m pytest tests/test_cli.py -v` → expect PASS.
Run: `.venv/bin/python -m ruff check crowe_mycelium/cli.py` → expect All checks passed.

- [ ] **Step 6: Commit**

```bash
git add crowe_mycelium/cli.py
git commit -m "feat(cli): wire /search flow + auto-detect search offer + Sources footer"
```

---

### Task 6: Version bump + live verification

**Files:**
- Modify: `pyproject.toml`, `crowe_mycelium/__init__.py`

- [ ] **Step 1: Bump version to 0.4.0** in both `crowe_mycelium/__init__.py` (`__version__ = "0.4.0"`) and `pyproject.toml` (`version = "0.4.0"`).

- [ ] **Step 2: Full suite + lint**

Run: `.venv/bin/python -m pytest -q` → expect all pass (prior 53 + new search/grounding/session tests).
Run: `.venv/bin/python -m ruff check crowe_mycelium tests` → expect All checks passed.
Confirm NO new dependency was added: `grep -c ddgs pyproject.toml` → expect `0`.

- [ ] **Step 3: Live verification (real terminal)**

Run `.venv/bin/crowe-mycelium --cloud chat` and verify:
1. `/search current wholesale price of oyster mushrooms` → fetches real results, the answer cites `[n]`, and a dim `Sources:` list with URLs follows.
2. Type a normal live question `what are oyster prices right now` → the **offer** appears ("search the web? [Y/n]"); pressing Enter/y runs the search; `n` answers from knowledge.
3. Type a knowledge question `how do I fruit lion's mane` → **no** offer, normal answer.
4. Simulate failure: `CROWE_MYCELIUM_SEARCH_PROVIDER=brave .venv/bin/crowe-mycelium --cloud chat` then `/search x` → prints the "not implemented … set …=duckduckgo" notice and answers ungrounded, no traceback.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml crowe_mycelium/__init__.py
git commit -m "chore: bump to 0.4.0 — Phase 1.5b agentic web search"
```

---

## Self-Review notes

- **Spec coverage:** §3.1 Searcher/DDG → T1; §3.1 factory → T2; §3.2 grounding/heuristic → T3; §3.3 dispatch → T4; §3.4 flow + offer + Sources → T5; §6 acceptance + version → T6. §4 error handling → T1 (`search` returns `[]` on fetch error) + T5 (`_run_search` degrade + NotImplementedError notice). All covered.
- **Type consistency:** `SearchResult(title, url, snippet)` used identically in T1/T3; `Searcher.search(query, max_results=5)` consistent T1↔T5; `format_grounding(query, results)` / `sources_text(results)` / `needs_live_info(text)` signatures match T3↔T5; `build_searcher(settings=None)` called as `build_searcher(settings)` in T5 (settings accepted, currently unused — reserved for provider config) and `build_searcher()` in T2 tests — both valid.
- **No new dep:** uses `httpx` (already present) + stdlib `re`/`html`; `ddgs` intentionally NOT added (T6 Step 2 asserts).
- **Placeholder scan:** none — every code step is complete.
- **Live-only:** the interactive offer + Rich Sources render are verified in T6, not unit-tested (the pure units they call are all tested in T1-T4).
