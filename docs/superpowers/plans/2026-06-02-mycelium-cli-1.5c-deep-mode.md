# Crowe Mycelium CLI 1.5c — Deep Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `/deep <question>` — a web-aware ensemble command that samples the model N times, reconciles the answers with a judge pass, and reports an agreement/confidence signal.

**Architecture:** `deep.py` orchestrates: optionally ground via the 1.5b searcher, collect N temperature-diverse samples (each under a labeled "deliberating" crest), then stream a judge/reconcile completion. It reuses `build_searcher`/`format_grounding`/`sources_text`/`needs_live_info` from 1.5b and the streaming renderer from 1.5a; `cli._build_messages` is passed in so `deep.py` never imports `cli`.

**Tech Stack:** Python 3.10+, Rich, Click, httpx (all present). Run tests `.venv/bin/python -m pytest -q`; lint `.venv/bin/python -m ruff check crowe_mycelium tests`. No new dependency.

---

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `crowe_mycelium/render/thinking.py` | `crest_frame(tick, elapsed, label="thinking")` | Modify |
| `crowe_mycelium/render/base.py` | abstract `deliberate(label, fn)` | Modify |
| `crowe_mycelium/render/rich.py` | `deliberate`: labeled crest while `fn` runs | Modify |
| `crowe_mycelium/render/plain.py` | `deliberate`: run `fn` silently | Modify |
| `crowe_mycelium/deep.py` | `collect_sample`, `build_judge_messages`, `deep_samples`, `deep_temperature`, `run_deep` | Create |
| `crowe_mycelium/session.py` | `/deep <query>` dispatch | Modify |
| `crowe_mycelium/cli.py` | `deep` action → `deep.run_deep` | Modify |
| `tests/test_render_rich.py`, `test_render_plain.py` | `deliberate` + `crest_frame` label | Modify |
| `tests/test_deep.py` | deep orchestration + helpers | Create |
| `tests/test_session.py` | `/deep` dispatch | Modify |
| `pyproject.toml`, `crowe_mycelium/__init__.py` | version → 0.5.0 | Modify |

---

### Task 1: `crest_frame` gains a label

**Files:**
- Modify: `crowe_mycelium/render/thinking.py`
- Test: `tests/test_render_rich.py` (append)

- [ ] **Step 1: Append failing test** to `tests/test_render_rich.py`:

```python
def test_crest_frame_accepts_custom_label():
    from crowe_mycelium.render.thinking import crest_frame

    assert "deliberating" in crest_frame(0, 3, label="deliberating")
    assert "thinking" in crest_frame(0, 3)  # default unchanged
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_render_rich.py::test_crest_frame_accepts_custom_label -v`
Expected: FAIL — `crest_frame` takes no `label` kwarg.

- [ ] **Step 3: Add the `label` parameter** in `crowe_mycelium/render/thinking.py`. Change the `crest_frame` signature and the line that renders the label. Current:

```python
def crest_frame(tick: int, elapsed: int) -> str:
    """Rich-markup string (multi-line) for one frame of the thinking crest."""
    color = PALETTE[tick % len(PALETTE)]
    spin = _SPIN[tick % len(_SPIN)]
    top = "   " + _field_row(tick, 0)
    # Middle strand carries the hex mark + the cycling-color "thinking" label
    # (keeps the PALETTE[0]/"thinking"/elapsed test contract).
    mid = (
        f"[{color}]{MARK}[/]  {_field_row(tick, 1)}  "
        f"[grey50]{spin}[/] [bold {color}]thinking[/] [grey50]· {elapsed}s[/]"
    )
    bot = "   " + _field_row(tick, 2)
    return f"{top}\n{mid}\n{bot}"
```

Change to:

```python
def crest_frame(tick: int, elapsed: int, label: str = "thinking") -> str:
    """Rich-markup string (multi-line) for one frame of the thinking crest.

    `label` is the verb shown on the middle strand ("thinking" by default,
    "deliberating · sample 2/3" for deep mode)."""
    color = PALETTE[tick % len(PALETTE)]
    spin = _SPIN[tick % len(_SPIN)]
    top = "   " + _field_row(tick, 0)
    mid = (
        f"[{color}]{MARK}[/]  {_field_row(tick, 1)}  "
        f"[grey50]{spin}[/] [bold {color}]{label}[/] [grey50]· {elapsed}s[/]"
    )
    bot = "   " + _field_row(tick, 2)
    return f"{top}\n{mid}\n{bot}"
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_render_rich.py -v`
Expected: PASS (the new test + the existing `test_crest_frame_shows_elapsed_and_cycles_color`, which uses the default label).

