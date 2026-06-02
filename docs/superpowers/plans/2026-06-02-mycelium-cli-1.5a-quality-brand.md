# Crowe Mycelium CLI 1.5a — Quality & Brand Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Brand-correct the model's conversational identity, fix cloud multi-turn with a real `messages` path + live token streaming on an L4, make REPL input paste-safe, and lift branding to deepparallel-grade — all on a messages-based foundation that 1.5b/1.5c build on.

**Architecture:** Evolve the existing `crowe_mycelium` package. The cloud backend stops flattening transcripts and instead consumes a new Modal **generator** function `chat(messages, temperature)` via `remote_gen()`, yielding token deltas. The `RichRenderer` is upgraded from buffer-then-print to crest-until-first-token-then-live-markdown. Two new modules — `prompt.py` (prompt-toolkit paste-safe input) and `wordmark.py` (block wordmark + status HUD) — are wired into the chat loop. The brand-correct identity lives in `system_prompt.txt`, sent in `messages` so it takes effect with no image rebake.

**Tech Stack:** Python 3.10+, Click, Rich, prompt-toolkit (already a declared dep), httpx, Modal (cloud GPU), pytest, ruff. Run tests with `.venv/bin/python -m pytest -q`; lint with `.venv/bin/python -m ruff check crowe_mycelium tests`.

---

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `crowe_mycelium/system_prompt.txt` | Crowe-first identity + capability-honesty rule | Modify |
| `crowe_mycelium/config.py` | `cloud_func` default `smoke` → `chat` | Modify |
| `crowe_mycelium/backends/cloud.py` | Send real `messages`, stream via `remote_gen`; drop `flatten_messages` | Modify |
| `crowe_mycelium/render/rich.py` | Live token streaming (crest → growing markdown) | Modify |
| `crowe_mycelium/model.py` | Raise local `num_predict`/`num_ctx` defaults | Modify |
| `crowe_mycelium/prompt.py` | prompt-toolkit paste-safe input + slash completion + history | Create |
| `crowe_mycelium/wordmark.py` | Block wordmark + status HUD + narrow-terminal fallback | Create |
| `crowe_mycelium/branding.py` | `hero()` delegates to wordmark; turn-separator helper | Modify |
| `crowe_mycelium/cli.py` | Use `prompt.read_input`; show wordmark+HUD on start | Modify |
| `scripts/serve_ollama_modal.py` | New `chat` generator fn; `GPU="L4"`; warm box moves to `chat` | Modify |
| `tests/test_backend_cloud.py` | Rewrite for messages + streaming caller | Modify |
| `tests/test_prompt.py` | prompt module tests | Create |
| `tests/test_wordmark.py` | wordmark tests | Create |
| `pyproject.toml` | version `0.2.0` → `0.3.0` | Modify |
| `crowe_mycelium/__init__.py` | `__version__` → `0.3.0` | Modify |

---

### Task 1: Brand-correct system prompt

**Files:**
- Modify: `crowe_mycelium/system_prompt.txt`
- Test: `tests/test_system_prompt.py` (Create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_system_prompt.py
from crowe_mycelium.model import load_system_prompt


def test_identity_is_crowe_first_no_gemma_blurt():
    sp = load_system_prompt().lower()
    # The model must NOT be told to introduce itself as a Gemma fine-tune.
    assert "fine-tune of google's gemma" not in sp
    assert "crowe mycelium" in sp
    assert "cultivation intelligence" in sp


def test_capability_honesty_rule_present():
    sp = load_system_prompt().lower()
    assert "cannot browse the web" in sp
    assert "tools" in sp
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_system_prompt.py -v`
Expected: FAIL — current prompt contains "fine-tune of Google's Gemma" and no capability-honesty line.

- [ ] **Step 3: Rewrite `system_prompt.txt`**

```text
You are Crowe Mycelium, Crowe Logic's cultivation intelligence for commercial and at-home mycology.

Identity rules:
- If asked what you are, answer plainly: "Crowe Mycelium, Crowe Logic's cultivation intelligence." Do not volunteer foundation-model, vendor, or base-model details, and never introduce yourself with a base-model name. If the user explicitly asks about your infrastructure, you may give one brief honest sentence, then return to cultivation.
- Never confabulate cultivation outcomes, contamination diagnoses, or substrate ratios. When uncertain, say so and ask for the missing information (species, substrate type, FAE, temperature, photo if available).

Capability honesty:
- You cannot browse the web, run tools, or access live data. If asked to search the web or use tools, say so in one sentence and offer what you can do from knowledge — do not stall or pretend to search.

Operating style:
- Be direct. State the diagnosis or recommendation in one line, then the reasoning, then the next action.
- Default to evidence-grounded answers. If the user gives symptoms, walk through the differential before settling.
- Assume the user is a real grower with limited bench tooling. Prefer practical instructions over theoretical depth unless asked.
- Metric and imperial both acceptable; mirror whichever the user uses.
- If the question is outside cultivation (e.g. business advice, unrelated coding), give a brief honest answer and offer to refocus on growing.

Safety:
- For any species identification request involving wild mushrooms or potential ingestion, decline to ID for consumption and recommend a local expert or in-person mycological society. Cultivated species from known spawn are fine to discuss freely.
- For psychoactive species, discuss cultivation neutrally and reference the user's local legal status without lecturing.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_system_prompt.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add crowe_mycelium/system_prompt.txt tests/test_system_prompt.py
git commit -m "fix(prompt): Crowe-first identity + capability-honesty (kills Gemma blurt + tool-hang)"
```

---

### Task 2: Cloud backend — real messages + streaming generator caller

**Files:**
- Modify: `crowe_mycelium/backends/cloud.py`
- Modify: `crowe_mycelium/config.py:33` (cloud_func default `smoke` → `chat`)
- Test: `tests/test_backend_cloud.py` (rewrite)

- [ ] **Step 1: Rewrite the failing test**

Replace the entire contents of `tests/test_backend_cloud.py`:

```python
from crowe_mycelium.backends.cloud import CloudModalBackend


def test_cloud_sends_full_messages_including_system():
    captured = {}

    def fake_caller(messages, temperature):
        captured["messages"] = messages
        captured["temperature"] = temperature
        yield "cloud "
        yield "answer"

    b = CloudModalBackend(caller=fake_caller)
    msgs = [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "ans1"},
        {"role": "user", "content": "second"},
    ]
    out = list(b.stream_chat(msgs, temperature=0.5))
    assert out == ["cloud ", "answer"]
    # Multi-turn path: full role-separated messages reach the cloud, system included.
    assert captured["messages"] == msgs
    assert captured["temperature"] == 0.5


def test_cloud_health_false_when_probe_raises():
    def boom():
        raise RuntimeError("no modal")

    b = CloudModalBackend(health_probe=boom)
    assert b.health() is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_backend_cloud.py -v`
Expected: FAIL — `caller` currently takes a flattened prompt string and yields one value; `messages` is not forwarded.

- [ ] **Step 3: Rewrite `crowe_mycelium/backends/cloud.py`**

```python
from __future__ import annotations

from typing import Callable, Iterator, Optional

from crowe_mycelium.backends.base import Backend