- [ ] **Step 5: Commit**

```bash
git add crowe_mycelium/render/thinking.py tests/test_render_rich.py
git commit -m "feat(render): crest_frame takes a custom label (default 'thinking')"
```

---

### Task 2: Renderer `deliberate(label, fn)`

**Files:**
- Modify: `crowe_mycelium/render/base.py`, `crowe_mycelium/render/rich.py`, `crowe_mycelium/render/plain.py`
- Test: `tests/test_render_rich.py`, `tests/test_render_plain.py` (append)

- [ ] **Step 1: Append failing tests**

To `tests/test_render_rich.py`:

```python
def test_rich_deliberate_runs_fn_and_returns_result():
    from crowe_mycelium.render.rich import RichRenderer

    assert RichRenderer().deliberate("working", lambda: "DONE") == "DONE"


def test_rich_deliberate_propagates_error():
    import pytest

    from crowe_mycelium.render.rich import RichRenderer

    def boom():
        raise RuntimeError("sample died")

    with pytest.raises(RuntimeError, match="sample died"):
        RichRenderer().deliberate("working", boom)
```

To `tests/test_render_plain.py`:

```python
def test_plain_deliberate_runs_fn_and_returns_result():
    from crowe_mycelium.render.plain import PlainRenderer

    assert PlainRenderer().deliberate("working", lambda: "DONE") == "DONE"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_render_rich.py tests/test_render_plain.py -k deliberate -v`
Expected: FAIL — `deliberate` not defined.

- [ ] **Step 3a: Add the abstract method** to `crowe_mycelium/render/base.py`. After the `render_stream` abstractmethod, add:

```python
    @abstractmethod
    def deliberate(self, label: str, fn) -> str:
        """Run `fn` (a no-arg callable returning text) while showing a labeled
        working indicator; return fn()'s result. Used to collect hidden samples."""
        raise NotImplementedError
```

- [ ] **Step 3b: Implement in `crowe_mycelium/render/rich.py`.** Add this method to `RichRenderer` (after `render_stream`):

```python
    def deliberate(self, label: str, fn) -> str:
        box: dict = {}

        def run():
            try:
                box["result"] = fn()
            except BaseException as e:  # surfaced after the live region closes
                box["err"] = e
            finally:
                box["done"] = True

        th = threading.Thread(target=run, daemon=True)
        t0 = time.time()
        th.start()
        with Live(console=console, refresh_per_second=30, transient=True) as live:
            tick = 0
            while not box.get("done"):
                live.update(Text.from_markup(crest_frame(tick, int(time.time() - t0), label=label)))
                tick += 1
                time.sleep(0.05)
        th.join()
        if "err" in box:
            raise box["err"]
        return box.get("result", "")
```

(The imports `threading`, `time`, `Live`, `Text`, `console`, `crest_frame` are already at the top of `rich.py` from 1.5a.)

- [ ] **Step 3c: Implement in `crowe_mycelium/render/plain.py`.** Add to `PlainRenderer` (after `render_stream`):

```python
    def deliberate(self, label: str, fn) -> str:
        print(label, file=sys.stderr)
        return fn()
```

(`sys` is already imported in `plain.py`.)

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_render_rich.py tests/test_render_plain.py -v`
Expected: PASS (all, including the prior render tests).

- [ ] **Step 5: Commit**

```bash
git add crowe_mycelium/render/base.py crowe_mycelium/render/rich.py crowe_mycelium/render/plain.py tests/test_render_rich.py tests/test_render_plain.py
git commit -m "feat(render): deliberate(label, fn) — labeled crest around a hidden sample"
```

---

### Task 3: deep.py helpers (sample, judge prompt, config)

**Files:**
- Create: `crowe_mycelium/deep.py`
- Test: `tests/test_deep.py` (create)

- [ ] **Step 1: Write the failing test** — create `tests/test_deep.py`:

```python
from crowe_mycelium import deep


class _StreamBackend:
    def __init__(self, chunks):
        self._chunks = chunks

    def stream_chat(self, messages, temperature=0.4):
        yield from self._chunks


def test_collect_sample_joins_stream():
    assert deep.collect_sample(_StreamBackend(["a", "b", "c"]), [], 0.8) == "abc"


def test_build_judge_messages_includes_candidates_query_and_instruction():
    msgs = deep.build_judge_messages("SYS", "why no pinning?", ["ans one", "ans two"])
    assert msgs[0] == {"role": "system", "content": "SYS"}
    user = msgs[1]["content"]
    assert "why no pinning?" in user
    assert "ans one" in user and "ans two" in user
    assert "reconcile" in user.lower()
    assert "agreement:" in user.lower()