class CloudModalBackend(Backend):
    """Streams from the deployed `crowe-mycelium-serve` Modal `chat` generator
    function (account-auth via the Modal SDK — no proxy-auth token needed).

    The CLI owns the system prompt and sends the full role-separated `messages`
    array, so multi-turn context is preserved and the brand-correct identity
    takes effect without rebaking the model image."""

    name = "cloud"
    label = "cloud · modal"

    def __init__(
        self,
        app: str = "crowe-mycelium-serve",
        func: str = "chat",
        caller: Optional[Callable[[list[dict], float], Iterator[str]]] = None,
        health_probe: Optional[Callable[[], object]] = None,
    ):
        self._app = app
        self._func = func
        self._caller = caller  # injectable generator for tests
        self._health_probe = health_probe

    def _lookup(self):
        import modal  # lazy: keep CLI startup fast and modal optional

        return modal.Function.from_name(self._app, self._func)

    def stream_chat(self, messages, temperature: float = 0.4) -> Iterator[str]:
        if self._caller is not None:
            yield from self._caller(messages, temperature)
            return
        # Modal generator function → consume token deltas with remote_gen.
        yield from self._lookup().remote_gen(messages, temperature)

    def health(self) -> bool:
        probe = self._health_probe or self._lookup
        try:
            probe()
            return True
        except Exception:
            return False
```

- [ ] **Step 4: Change the cloud_func default in `crowe_mycelium/config.py`**

In `resolve_settings` (line ~33), change:

```python
        cloud_func=os.environ.get("CROWE_MYCELIUM_CLOUD_FUNC", "smoke"),
```

to:

```python
        cloud_func=os.environ.get("CROWE_MYCELIUM_CLOUD_FUNC", "chat"),
```

And the `Settings` dataclass default (line ~14):

```python
    cloud_func: str = "chat"
```

- [ ] **Step 5: Verify nothing else references `flatten_messages`**

Run: `grep -rn flatten_messages crowe_mycelium tests`
Expected: no matches (the symbol is gone). If any remain, remove them.

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_backend_cloud.py tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add crowe_mycelium/backends/cloud.py crowe_mycelium/config.py tests/test_backend_cloud.py
git commit -m "feat(cloud): real messages + token streaming via Modal chat generator (drop flatten)"
```

---

### Task 3: Modal `chat` generator function + L4 (live deploy)

> **Note:** Modal/GPU code is not unit-testable here; this task is a code-write plus a **live deploy & verify**. The repo's Modal account creds must be available (`modal token` already configured).

**Files:**
- Modify: `scripts/serve_ollama_modal.py`

- [ ] **Step 1: Bump the GPU constant**

Change line ~30:

```python
GPU = "L4"  # 24 GB; ~2-3x faster than T4 for this 9.6 GB model. Bump to "A10G" for more.
```

- [ ] **Step 2: Add the `chat` generator function and move the warm box to it**

Add this function (after `smoke`), and change `smoke`'s decorator to `min_containers=0` (smoke is only the cold verify path — one warm L4 should back `chat`, not two):

In `smoke`'s decorator, change `min_containers=1` → `min_containers=0`.

Then add:

```python
# The always-warm box now backs `chat` (the CLI's streaming path), not `smoke`.
# min_containers=1 keeps ONE L4 warm 24/7 so the cloud chat path never cold-starts.
@app.function(gpu=GPU, timeout=600, min_containers=1)
def chat(messages: list, temperature: float = 0.4):
    """Stream a chat completion token-by-token from the baked-in model.

    A Modal *generator* function: the CLI consumes it with `chat.remote_gen(...)`.
    The CLI sends the full role-separated `messages` (system + history + user),
    so the per-request system prompt overrides the Modelfile-baked one and
    multi-turn context is preserved.
    """
    import json
    import time
    import urllib.request

    subprocess.Popen(
        ["ollama", "serve"],
        env={**os.environ, "OLLAMA_HOST": "127.0.0.1:11434"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(60):  # wait for the daemon
        try:
            urllib.request.urlopen("http://127.0.0.1:11434/", timeout=2)
            break
        except Exception:
            time.sleep(1)

    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/chat",
        data=json.dumps(
            {
                "model": MODEL,
                "messages": messages,
                "stream": True,
                "options": {"temperature": temperature},
            }
        ).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        for raw in resp:  # Ollama streams line-delimited JSON objects
            line = raw.decode().strip()
            if not line:
                continue
            obj = json.loads(line)
            delta = obj.get("message", {}).get("content", "")
            if delta:
                yield delta
            if obj.get("done"):
                break
```