def test_deep_samples_default_and_env(monkeypatch):
    monkeypatch.delenv("CROWE_MYCELIUM_DEEP_SAMPLES", raising=False)
    assert deep.deep_samples() == 3
    monkeypatch.setenv("CROWE_MYCELIUM_DEEP_SAMPLES", "5")
    assert deep.deep_samples() == 5
    monkeypatch.setenv("CROWE_MYCELIUM_DEEP_SAMPLES", "1")  # floored at 2
    assert deep.deep_samples() == 2


def test_deep_temperature_default_and_env(monkeypatch):
    monkeypatch.delenv("CROWE_MYCELIUM_DEEP_TEMPERATURE", raising=False)
    assert deep.deep_temperature() == 0.8
    monkeypatch.setenv("CROWE_MYCELIUM_DEEP_TEMPERATURE", "0.5")
    assert deep.deep_temperature() == 0.5
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_deep.py -v`
Expected: FAIL — `crowe_mycelium/deep.py` does not exist.

- [ ] **Step 3: Create `crowe_mycelium/deep.py`** with this content (the `run_deep` orchestrator is added in Task 4 — include only the helpers + imports now):

```python
"""Deep mode: a web-aware ensemble. Sample the model N times (temperature-diverse),
optionally grounded in web search, then a judge pass reconciles the candidates into
one best answer with an agreement/confidence signal.

Composes 1.5b (search/grounding) + 1.5a (streaming renderer). cli._build_messages
is passed in so this module never imports cli.
"""

from __future__ import annotations

import os

from crowe_mycelium.branding import console
from crowe_mycelium.grounding import format_grounding, needs_live_info, sources_text
from crowe_mycelium.search import build_searcher


def deep_samples() -> int:
    """How many candidate answers to draw (default 3, floored at 2)."""
    raw = os.environ.get("CROWE_MYCELIUM_DEEP_SAMPLES", "3")
    try:
        return max(2, int(raw))
    except ValueError:
        return 3


def deep_temperature() -> float:
    """Sampling temperature for the candidates (default 0.8 for diversity)."""
    raw = os.environ.get("CROWE_MYCELIUM_DEEP_TEMPERATURE", "0.8")
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.8


def collect_sample(backend, messages, temperature) -> str:
    """Consume one full completion from the backend stream into a string."""
    return "".join(backend.stream_chat(messages, temperature))