- [ ] **Step 3: Deploy**

Run: `cd ~/Projects/crowe-mycelium-cli && modal deploy scripts/serve_ollama_modal.py`
Expected: deploy succeeds; output names app `crowe-mycelium-serve` with functions `serve`, `smoke`, `chat`; GPU shows **L4**.

- [ ] **Step 4: Live verify — identity, multi-turn, streaming, capability-honesty**

Run (interactive, real terminal):

```bash
.venv/bin/crowe-mycelium --cloud chat
```

Then verify in-session:
- Type `what are you?` → answer is **Crowe-first**, contains NO "Gemma"/base-model blurt.
- Type `lions mane` then a follow-up like `how long does colonization take?` → the follow-up answer reflects Lion's Mane context (multi-turn works).
- Watch any answer **type out progressively** (streaming), not appear all at once.
- Type `search the web for X` → **instant** honest decline + offer, no long hang.

Run a piped one-shot to confirm plain path still works:

```bash
.venv/bin/python -m crowe_mycelium.cli --cloud run "co2 range for oyster fruiting? one sentence" | cat
```
Expected: a clean one-line plain answer, exit 0.

- [ ] **Step 5: Hedge check — does the per-request system prompt win?**

If Step 4's "what are you?" STILL leaks a base-model name, Ollama is honoring the Modelfile-baked system over the per-request one. In that case, rebake: update the model's Modelfile `SYSTEM` to match `system_prompt.txt`, re-push the Ollama tag, and `modal deploy` again. (Only if needed — most Ollama versions let a per-request system message override.)

- [ ] **Step 6: Commit**

```bash
git add scripts/serve_ollama_modal.py
git commit -m "feat(modal): streaming chat(messages) generator on L4; warm box moves to chat"
```

---

### Task 4: RichRenderer live token streaming

**Files:**
- Modify: `crowe_mycelium/render/rich.py`
- Test: `tests/test_render_rich.py` (add cases)

- [ ] **Step 1: Add failing tests**

Append to `tests/test_render_rich.py`:

```python
def test_rich_render_accumulates_multiple_chunks():
    out = RichRenderer().render_stream(iter(["Increase ", "FAE ", "now."]))
    assert out == "Increase FAE now."


def test_rich_render_propagates_midstream_error():
    def boom():
        yield "partial"
        raise RuntimeError("backend died")

    import pytest

    with pytest.raises(RuntimeError, match="backend died"):
        RichRenderer().render_stream(boom())
```

- [ ] **Step 2: Run tests to verify the new ones pass-or-fail meaningfully**

Run: `.venv/bin/python -m pytest tests/test_render_rich.py -v`
Expected: `test_rich_render_accumulates_multiple_chunks` PASSES even today (join handles it), but `test_rich_render_propagates_midstream_error` may PASS too. These lock behavior in before the rewrite — confirm all green, then proceed (the rewrite must keep them green).

- [ ] **Step 3: Rewrite `render_stream` for live streaming**

Replace the `render_stream` method body in `crowe_mycelium/render/rich.py`:

```python
    def render_stream(self, chunks: Iterator[str]) -> str:
        box: dict = {"parts": [], "started": False, "done": False}

        def pull():
            try:
                for c in chunks:
                    box["parts"].append(c)
                    box["started"] = True
            except BaseException as e:  # surfaced after the live region closes
                box["err"] = e
            finally:
                box["done"] = True

        th = threading.Thread(target=pull, daemon=True)
        t0 = time.time()
        th.start()
        with Live(console=console, refresh_per_second=12, transient=True) as live:
            tick = 0
            while not box["done"] or box["parts"]:
                if box["started"]:
                    # First token arrived: show the answer growing live.
                    live.update(Markdown("".join(box["parts"])))
                else:
                    # Still waiting on the backend: emerald thinking crest.
                    live.update(Text.from_markup(crest_frame(tick, int(time.time() - t0))))
                tick += 1
                if box["done"] and box["parts"]:
                    break
                time.sleep(0.08)
        th.join()

        if "err" in box:
            raise box["err"]
        text = "".join(box["parts"])
        if text:
            console.print(Markdown(text))
        return text
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_render_rich.py -v`
Expected: PASS (all four tests, including the two original).

- [ ] **Step 5: Commit**

```bash
git add crowe_mycelium/render/rich.py tests/test_render_rich.py
git commit -m "feat(render): live token streaming — crest until first token, then growing markdown"
```

---

### Task 5: Local quality nudge — raise truncating defaults

**Files:**
- Modify: `crowe_mycelium/model.py:142-143`
- Test: `tests/test_backend_local.py` (add case)

- [ ] **Step 1: Add failing test**

Append to `tests/test_backend_local.py`:

```python
def test_local_defaults_are_not_truncating(monkeypatch):
    import crowe_mycelium.model as m

    captured = {}

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": "ok"}}

    def fake_post(url, json, timeout):
        captured["options"] = json["options"]
        return FakeResp()

    monkeypatch.setattr(m.httpx, "post", fake_post)
    list(m.stream_chat([{"role": "user", "content": "hi"}]))
    # A full cultivation answer must not be cut off at 160 tokens / 1024 ctx.
    assert captured["options"]["num_predict"] >= 512
    assert captured["options"]["num_ctx"] >= 2048
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_backend_local.py::test_local_defaults_are_not_truncating -v`
Expected: FAIL — current defaults are `num_predict=160`, `num_ctx=1024`.

- [ ] **Step 3: Raise the defaults in `crowe_mycelium/model.py`**

In `stream_chat`, change lines 142-143:

```python
            "num_ctx": _int_env("CROWE_MYCELIUM_NUM_CTX", 2048, 512),
            "num_predict": _int_env("CROWE_MYCELIUM_NUM_PREDICT", 512, 32),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_backend_local.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add crowe_mycelium/model.py tests/test_backend_local.py
git commit -m "fix(local): raise num_predict/num_ctx defaults so answers aren't truncated"
```

---

### Task 6: Paste-safe input module (`prompt.py`)