def build_judge_messages(system: str, query: str, candidates: list[str]) -> list[dict]:
    """The reconciliation prompt: original question + numbered candidates + a
    directive to merge them and end with an agreement line."""
    n = len(candidates)
    numbered = "\n\n".join(f"[Answer {i}]\n{c}" for i, c in enumerate(candidates, 1))
    user = (
        f"Question: {query}\n\n"
        f"{n} independent expert answers were drafted:\n\n{numbered}\n\n"
        f"Reconcile them into ONE best answer. Where they agree, state it confidently; "
        f"where they diverge, choose the most evidence-grounded option and flag the "
        f"uncertainty. End with one line: 'agreement: <k>/{n} aligned' "
        f"(append ' — diverged on <topic>' if they differ)."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_deep.py -v`
Expected: PASS (the four helper tests).

- [ ] **Step 5: Lint + commit**

```bash
.venv/bin/python -m ruff check crowe_mycelium/deep.py tests/test_deep.py
git add crowe_mycelium/deep.py tests/test_deep.py
git commit -m "feat(deep): sample/judge/config helpers for ensemble reasoning"
```

---

### Task 4: deep.run_deep orchestrator

**Files:**
- Modify: `crowe_mycelium/deep.py` (append `run_deep`)
- Test: `tests/test_deep.py` (append)

- [ ] **Step 1: Append failing tests** to `tests/test_deep.py`:

```python
from crowe_mycelium.config import Settings
from crowe_mycelium.search import SearchResult


class _DeepBackend:
    """First N stream_chat calls return the samples; the next returns the judge."""

    def __init__(self, samples, judge):
        self._samples = list(samples)
        self._judge = judge
        self.calls = 0

    def stream_chat(self, messages, temperature=0.4):
        self.calls += 1
        if self.calls <= len(self._samples):
            yield self._samples[self.calls - 1]
        else:
            yield self._judge


class _RecRenderer:
    def __init__(self):
        self.labels = []
        self.streamed = []
        self.errors = []
        self.notices = []

    def deliberate(self, label, fn):
        self.labels.append(label)
        return fn()

    def render_stream(self, chunks):
        text = "".join(chunks)
        self.streamed.append(text)
        return text

    def error(self, msg):
        self.errors.append(msg)

    def notice(self, msg):
        self.notices.append(msg)


def _bm(history, system, user):
    return [{"role": "user", "content": user}]


def test_run_deep_samples_then_judges(monkeypatch):
    monkeypatch.setenv("CROWE_MYCELIUM_DEEP_SAMPLES", "3")
    be = _DeepBackend(samples=["s1", "s2", "s3"], judge="reconciled")
    r = _RecRenderer()
    history = []
    deep.run_deep("how do I diagnose green mold", be, "SYS", history, Settings(), r, _bm)
    assert len(r.labels) == 3  # three hidden samples
    assert r.streamed == ["reconciled"]  # one judge stream
    assert history[-2:] == [
        ("user", "how do I diagnose green mold"),
        ("assistant", "reconciled"),
    ]


def test_run_deep_degrades_when_all_samples_empty():
    be = _DeepBackend(samples=["", "  ", ""], judge="never")
    r = _RecRenderer()
    deep.run_deep("how do I diagnose mold", be, "SYS", [], Settings(), r, _bm)
    assert r.errors and "no answers" in r.errors[0]
    assert r.streamed == []  # no judge call when nothing to reconcile


def test_run_deep_grounds_when_query_needs_live_info(monkeypatch):
    class _FakeSearcher:
        def search(self, query, max_results=5):
            return [SearchResult("Title", "http://src", "snippet")]

    monkeypatch.setattr(deep, "build_searcher", lambda settings: _FakeSearcher())
    be = _DeepBackend(samples=["s1", "s2", "s3"], judge="rec")
    r = _RecRenderer()
    captured = {}

    def bm(history, system, user):
        captured["user"] = user
        return [{"role": "user", "content": user}]

    deep.run_deep("current oyster prices", be, "SYS", [], Settings(), r, bm)
    assert "http://src" in captured["user"]  # grounding injected into the turn
    assert "[1]" in captured["user"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_deep.py -k run_deep -v`
Expected: FAIL — `run_deep` not defined.

- [ ] **Step 3: Append `run_deep` to `crowe_mycelium/deep.py`:**

```python
def run_deep(query, backend, system, history, settings, renderer, build_messages, *, force_web=False):
    """Ensemble: optionally ground, sample N times, judge/reconcile, render.

    `build_messages` is cli._build_messages (passed to avoid importing cli)."""
    results = []
    if force_web or needs_live_info(query):
        try:
            results = build_searcher(settings).search(query)
        except NotImplementedError as e:
            renderer.notice(str(e))
            results = []
    user_turn = format_grounding(query, results) if results else query

    n = deep_samples()
    temp = deep_temperature()
    candidates: list[str] = []
    for i in range(n):
        messages = build_messages(history, system, user_turn)
        try:
            sample = renderer.deliberate(
                f"deliberating · sample {i + 1}/{n}",
                lambda m=messages: collect_sample(backend, m, temp),
            )
        except Exception:
            sample = ""  # a failed sample is skipped; reconcile over the rest
        if sample.strip():
            candidates.append(sample)

    if not candidates:
        renderer.error("deep mode: no answers produced.")
        return

    judge_messages = build_judge_messages(system, query, candidates)
    try:
        reply = renderer.render_stream(backend.stream_chat(judge_messages, 0.3))
    except Exception as e:
        renderer.error(str(e))
        return

    if results:
        console.print(f"[grey50]{sources_text(results)}[/]")
    history.append(("user", query))
    history.append(("assistant", reply))
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_deep.py -v`
Expected: PASS (all deep tests).

- [ ] **Step 5: Lint + commit**

```bash
.venv/bin/python -m ruff check crowe_mycelium/deep.py tests/test_deep.py
git add crowe_mycelium/deep.py tests/test_deep.py
git commit -m "feat(deep): run_deep orchestrator (ground -> sample N -> judge -> render)"
```

---

### Task 5: `/deep` slash dispatch

**Files:**
- Modify: `crowe_mycelium/session.py`
- Test: `tests/test_session.py` (append)

- [ ] **Step 1: Append failing tests** to `tests/test_session.py`:

```python
def test_deep_with_query_dispatches_with_arg():
    r = dispatch_slash("/deep how do I diagnose green mold")
    assert r.handled and r.action == "deep" and r.arg == "how do I diagnose green mold"


def test_deep_web_arg_preserved():
    r = dispatch_slash("/deep web oyster prices")
    assert r.handled and r.action == "deep" and r.arg == "web oyster prices"


def test_bare_deep_dispatches_empty_arg():
    r = dispatch_slash("/deep")
    assert r.handled and r.action == "deep" and r.arg == ""
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_session.py -k deep -v`
Expected: FAIL — `/deep` falls through to `noop`.

- [ ] **Step 3: Add the `/deep` branch** in `crowe_mycelium/session.py`, right AFTER the `/search` branch and BEFORE the final `if c.startswith("/"):` noop:

```python
    if c == "/deep" or c.startswith("/deep "):
        return SlashResult(True, "deep", c[len("/deep") :].strip())
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_session.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add crowe_mycelium/session.py tests/test_session.py
git commit -m "feat(session): dispatch /deep <query> (and /deep web <query>)"
```

---

### Task 6: Wire `/deep` into the chat loop

**Files:**
- Modify: `crowe_mycelium/cli.py`

- [ ] **Step 1: Add the import** near the other `from crowe_mycelium ...` imports in `cli.py`:

```python
from crowe_mycelium import deep as _deep
```

- [ ] **Step 2: Add the `deep` slash branch.** In `_chat_loop`'s slash-dispatch `if res.handled:` chain, add a branch right after the `elif res.action == "search":` block:

```python
            elif res.action == "deep":
                arg = res.arg
                force_web = False
                if arg.startswith("web "):
                    force_web = True
                    arg = arg[len("web ") :].strip()
                if not arg:
                    branding.info("usage: /deep <question>  (or /deep web <question>)")
                else:
                    _deep.run_deep(
                        arg, backend, system, history, settings, renderer,
                        _build_messages, force_web=force_web,
                    )
                    branding.turn_separator()
```

- [ ] **Step 3: Confirm import + CLI tests**

Run: `.venv/bin/python -c "import crowe_mycelium.cli"` → expect no error.
Run: `.venv/bin/python -m pytest tests/test_cli.py -v` → expect PASS.
Run: `.venv/bin/python -m ruff check crowe_mycelium/cli.py` → expect All checks passed.

- [ ] **Step 4: Commit**

```bash
git add crowe_mycelium/cli.py
git commit -m "feat(cli): wire /deep (and /deep web) into the chat loop"
```

---

### Task 7: Version bump + full verification

**Files:**
- Modify: `pyproject.toml`, `crowe_mycelium/__init__.py`

- [ ] **Step 1: Bump version to 0.5.0** in `crowe_mycelium/__init__.py` (`__version__ = "0.5.0"`) and `pyproject.toml` (`version = "0.5.0"`).

- [ ] **Step 2: Full suite + lint + no-new-dep**

Run: `.venv/bin/python -m pytest -q` → expect all pass (prior 68 + new deep/render/session tests).
Run: `.venv/bin/python -m ruff check crowe_mycelium tests` → expect All checks passed (the pre-existing scripts/ lint errors are out of scope).
Run: `grep -c ddgs pyproject.toml` → expect `0`.

- [ ] **Step 3: Live verification (real terminal, warm L4)**

Run `.venv/bin/crowe-mycelium --cloud chat` and verify:
1. `/deep how do I diagnose a stalled lion's mane that won't pin` → shows `deliberating · sample 1/3 … 2/3 … 3/3`, then streams ONE reconciled answer ending with an `agreement: k/3` line. No web (knowledge ensemble).
2. `/deep current wholesale oyster mushroom prices` → auto-grounds (fetches sources), reconciles, prints a Sources list + the agreement line.
3. `/deep web lion's mane` → forces a search even though it wouldn't auto-trigger.
4. `/deep` (bare) → prints the usage line.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml crowe_mycelium/__init__.py
git commit -m "chore: bump to 0.5.0 — Phase 1.5c deep mode"
```

---

## Self-Review notes

- **Spec coverage:** §3.1 deep.py (helpers → T3, run_deep → T4); §3.2 renderer deliberate + crest label → T1+T2; §3.3 dispatch → T5; §3.4 cli wiring → T6; §6 acceptance + version → T7. §4 error handling → T4 (sample skip + all-fail error + judge error). All covered.
- **Type consistency:** `run_deep(query, backend, system, history, settings, renderer, build_messages, *, force_web=False)` matches T4 impl, T4 tests, and the T6 call site; `collect_sample(backend, messages, temperature)`, `build_judge_messages(system, query, candidates)`, `deep_samples()/deep_temperature()` consistent T3↔T4; `deliberate(label, fn) -> str` consistent base/rich/plain (T2) and the T4 `renderer.deliberate(...)` call.
- **No new dep:** uses stdlib + existing 1.5b/1.5a code; `grep ddgs` asserted 0 in T7.
- **Placeholder scan:** none — every step has complete code.
- **Live-only:** the labeled-crest visual + the warm-L4 latency are verified in T7 Step 3; all pure units are unit-tested (T1–T6).