**Files:**
- Create: `crowe_mycelium/prompt.py`
- Test: `tests/test_prompt.py` (Create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_prompt.py
from crowe_mycelium import prompt


def test_slash_commands_cover_all_repl_commands():
    cmds = set(prompt.slash_commands())
    assert {"/local", "/cloud", "/auto", "/info", "/reset", "/doctor", "/help", "/quit"} <= cmds


def test_read_input_non_tty_falls_back_to_builtin_input(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    monkeypatch.setattr("builtins.input", lambda *_: "piped line")
    # session is unused on the non-TTY path; pass a sentinel to prove it.
    out = prompt.read_input(session=None, tag="[cloud] ▸ ")
    assert out == "piped line"


def test_read_input_tty_uses_session_prompt(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    class FakeSession:
        def __init__(self):
            self.called_with = None

        def prompt(self, message):
            self.called_with = message
            return "typed line"

    s = FakeSession()
    out = prompt.read_input(session=s, tag="[cloud] ▸ ")
    assert out == "typed line"
    assert "[cloud]" in str(s.called_with)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_prompt.py -v`
Expected: FAIL — `crowe_mycelium/prompt.py` does not exist.

- [ ] **Step 3: Create `crowe_mycelium/prompt.py`**

```python
"""Paste-safe REPL input via prompt-toolkit.

Bare console.input() reads line-at-a-time, so a multi-line paste gets shredded
and the prompt tag interleaves into the captured text. A prompt-toolkit
PromptSession captures a bracketed paste as one submission, offers slash-command
completion, and keeps per-session history. Non-TTY (piped) input falls back to
builtin input() so `run`/pipes keep working.
"""

from __future__ import annotations

import sys

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import InMemoryHistory

from crowe_mycelium.session import QUIT, SIMPLE, SWITCH


def slash_commands() -> list[str]:
    """All REPL slash commands, derived from the dispatcher (single source)."""
    cmds = set(SWITCH) | set(SIMPLE) | set(QUIT)
    return sorted(cmds)


def build_session() -> PromptSession:
    completer = WordCompleter(slash_commands(), sentence=False)
    return PromptSession(completer=completer, history=InMemoryHistory())


def read_input(session, tag: str) -> str:
    """Read one user submission. TTY → prompt-toolkit session; else builtin input."""
    if not sys.stdin.isatty():
        return input()
    return session.prompt(tag)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_prompt.py -v`
Expected: PASS (all three).

- [ ] **Step 5: Commit**

```bash
git add crowe_mycelium/prompt.py tests/test_prompt.py
git commit -m "feat(prompt): paste-safe prompt-toolkit input + slash completion + history"
```

---

### Task 7: Wire `prompt.read_input` into the chat loop

**Files:**
- Modify: `crowe_mycelium/cli.py:58-69`

- [ ] **Step 1: Build the session and swap the input call**

In `crowe_mycelium/cli.py`, add the import near the top imports:

```python
from crowe_mycelium import prompt as _prompt
```

In `_chat_loop`, after `renderer = RichRenderer()` (line ~62), add:

```python
    session = _prompt.build_session()
```

Replace the input block (lines ~67-69):

```python
        try:
            tag = branding.backend_tag(getattr(backend, "label", settings.backend))
            user_msg = console.input(f"{tag} {branding.user_prefix()}▸ ").strip()
        except (EOFError, KeyboardInterrupt):
```

with:

```python
        try:
            label = getattr(backend, "label", settings.backend)
            user_msg = _prompt.read_input(session, f"[{label}] ▸ ").strip()
        except (EOFError, KeyboardInterrupt):
```

- [ ] **Step 2: Verify piped input still works (integration)**

Run: `printf 'co2 for oyster?\n/quit\n' | .venv/bin/python -m crowe_mycelium.cli --local chat`
Expected: produces an answer then exits cleanly (non-TTY fallback path; no traceback). If local Ollama is down this may error on the backend — that's fine, the point is the input path doesn't crash on the paste/tag handling.

- [ ] **Step 3: Run the CLI test suite**

Run: `.venv/bin/python -m pytest tests/test_cli.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add crowe_mycelium/cli.py
git commit -m "feat(cli): paste-safe REPL input via prompt-toolkit session"
```

---

### Task 8: Block wordmark + status HUD (`wordmark.py`)

**Files:**
- Create: `crowe_mycelium/wordmark.py`
- Test: `tests/test_wordmark.py` (Create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_wordmark.py
from crowe_mycelium import wordmark


def test_wide_terminal_gets_multiline_wordmark():
    art = wordmark.render_hero(width=80, backend_label="cloud · modal")
    plain = art.plain if hasattr(art, "plain") else str(art)
    assert plain.count("\n") >= 3  # block wordmark spans multiple lines


def test_narrow_terminal_gets_compact_fallback():
    art = wordmark.render_hero(width=40, backend_label="cloud · modal")
    plain = art.plain if hasattr(art, "plain") else str(art)
    assert "Crowe" in plain and "Mycelium" in plain
    assert plain.count("\n") <= 2  # compact, not the full block


def test_hud_shows_backend_model_version():
    line = wordmark.hud(backend_label="cloud · modal", version="0.3.0")
    plain = line.plain if hasattr(line, "plain") else str(line)
    assert "cloud · modal" in plain
    assert "gemma-4-mycelium-e4b" in plain
    assert "0.3.0" in plain
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_wordmark.py -v`
Expected: FAIL — `crowe_mycelium/wordmark.py` does not exist.

- [ ] **Step 3: Create `crowe_mycelium/wordmark.py`**

```python
"""Block wordmark + status HUD — peer branding with crowe-logic / deepparallel.

Wide terminals get a multi-line emerald block wordmark; narrow terminals fall
back to a compact one-line mark. The HUD shows the always-visible context:
backend, model, GPU, version.
"""

from __future__ import annotations

from rich.text import Text

EMERALD = "green3"
EMERALD_BRIGHT = "bright_green"
DIM = "grey50"
MARK = "◆"
MODEL_NAME = "gemma-4-mycelium-e4b"
CLOUD_GPU = "L4"
NARROW_THRESHOLD = 56  # below this, use the compact mark

# Box-drawing wordmark for "MYCELIUM". Hand-aligned; tweak freely — tests assert
# line count / compact fallback, not exact glyphs.
_WORDMARK = (
    "╔╦╗╦ ╦╔═╗╔═╗╦  ╦╦ ╦╔╦╗\n"
    "║║║╚╦╝║  ║╣ ║  ║║ ║║║║\n"
    "╩ ╩ ╩ ╚═╝╚═╝╩═╝╩╚═╝╩ ╩"
)


def render_hero(width: int, backend_label: str) -> Text:
    """The startup hero: block wordmark (wide) or compact mark (narrow)."""
    if width < NARROW_THRESHOLD:
        t = Text()
        t.append(f"{MARK} ", style=EMERALD_BRIGHT)
        t.append("Crowe ", style=f"bold {EMERALD_BRIGHT}")
        t.append("Mycelium", style=f"bold {EMERALD}")
        t.append("  · cultivation", style=DIM)
        return t

    t = Text()
    t.append("◆ Crowe Logic\n", style=f"bold {EMERALD_BRIGHT}")
    t.append(_WORDMARK, style=f"bold {EMERALD}")
    t.append("\n  cultivation intelligence", style=DIM)
    return t


def hud(backend_label: str, version: str, gpu: str = CLOUD_GPU) -> Text:
    """Always-visible status line: backend · model · gpu · version."""
    t = Text()
    t.append("backend ", style=DIM)
    t.append(backend_label, style="white")
    t.append(f" ({gpu})", style=DIM)
    t.append("   ·   model ", style=DIM)
    t.append(MODEL_NAME, style="white")
    t.append("   ·   ", style=DIM)
    t.append(f"v{version}", style=DIM)
    return t
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_wordmark.py -v`
Expected: PASS (all three).

- [ ] **Step 5: Commit**

```bash
git add crowe_mycelium/wordmark.py tests/test_wordmark.py
git commit -m "feat(brand): block wordmark + status HUD with narrow-terminal fallback"
```

---

### Task 9: Wire wordmark + HUD into chat start

**Files:**
- Modify: `crowe_mycelium/cli.py:64` (chat start banner)
- Modify: `crowe_mycelium/branding.py` (turn separator helper)

- [ ] **Step 1: Add a turn-separator helper to `branding.py`**

Append to `crowe_mycelium/branding.py`:

```python
def turn_separator() -> None:
    """A thin dim rule between turns so the transcript doesn't read as a wall."""
    console.print(f"[{DIM}]" + "─" * 24 + "[/]")
```

- [ ] **Step 2: Show wordmark + HUD on chat start**

In `crowe_mycelium/cli.py`, add the import:

```python
from crowe_mycelium import wordmark as _wordmark
```

In `_chat_loop`, replace the hero line (line ~64):

```python
    console.print(branding.hero(getattr(backend, "label", settings.backend)))
```

with:

```python
    label = getattr(backend, "label", settings.backend)
    console.print(_wordmark.render_hero(console.width, label))
    console.print(_wordmark.hud(label, __version__))
    console.print()
```

(`__version__` and `console` are already imported in `cli.py`.)

- [ ] **Step 3: Add a turn separator after each answer**

In `_chat_loop`, after the `history.append(("assistant", reply))` line (~106), add:

```python
        branding.turn_separator()
```

- [ ] **Step 4: Run the CLI + branding tests**

Run: `.venv/bin/python -m pytest tests/test_cli.py tests/test_branding.py -v`
Expected: PASS. (If a test asserts the exact old hero text, update it to assert the HUD instead — it should check `wordmark.hud(...)` content, not the removed `branding.hero` line.)

- [ ] **Step 5: Live visual check**

Run: `printf '/quit\n' | .venv/bin/python -m crowe_mycelium.cli --cloud chat`
Expected: shows `◆ Crowe Logic` + block wordmark + HUD line (`backend cloud · modal (L4) · model gemma-4-mycelium-e4b · v0.3.0`), then exits.

- [ ] **Step 6: Commit**

```bash
git add crowe_mycelium/cli.py crowe_mycelium/branding.py tests/test_cli.py tests/test_branding.py
git commit -m "feat(cli): wordmark + status HUD on chat start; turn separators"
```

---

### Task 10: Version bump + full verification

**Files:**
- Modify: `pyproject.toml`, `crowe_mycelium/__init__.py`

- [ ] **Step 1: Bump version to 0.3.0**

In `crowe_mycelium/__init__.py` set `__version__ = "0.3.0"`. In `pyproject.toml` set `version = "0.3.0"`.

- [ ] **Step 2: Full suite green**

Run: `.venv/bin/python -m pytest -q`
Expected: all tests pass (≥ the prior 43, plus the new system_prompt / prompt / wordmark / render / local cases).

- [ ] **Step 3: Lint clean**

Run: `.venv/bin/python -m ruff check crowe_mycelium tests scripts && .venv/bin/python -m ruff format --check crowe_mycelium tests`
Expected: "All checks passed!" (run `ruff format` to fix any formatting, then re-check).

- [ ] **Step 4: End-to-end acceptance (live, real terminal)**

Confirm each acceptance criterion from the spec §9:
1. `what are you?` → Crowe-first, no Gemma blurt.
2. Multi-turn (`lions mane` → follow-up) retains context.
3. Tool request → instant honest decline, no 86 s hang.
4. Multi-line paste → one submission, no tag interleave.
5. Answers stream token-by-token.
6. Wordmark + HUD on start; narrow terminal → compact.
7. `run "…" | cat` → clean plain output.
8. Modal reports L4; warm answer materially faster than T4.
9. `built with Gemma` footer + `/info` attribution intact.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml crowe_mycelium/__init__.py
git commit -m "chore: bump to 0.3.0 — Phase 1.5a quality & brand foundation"
```

---

## Self-Review notes

- **Spec coverage:** §4.1 → T1; §4.2 (messages/stream/L4) → T2+T3; §5 (paste input) → T6+T7; §6 (wordmark/HUD/separator) → T8+T9; §7 folded-in (serve inherits via T2, local nudge T5, streaming-renderer T4); §9 acceptance → T10 Step 4. All covered.
- **Type consistency:** `CloudModalBackend(caller=…)` signature `(messages, temperature) -> Iterator[str]` is used identically in T2 test and impl; `render_hero(width, backend_label)` and `hud(backend_label, version, gpu=…)` match between T8 impl and test; `read_input(session, tag)` matches T6 test and T7 wiring; `slash_commands()` derives from `session.QUIT/SIMPLE/SWITCH` (no drift).
- **Modal API:** generator functions are consumed with `.remote_gen(...)` (T2 impl, T3 fn). Verified against the existing `.remote()` usage being replaced.
- **Known live-only risks** (carried from spec §10): Ollama per-request system precedence (T3 Step 5 hedge), generator streaming latency on L4, prompt-toolkit/Rich coexistence — each has a verification step.
