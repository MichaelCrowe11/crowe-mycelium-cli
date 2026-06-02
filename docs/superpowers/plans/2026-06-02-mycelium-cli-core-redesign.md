# Crowe Mycelium CLI — Core Peer Redesign (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring `crowe-mycelium` to full peer with `crowe-logic`/`deepparallel` — a Backend abstraction (local Ollama / Modal cloud / `auto` cloud-first), a Renderer abstraction (Plain/Rich), the emerald design language, and `doctor`/`serve` — folding the `crowelm-mycelium`/`crowelm-cloud` scripts into one tool.

**Architecture:** Evolve the existing `crowe_mycelium` package. Two ABCs — `Backend` (`stream_chat`/`health`) and `Renderer` (`render_stream`/`notice`/`error`) — keep the REPL UI-agnostic and backend-agnostic. `AutoBackend` does cloud-first→local fallback and reserves an `escalate` seam for the Phase 5 hybrid brain. The cloud backend calls the deployed `crowe-mycelium-serve` Modal `smoke` function (account-auth, no token).

**Tech Stack:** Python ≥3.10, Click, Rich, httpx, python-dotenv, `modal` (cloud backend), pytest + ruff (dev). Spec: `docs/superpowers/specs/2026-06-02-mycelium-cli-core-redesign-design.md`.

---

## File structure

| File | Responsibility |
|------|----------------|
| `pyproject.toml` | add pytest/ruff dev deps + pytest config (modify) |
| `tests/conftest.py` | shared `FakeBackend` + fixtures (create) |
| `crowe_mycelium/backends/base.py` | `Backend` ABC (create) |
| `crowe_mycelium/backends/local.py` | `LocalOllamaBackend` (create) |
| `crowe_mycelium/backends/cloud.py` | `CloudModalBackend` (create) |
| `crowe_mycelium/backends/router.py` | `AutoBackend` + escalation seam (create) |
| `crowe_mycelium/backends/__init__.py` | `build_backend()` factory (create) |
| `crowe_mycelium/config.py` | `Settings` + `resolve_settings()` (create) |
| `crowe_mycelium/render/base.py` | `Renderer` ABC (create) |
| `crowe_mycelium/render/plain.py` | `PlainRenderer` (create) |
| `crowe_mycelium/render/thinking.py` | emerald crest frame generator (create) |
| `crowe_mycelium/render/rich.py` | `RichRenderer` (create) |
| `crowe_mycelium/branding.py` | ◆ mark, emerald palette, hero/footer/tag (modify) |
| `crowe_mycelium/session.py` | slash-command dispatch (create) |
| `crowe_mycelium/cli.py` | rewire commands + routing + plain-when-piped + `doctor` + `chat --idle` (modify) |
| `~/.local/bin/crowelm-cloud`, `~/.local/bin/crowelm-mycelium` | thin shims (modify) |
| `README.md` | Gemma attribution surface stays accurate (modify, final) |

`model.py`, `provenance.py`, `registry.json`, `system_prompt.txt` are reused as-is. `model.py:stream_chat()` already yields the full answer as one chunk; both backends keep that contract (renderers handle one-or-many chunks identically).

---

## Task 0: Dev tooling + test infrastructure

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/conftest.py`, `tests/__init__.py`

- [ ] **Step 1: Add dev deps + pytest config to `pyproject.toml`**

Append after the `[project.scripts]` block:

```toml
[project.optional-dependencies]
dev = ["pytest>=8.0.0", "ruff>=0.6.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"

[tool.ruff]
line-length = 100
target-version = "py310"
```

- [ ] **Step 2: Create `tests/__init__.py`** (empty file)

```python
```

- [ ] **Step 3: Create `tests/conftest.py` with a shared FakeBackend**

```python
from __future__ import annotations

from typing import Iterator

import pytest

from crowe_mycelium.backends.base import Backend


class FakeBackend(Backend):
    """Deterministic backend for tests — no network, no Ollama, no Modal."""

    def __init__(self, name="fake", chunks=None, healthy=True, fail=False):
        self.name = name
        self.label = f"{name} · test"
        self._chunks = chunks if chunks is not None else ["hello"]
        self._healthy = healthy
        self._fail = fail
        self.calls: list[list[dict]] = []

    def stream_chat(self, messages, temperature: float = 0.4) -> Iterator[str]:
        self.calls.append(messages)
        if self._fail:
            raise RuntimeError("boom")
        for c in self._chunks:
            yield c

    def health(self) -> bool:
        return self._healthy


@pytest.fixture
def fake_backend():
    return FakeBackend
```

- [ ] **Step 4: Install dev deps**

Run: `cd ~/Projects/crowe-mycelium-cli && uv pip install -e ".[dev]"`
Expected: installs pytest + ruff into the active env.

- [ ] **Step 5: Verify pytest collects (0 tests is fine)**

Run: `cd ~/Projects/crowe-mycelium-cli && python -m pytest`
Expected: `no tests ran` (exit 5) — confirms config is valid. (`tests/conftest.py` imports `Backend`, which doesn't exist yet, so this will error on import. That's expected; it passes after Task 1.)

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml tests/__init__.py tests/conftest.py
git commit -m "chore: add pytest+ruff dev tooling and test scaffold"
```

---

## Task 1: Backend ABC

**Files:**
- Create: `crowe_mycelium/backends/__init__.py`, `crowe_mycelium/backends/base.py`
- Test: `tests/test_backend_base.py`

- [ ] **Step 1: Create empty `crowe_mycelium/backends/__init__.py`** (factory added in Task 5)

```python
```

- [ ] **Step 2: Write the failing test** — `tests/test_backend_base.py`

```python
import pytest

from crowe_mycelium.backends.base import Backend
from tests.conftest import FakeBackend


def test_backend_is_abstract():
    with pytest.raises(TypeError):
        Backend()  # cannot instantiate the ABC directly


def test_fake_backend_satisfies_interface():
    b = FakeBackend(name="x", chunks=["a", "b"])
    assert b.health() is True
    assert list(b.stream_chat([{"role": "user", "content": "hi"}])) == ["a", "b"]
    assert b.name == "x"
    assert b.label == "x · test"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_backend_base.py -v`
Expected: FAIL — `ModuleNotFoundError: crowe_mycelium.backends.base`

- [ ] **Step 4: Implement `crowe_mycelium/backends/base.py`**

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator


class Backend(ABC):
    """A source of chat completions. Local, cloud, and (Phase 5) borrowed-brain
    backends are interchangeable behind this interface."""

    name: str = "backend"
    label: str = "backend"

    @abstractmethod
    def stream_chat(self, messages: list[dict], temperature: float = 0.4) -> Iterator[str]:
        """Yield answer text. Implementations MAY yield a single full chunk."""
        raise NotImplementedError

    @abstractmethod
    def health(self) -> bool:
        """Return True if this backend can currently serve a request."""
        raise NotImplementedError
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_backend_base.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add crowe_mycelium/backends/__init__.py crowe_mycelium/backends/base.py tests/test_backend_base.py
git commit -m "feat(backends): add Backend ABC"
```

---

## Task 2: LocalOllamaBackend

**Files:**
- Create: `crowe_mycelium/backends/local.py`
- Test: `tests/test_backend_local.py`

- [ ] **Step 1: Write the failing test** — `tests/test_backend_local.py`

```python
from crowe_mycelium.backends import local as local_mod
from crowe_mycelium.backends.local import LocalOllamaBackend


def test_local_streams_via_model(monkeypatch):
    monkeypatch.setattr(local_mod._model, "stream_chat",
                        lambda messages, temperature=0.4: iter(["600-1200 ppm"]))
    b = LocalOllamaBackend()
    assert b.name == "local"
    assert list(b.stream_chat([{"role": "user", "content": "co2?"}])) == ["600-1200 ppm"]


def test_local_health_reflects_check_backend(monkeypatch):
    monkeypatch.setattr(local_mod._model, "check_backend", lambda: (True, "ok"))
    assert LocalOllamaBackend().health() is True
    monkeypatch.setattr(local_mod._model, "check_backend", lambda: (False, "down"))
    assert LocalOllamaBackend().health() is False


def test_local_store_hint_when_elements_absent(monkeypatch, tmp_path):
    b = LocalOllamaBackend(store=str(tmp_path / "nope"))
    assert "Elements" in b.store_hint()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_backend_local.py -v`
Expected: FAIL — `ModuleNotFoundError: crowe_mycelium.backends.local`

- [ ] **Step 3: Implement `crowe_mycelium/backends/local.py`**

```python
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

from crowe_mycelium import model as _model
from crowe_mycelium.backends.base import Backend

DEFAULT_STORE = "/Volumes/Elements/ollama-models"


class LocalOllamaBackend(Backend):
    """Local Ollama. Model blobs commonly live on the Elements drive."""

    name = "local"
    label = "local · offline"

    def __init__(self, store: str | None = None):
        self._store = store or os.environ.get("CROWE_MYCELIUM_OLLAMA_STORE", DEFAULT_STORE)

    def health(self) -> bool:
        ok, _ = _model.check_backend()
        return ok

    def stream_chat(self, messages, temperature: float = 0.4) -> Iterator[str]:
        yield from _model.stream_chat(messages, temperature=temperature)

    def store_readable(self) -> bool:
        """An I/O touch (not just exists()): catches a stale/unmounted drive."""
        try:
            blobs = Path(self._store, "blobs")
            return blobs.is_dir() and any(blobs.iterdir())
        except Exception:
            return False

    def store_hint(self) -> str:
        if self.store_readable():
            return f"Elements model store OK ({self._store})"
        return (f"Elements model store not readable ({self._store}). "
                f"Plug in / re-seat the drive, or ensure Ollama has the model pulled.")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_backend_local.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add crowe_mycelium/backends/local.py tests/test_backend_local.py
git commit -m "feat(backends): add LocalOllamaBackend with Elements guard"
```

---

## Task 3: CloudModalBackend

**Files:**
- Create: `crowe_mycelium/backends/cloud.py`
- Test: `tests/test_backend_cloud.py`

- [ ] **Step 1: Write the failing test** — `tests/test_backend_cloud.py`

```python
from crowe_mycelium.backends.cloud import CloudModalBackend, flatten_messages


def test_flatten_uses_last_user_and_includes_history():
    msgs = [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "ans1"},
        {"role": "user", "content": "second"},
    ]
    out = flatten_messages(msgs)
    assert "SYS" not in out  # system is baked into the cloud model
    assert "first" in out and "ans1" in out and "second" in out
    assert out.rstrip().endswith("second")


def test_cloud_streams_one_chunk_via_injected_caller():
    captured = {}
    b = CloudModalBackend(caller=lambda p: captured.setdefault("p", p) or "cloud answer")
    out = list(b.stream_chat([{"role": "user", "content": "hi"}]))
    assert out == ["cloud answer"]
    assert "hi" in captured["p"]


def test_cloud_health_false_when_caller_lookup_raises():
    def boom():
        raise RuntimeError("no modal")
    b = CloudModalBackend(health_probe=boom)
    assert b.health() is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_backend_cloud.py -v`
Expected: FAIL — `ModuleNotFoundError: crowe_mycelium.backends.cloud`

- [ ] **Step 3: Implement `crowe_mycelium/backends/cloud.py`**

```python
from __future__ import annotations

from typing import Callable, Iterator, Optional

from crowe_mycelium.backends.base import Backend


def flatten_messages(messages: list[dict]) -> str:
    """Render non-system turns into one prompt string.

    The deployed cloud model has the mycology system prompt baked in, and the
    `smoke` function takes a single prompt, so we drop the system message and
    serialize the conversation (gives the cloud path basic memory)."""
    lines: list[str] = []
    for m in messages:
        role = m.get("role")
        if role == "system":
            continue
        speaker = "User" if role == "user" else "Assistant"
        lines.append(f"{speaker}: {m.get('content', '')}")
    return "\n".join(lines)


class CloudModalBackend(Backend):
    """Calls the deployed `crowe-mycelium-serve` Modal `smoke` function
    (account-auth via the Modal SDK — no proxy-auth token needed)."""

    name = "cloud"
    label = "cloud · modal"

    def __init__(self, app: str = "crowe-mycelium-serve", func: str = "smoke",
                 caller: Optional[Callable[[str], str]] = None,
                 health_probe: Optional[Callable[[], object]] = None):
        self._app = app
        self._func = func
        self._caller = caller          # injectable for tests
        self._health_probe = health_probe

    def _lookup(self):
        import modal  # lazy: keep CLI startup fast and modal optional
        return modal.Function.from_name(self._app, self._func)

    def stream_chat(self, messages, temperature: float = 0.4) -> Iterator[str]:
        prompt = flatten_messages(messages)
        if self._caller is not None:
            yield self._caller(prompt)
            return
        yield self._lookup().remote(prompt)

    def health(self) -> bool:
        probe = self._health_probe or self._lookup
        try:
            probe()
            return True
        except Exception:
            return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_backend_cloud.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Add `modal` to runtime deps in `pyproject.toml`**

In the `dependencies = [...]` list, add:

```toml
    "modal>=1.0.0",
```

- [ ] **Step 6: Commit**

```bash
git add crowe_mycelium/backends/cloud.py tests/test_backend_cloud.py pyproject.toml
git commit -m "feat(backends): add CloudModalBackend (smoke fn, account-auth)"
```

---

## Task 4: AutoBackend router (cloud-first → local, escalation seam)

**Files:**
- Create: `crowe_mycelium/backends/router.py`
- Test: `tests/test_router.py`

- [ ] **Step 1: Write the failing test** — `tests/test_router.py`

```python
import pytest

from crowe_mycelium.backends.router import AutoBackend
from tests.conftest import FakeBackend


def _msgs():
    return [{"role": "user", "content": "hi"}]


def test_auto_prefers_cloud_when_healthy():
    cloud = FakeBackend(name="cloud", chunks=["from cloud"], healthy=True)
    local = FakeBackend(name="local", chunks=["from local"], healthy=True)
    r = AutoBackend(cloud=cloud, local=local)
    assert list(r.stream_chat(_msgs())) == ["from cloud"]
    assert r.label == "cloud · test"


def test_auto_falls_back_to_local_when_cloud_down():
    cloud = FakeBackend(name="cloud", healthy=False)
    local = FakeBackend(name="local", chunks=["from local"], healthy=True)
    r = AutoBackend(cloud=cloud, local=local)
    assert list(r.stream_chat(_msgs())) == ["from local"]
    assert r.label == "local · test"


def test_auto_raises_when_both_down():
    r = AutoBackend(cloud=FakeBackend(healthy=False), local=FakeBackend(healthy=False))
    with pytest.raises(RuntimeError, match="No backend available"):
        list(r.stream_chat(_msgs()))


def test_escalate_seam_is_stored_but_unused_in_phase1():
    esc = FakeBackend(name="forge")
    r = AutoBackend(cloud=FakeBackend(), local=FakeBackend(), escalate=esc)
    assert r.escalate is esc  # reserved for Phase 5; not routed to yet
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_router.py -v`
Expected: FAIL — `ModuleNotFoundError: crowe_mycelium.backends.router`

- [ ] **Step 3: Implement `crowe_mycelium/backends/router.py`**

```python
from __future__ import annotations

from typing import Iterator, Optional

from crowe_mycelium.backends.base import Backend


class AutoBackend(Backend):
    """Cloud-first, local fallback. `escalate` is the Phase 5 hybrid-brain seam:
    a future router rule will hand coding/agentic prompts to it; unused now."""

    name = "auto"

    def __init__(self, cloud: Backend, local: Backend, escalate: Optional[Backend] = None):
        self.cloud = cloud
        self.local = local
        self.escalate = escalate
        self._active: Optional[Backend] = None

    @property
    def label(self) -> str:
        return self._active.label if self._active else "auto · cloud-first"

    def _choose(self) -> Optional[Backend]:
        if self.cloud.health():
            return self.cloud
        if self.local.health():
            return self.local
        return None

    def health(self) -> bool:
        return self.cloud.health() or self.local.health()

    def stream_chat(self, messages, temperature: float = 0.4) -> Iterator[str]:
        chosen = self._choose()
        if chosen is None:
            raise RuntimeError(
                "No backend available: cloud unreachable and local (Elements/Ollama) "
                "is down. Plug in Elements, or check the Modal app "
                "(`modal app list | grep mycel`)."
            )
        self._active = chosen
        yield from chosen.stream_chat(messages, temperature=temperature)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_router.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add crowe_mycelium/backends/router.py tests/test_router.py
git commit -m "feat(backends): add AutoBackend cloud-first router + escalate seam"
```

---

## Task 5: Settings + backend factory

**Files:**
- Create: `crowe_mycelium/config.py`
- Modify: `crowe_mycelium/backends/__init__.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test** — `tests/test_config.py`

```python
from crowe_mycelium.config import Settings, resolve_settings
from crowe_mycelium.backends import build_backend
from crowe_mycelium.backends.router import AutoBackend
from crowe_mycelium.backends.local import LocalOllamaBackend
from crowe_mycelium.backends.cloud import CloudModalBackend


def test_default_backend_is_auto(monkeypatch):
    monkeypatch.delenv("CROWE_MYCELIUM_BACKEND", raising=False)
    assert resolve_settings().backend == "auto"


def test_explicit_arg_overrides_env(monkeypatch):
    monkeypatch.setenv("CROWE_MYCELIUM_BACKEND", "cloud")
    assert resolve_settings(backend="local").backend == "local"


def test_invalid_backend_falls_back_to_auto(monkeypatch):
    monkeypatch.setenv("CROWE_MYCELIUM_BACKEND", "banana")
    assert resolve_settings().backend == "auto"


def test_factory_builds_right_type():
    assert isinstance(build_backend(Settings(backend="local")), LocalOllamaBackend)
    assert isinstance(build_backend(Settings(backend="cloud")), CloudModalBackend)
    assert isinstance(build_backend(Settings(backend="auto")), AutoBackend)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: crowe_mycelium.config`

- [ ] **Step 3: Implement `crowe_mycelium/config.py`**

```python
from __future__ import annotations

import os
from dataclasses import dataclass

VALID_BACKENDS = {"auto", "local", "cloud"}


@dataclass(frozen=True)
class Settings:
    backend: str = "auto"
    temperature: float = 0.4
    cloud_app: str = "crowe-mycelium-serve"
    cloud_func: str = "smoke"


def resolve_settings(backend: str | None = None, temperature: float | None = None) -> Settings:
    """Priority: explicit arg > env > default."""
    be = backend or os.environ.get("CROWE_MYCELIUM_BACKEND", "auto")
    if be not in VALID_BACKENDS:
        be = "auto"
    if temperature is not None:
        temp = temperature
    else:
        try:
            temp = float(os.environ.get("CROWE_MYCELIUM_TEMPERATURE", "0.4"))
        except ValueError:
            temp = 0.4
    return Settings(
        backend=be,
        temperature=temp,
        cloud_app=os.environ.get("CROWE_MYCELIUM_CLOUD_APP", "crowe-mycelium-serve"),
        cloud_func=os.environ.get("CROWE_MYCELIUM_CLOUD_FUNC", "smoke"),
    )
```

- [ ] **Step 4: Implement the factory in `crowe_mycelium/backends/__init__.py`**

```python
from __future__ import annotations

from crowe_mycelium.backends.base import Backend
from crowe_mycelium.backends.cloud import CloudModalBackend
from crowe_mycelium.backends.local import LocalOllamaBackend
from crowe_mycelium.backends.router import AutoBackend


def build_backend(settings) -> Backend:
    """Construct the Backend for the resolved settings."""
    local = LocalOllamaBackend()
    cloud = CloudModalBackend(app=settings.cloud_app, func=settings.cloud_func)
    if settings.backend == "local":
        return local
    if settings.backend == "cloud":
        return cloud
    return AutoBackend(cloud=cloud, local=local)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
git add crowe_mycelium/config.py crowe_mycelium/backends/__init__.py tests/test_config.py
git commit -m "feat(config): Settings, env>arg resolution, backend factory"
```

---

## Task 6: Renderer ABC + PlainRenderer

**Files:**
- Create: `crowe_mycelium/render/__init__.py`, `crowe_mycelium/render/base.py`, `crowe_mycelium/render/plain.py`
- Test: `tests/test_render_plain.py`

- [ ] **Step 1: Create empty `crowe_mycelium/render/__init__.py`**

```python
```

- [ ] **Step 2: Write the failing test** — `tests/test_render_plain.py`

```python
from crowe_mycelium.render.plain import PlainRenderer


def test_plain_writes_answer_to_stdout(capsys):
    out = PlainRenderer().render_stream(iter(["600-", "1200 ppm"]))
    captured = capsys.readouterr()
    assert out == "600-1200 ppm"
    assert "600-1200 ppm" in captured.out
    assert captured.err == ""


def test_plain_diagnostics_go_to_stderr(capsys):
    r = PlainRenderer()
    r.notice("switched to local")
    r.error("cloud down")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "switched to local" in captured.err
    assert "error: cloud down" in captured.err
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_render_plain.py -v`
Expected: FAIL — `ModuleNotFoundError: crowe_mycelium.render.plain`

- [ ] **Step 4: Implement `crowe_mycelium/render/base.py`**

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator


class Renderer(ABC):
    """Turns a token stream into output. Plain for pipes, Rich for terminals."""

    @abstractmethod
    def render_stream(self, chunks: Iterator[str]) -> str:
        """Render the stream and return the full accumulated text."""
        raise NotImplementedError

    @abstractmethod
    def notice(self, msg: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def error(self, msg: str) -> None:
        raise NotImplementedError
```

- [ ] **Step 5: Implement `crowe_mycelium/render/plain.py`**

```python
from __future__ import annotations

import sys
from typing import Iterator

from crowe_mycelium.render.base import Renderer


class PlainRenderer(Renderer):
    """Pipe-safe: answer to stdout, diagnostics to stderr, no chrome."""

    def render_stream(self, chunks: Iterator[str]) -> str:
        parts: list[str] = []
        for c in chunks:
            sys.stdout.write(c)
            sys.stdout.flush()
            parts.append(c)
        sys.stdout.write("\n")
        sys.stdout.flush()
        return "".join(parts)

    def notice(self, msg: str) -> None:
        print(msg, file=sys.stderr)

    def error(self, msg: str) -> None:
        print(f"error: {msg}", file=sys.stderr)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_render_plain.py -v`
Expected: PASS (2 passed)

- [ ] **Step 7: Commit**

```bash
git add crowe_mycelium/render/__init__.py crowe_mycelium/render/base.py crowe_mycelium/render/plain.py tests/test_render_plain.py
git commit -m "feat(render): Renderer ABC + pipe-safe PlainRenderer"
```

---

## Task 7: Thinking crest + RichRenderer

**Files:**
- Create: `crowe_mycelium/render/thinking.py`, `crowe_mycelium/render/rich.py`
- Test: `tests/test_render_rich.py`

- [ ] **Step 1: Write the failing test** — `tests/test_render_rich.py`

```python
from crowe_mycelium.render.thinking import crest_frame, PALETTE
from crowe_mycelium.render.rich import RichRenderer


def test_crest_frame_shows_elapsed_and_cycles_color():
    f0 = crest_frame(0, 3)
    assert "thinking" in f0 and "3s" in f0
    assert PALETTE[0] in f0
    assert crest_frame(1, 3) != f0  # spinner/color advances


def test_rich_render_returns_full_text():
    # RichRenderer must still return the accumulated answer (used for history).
    out = RichRenderer().render_stream(iter(["**bold** answer"]))
    assert out == "**bold** answer"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_render_rich.py -v`
Expected: FAIL — `ModuleNotFoundError: crowe_mycelium.render.thinking`

- [ ] **Step 3: Implement `crowe_mycelium/render/thinking.py`**

```python
from __future__ import annotations

# Emerald "cultivation" drift — distinct from crowe-logic gold / deepparallel cyan.
PALETTE = ["green3", "bright_green", "spring_green2", "green4", "dark_sea_green"]
_SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
MARK = "⬢"


def crest_frame(tick: int, elapsed: int) -> str:
    """Rich-markup string for one animation frame of the thinking crest."""
    spin = _SPIN[tick % len(_SPIN)]
    color = PALETTE[tick % len(PALETTE)]
    return f"[{color}]{MARK}[/] [grey50]{spin} thinking · {elapsed}s[/]"
```

- [ ] **Step 4: Implement `crowe_mycelium/render/rich.py`**

```python
from __future__ import annotations

import threading
import time
from typing import Iterator

from rich.live import Live
from rich.markdown import Markdown
from rich.text import Text

from crowe_mycelium.branding import console
from crowe_mycelium.render.base import Renderer
from crowe_mycelium.render.thinking import crest_frame


class RichRenderer(Renderer):
    """Terminal output: an emerald thinking crest while the backend works (so a
    cold/slow backend is never a silent wait), then markdown-rendered answer."""

    def render_stream(self, chunks: Iterator[str]) -> str:
        box: dict = {}

        def pull():
            try:
                box["text"] = "".join(chunks)
            except BaseException as e:  # surfaced after the crest stops
                box["err"] = e

        th = threading.Thread(target=pull, daemon=True)
        t0 = time.time()
        th.start()
        with Live(console=console, refresh_per_second=12, transient=True) as live:
            tick = 0
            while th.is_alive():
                live.update(Text.from_markup(crest_frame(tick, int(time.time() - t0))))
                tick += 1
                th.join(timeout=0.08)

        if "err" in box:
            raise box["err"]
        text = box.get("text", "")
        if text:
            console.print(Markdown(text))
        return text

    def notice(self, msg: str) -> None:
        console.print(f"[grey50]{msg}[/]")

    def error(self, msg: str) -> None:
        console.print(f"[bold red]error[/] {msg}")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_render_rich.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add crowe_mycelium/render/thinking.py crowe_mycelium/render/rich.py tests/test_render_rich.py
git commit -m "feat(render): emerald thinking crest + RichRenderer markdown"
```

---

## Task 8: Branding redesign (◆ mark, emerald palette, clean hero, dim footer)

**Files:**
- Modify: `crowe_mycelium/branding.py`
- Test: `tests/test_branding.py`

- [ ] **Step 1: Write the failing test** — `tests/test_branding.py`

```python
from rich.text import Text

from crowe_mycelium import branding


def test_hero_is_crowe_first_and_omits_gemma():
    t = branding.hero("auto · cloud-first")
    plain = t.plain if isinstance(t, Text) else str(t)
    assert "Crowe Logic" in plain
    assert "Mycelium" in plain
    assert "cultivation" in plain
    assert "Gemma" not in plain  # attribution lives in the footer, not the hero


def test_footer_text_carries_required_attribution():
    assert "built with Gemma" in branding.footer_text()


def test_backend_tag_wraps_label():
    assert "cloud · modal" in branding.backend_tag("cloud · modal")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_branding.py -v`
Expected: FAIL — `AttributeError: module 'crowe_mycelium.branding' has no attribute 'hero'`

- [ ] **Step 3: Modify `crowe_mycelium/branding.py`** — add the new palette + functions (keep `console`, `info`, `error`, `user_prefix`; replace `welcome`/`attribution_footer` usage with `hero`/`footer_text`). Add after the existing palette constants:

```python
# --- Emerald peer-design palette (Phase 1 redesign) ---
EMERALD = "green3"
EMERALD_BRIGHT = "bright_green"
DIM = "grey50"
MARK = "◆"


def hero(backend_label: str) -> Text:
    """Clean, Crowe-first welcome line. Gemma attribution is NOT here (footer)."""
    t = Text()
    t.append(f"{MARK} ", style=EMERALD_BRIGHT)
    t.append("Crowe Logic ", style=f"bold {EMERALD_BRIGHT}")
    t.append("· ", style=DIM)
    t.append("Mycelium", style=f"bold {EMERALD}")
    t.append("        cultivation", style=DIM)
    t.append(f"\n  backend: {backend_label}   ·   /help", style=DIM)
    return t


def footer_text() -> str:
    """Required Gemma attribution — rendered dim, once per session."""
    return "built with Gemma · Gemma Terms apply (https://ai.google.dev/gemma/terms)"


def footer() -> None:
    console.print(f"[{DIM}]{footer_text()}[/]")


def backend_tag(label: str) -> str:
    """Prompt tag showing the active backend, e.g. [cloud · modal]."""
    return f"[{DIM}]\\[{label}][/]"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_branding.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add crowe_mycelium/branding.py tests/test_branding.py
git commit -m "feat(branding): emerald peer design — hero, footer, backend tag"
```

---

## Task 9: Slash-command dispatch

**Files:**
- Create: `crowe_mycelium/session.py`
- Test: `tests/test_session.py`

- [ ] **Step 1: Write the failing test** — `tests/test_session.py`

```python
import pytest

from crowe_mycelium.session import dispatch_slash, SlashResult


@pytest.mark.parametrize("cmd,action", [
    ("/quit", "quit"), ("/exit", "quit"), (":q", "quit"),
    ("/help", "help"), ("/reset", "reset"), ("/info", "info"), ("/doctor", "doctor"),
])
def test_known_commands(cmd, action):
    r = dispatch_slash(cmd)
    assert r.handled and r.action == action


@pytest.mark.parametrize("cmd,arg", [("/local", "local"), ("/cloud", "cloud"), ("/auto", "auto")])
def test_switch_commands(cmd, arg):
    r = dispatch_slash(cmd)
    assert r.handled and r.action == "switch" and r.arg == arg


def test_unknown_slash_is_handled_noop():
    r = dispatch_slash("/wat")
    assert r.handled and r.action == "noop"


def test_plain_text_is_not_a_slash():
    r = dispatch_slash("how do I fruit lion's mane?")
    assert r == SlashResult(handled=False)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_session.py -v`
Expected: FAIL — `ModuleNotFoundError: crowe_mycelium.session`

- [ ] **Step 3: Implement `crowe_mycelium/session.py`**

```python
from __future__ import annotations

from dataclasses import dataclass

QUIT = {"/quit", "/exit", ":q"}
SWITCH = {"/local": "local", "/cloud": "cloud", "/auto": "auto"}
SIMPLE = {"/help": "help", "/reset": "reset", "/info": "info", "/doctor": "doctor"}


@dataclass(frozen=True)
class SlashResult:
    handled: bool
    action: str = ""
    arg: str = ""


def dispatch_slash(text: str) -> SlashResult:
    c = text.strip()
    if c in QUIT:
        return SlashResult(True, "quit")
    if c in SIMPLE:
        return SlashResult(True, SIMPLE[c])
    if c in SWITCH:
        return SlashResult(True, "switch", SWITCH[c])
    if c.startswith("/"):
        return SlashResult(True, "noop")
    return SlashResult(False)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_session.py -v`
Expected: PASS (12 passed)

- [ ] **Step 5: Commit**

```bash
git add crowe_mycelium/session.py tests/test_session.py
git commit -m "feat(session): slash-command dispatch"
```

---

## Task 10: Rewire `cli.py` (routing, plain-when-piped, REPL, chat --idle)

**Files:**
- Modify: `crowe_mycelium/cli.py` (full rewrite)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test** — `tests/test_cli.py`

```python
from click.testing import CliRunner

import crowe_mycelium.cli as climod
from crowe_mycelium.cli import main
from tests.conftest import FakeBackend


def test_run_uses_backend_and_prints_answer(monkeypatch):
    monkeypatch.setattr(climod, "build_backend",
                        lambda settings: FakeBackend(chunks=["600-1200 ppm"]))
    monkeypatch.setattr(climod, "load_system_prompt", lambda: "SYS")
    result = CliRunner().invoke(main, ["run", "co2", "for", "oyster"])
    assert result.exit_code == 0
    assert "600-1200 ppm" in result.output


def test_backend_flag_selects_local(monkeypatch):
    seen = {}
    monkeypatch.setattr(climod, "build_backend",
                        lambda settings: seen.setdefault("backend", settings.backend) or FakeBackend())
    monkeypatch.setattr(climod, "load_system_prompt", lambda: "SYS")
    CliRunner().invoke(main, ["--local", "run", "hi"])
    assert seen["backend"] == "local"


def test_models_lists_the_model():
    result = CliRunner().invoke(main, ["models"])
    assert result.exit_code == 0
    assert "Gemma 4 Mycelium" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_backend' from crowe_mycelium.cli`

- [ ] **Step 3: Rewrite `crowe_mycelium/cli.py`**

```python
#!/usr/bin/env python3
"""Crowe Mycelium CLI — cultivation intelligence on Gemma 4 Mycelium.

Backends: local Ollama, Modal cloud, or auto (cloud-first → local fallback).

    crowe-mycelium                      # interactive chat (default)
    crowe-mycelium --local chat         # force local
    crowe-mycelium run "prompt"         # one-shot (plain when piped)
    crowe-mycelium info | models | doctor
"""

from __future__ import annotations

import sys
import time

import click
from dotenv import load_dotenv
from rich import box
from rich.table import Table

from crowe_mycelium import __version__, branding
from crowe_mycelium.backends import build_backend
from crowe_mycelium.branding import console
from crowe_mycelium.config import resolve_settings
from crowe_mycelium.model import load_model_spec, load_system_prompt, ollama_host, ollama_tag
from crowe_mycelium.render.plain import PlainRenderer
from crowe_mycelium.render.rich import RichRenderer
from crowe_mycelium.session import dispatch_slash


def _settings(ctx):
    return resolve_settings(backend=ctx.obj.get("backend"), temperature=ctx.obj["temperature"])


def _build_messages(history, system, user_msg):
    msgs = [{"role": "system", "content": system}]
    for role, content in history:
        msgs.append({"role": role, "content": content})
    msgs.append({"role": "user", "content": user_msg})
    return msgs


def _print_info(spec, settings) -> None:
    table = Table(box=box.SIMPLE_HEAVY, show_header=False, pad_edge=False)
    table.add_column("k", style="grey50")
    table.add_column("v", style="white")
    table.add_row("model", spec.name)
    table.add_row("label", spec.label)
    table.add_row("base", f"{spec.base_model} (built with Gemma)")
    table.add_row("backend", settings.backend)
    table.add_row("cloud app", settings.cloud_app)
    table.add_row("ollama tag", ollama_tag())
    table.add_row("ollama host", ollama_host())
    table.add_row("context", str(spec.context_window))
    console.print(table)


def _chat_loop(ctx) -> None:
    settings = _settings(ctx)
    backend = build_backend(settings)
    system = load_system_prompt()
    renderer = RichRenderer()

    console.print(branding.hero(getattr(backend, "label", settings.backend)))
    history: list[tuple[str, str]] = []
    while True:
        try:
            tag = branding.backend_tag(getattr(backend, "label", settings.backend))
            user_msg = console.input(f"{tag} {branding.user_prefix()}▸ ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break
        if not user_msg:
            continue

        res = dispatch_slash(user_msg)
        if res.handled:
            if res.action == "quit":
                break
            if res.action == "help":
                branding.info("/local /cloud /auto · /info /reset /doctor /quit")
            elif res.action == "reset":
                history.clear()
                branding.info("conversation cleared.")
            elif res.action == "info":
                _print_info(load_model_spec(), settings)
            elif res.action == "doctor":
                _doctor_report(settings)
            elif res.action == "switch":
                settings = resolve_settings(backend=res.arg, temperature=settings.temperature)
                backend = build_backend(settings)
                branding.info(f"switched to {res.arg}.")
            else:
                branding.info("unknown command. /help")
            continue

        messages = _build_messages(history, system, user_msg)
        try:
            reply = renderer.render_stream(backend.stream_chat(messages, settings.temperature))
        except Exception as e:
            renderer.error(str(e))
            continue
        history.append(("user", user_msg))
        history.append(("assistant", reply))

    branding.footer()


def _doctor_report(settings) -> None:
    from crowe_mycelium.backends.cloud import CloudModalBackend
    from crowe_mycelium.backends.local import LocalOllamaBackend

    local = LocalOllamaBackend()
    cloud = CloudModalBackend(app=settings.cloud_app, func=settings.cloud_func)
    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("backend")
    table.add_column("status")
    table.add_column("detail")
    table.add_row("local", "ok" if local.health() else "down", local.store_hint())
    table.add_row("cloud", "ok" if cloud.health() else "down",
                  f"modal app {settings.cloud_app} (paid always-on if min_containers=1)")
    console.print(table)


@click.group(invoke_without_command=True,
             context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="crowe-mycelium")
@click.option("--temperature", "-t", default=0.4, show_default=True, type=float)
@click.option("--local", "force_local", is_flag=True, help="Force the local Ollama backend.")
@click.option("--cloud", "force_cloud", is_flag=True, help="Force the Modal cloud backend.")
@click.option("--auto", "force_auto", is_flag=True, help="Cloud-first, local fallback (default).")
@click.pass_context
def main(ctx, temperature, force_local, force_cloud, force_auto) -> None:
    """Crowe Mycelium — cultivation intelligence on Gemma 4 Mycelium."""
    load_dotenv()
    ctx.ensure_object(dict)
    ctx.obj["temperature"] = temperature
    ctx.obj["backend"] = ("local" if force_local else
                          "cloud" if force_cloud else
                          "auto" if force_auto else None)
    if ctx.invoked_subcommand is None:
        _chat_loop(ctx)


@main.command()
@click.pass_context
def chat(ctx) -> None:
    """Interactive chat session."""
    _chat_loop(ctx)


@main.command()
@click.argument("prompt", nargs=-1, required=True)
@click.pass_context
def run(ctx, prompt) -> None:
    """One-shot prompt. Streams to stdout (plain when piped)."""
    settings = _settings(ctx)
    backend = build_backend(settings)
    system = load_system_prompt()
    messages = _build_messages([], system, " ".join(prompt))
    renderer = PlainRenderer() if not sys.stdout.isatty() else RichRenderer()
    try:
        renderer.render_stream(backend.stream_chat(messages, settings.temperature))
    except Exception as e:
        renderer.error(str(e))
        sys.exit(1)


@main.command()
@click.pass_context
def info(ctx) -> None:
    """Model + backend status."""
    settings = _settings(ctx)
    _print_info(load_model_spec(), settings)
    branding.footer()


@main.command()
def models() -> None:
    """List registered models."""
    spec = load_model_spec()
    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("name", style="bold")
    table.add_column("label")
    table.add_column("base")
    table.add_row(spec.name, spec.label, spec.base_model)
    console.print(table)
    branding.footer()


@main.command()
@click.pass_context
def doctor(ctx) -> None:
    """Diagnose local + cloud reachability."""
    _doctor_report(_settings(ctx))
    branding.footer()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cli.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add crowe_mycelium/cli.py tests/test_cli.py
git commit -m "feat(cli): backend routing, plain-when-piped, REPL, doctor"
```

---

## Task 11: Fold the wrappers into thin shims

**Files:**
- Modify: `~/.local/bin/crowelm-cloud`, `~/.local/bin/crowelm-mycelium`

- [ ] **Step 1: Replace `~/.local/bin/crowelm-cloud`** with a delegating shim

```bash
#!/usr/bin/env bash
# Shim: the cloud sibling now delegates to the unified crowe-mycelium CLI.
# `crowelm-cloud "q"` -> one-shot cloud;  `crowelm-cloud` / `--chat` -> chat.
if [ "$#" -eq 0 ] || [ "$1" = "--chat" ]; then
    [ "$1" = "--chat" ] && shift
    exec crowe-mycelium --cloud chat "$@"
fi
exec crowe-mycelium --cloud run "$@"
```

- [ ] **Step 2: Replace `~/.local/bin/crowelm-mycelium`** with a delegating shim

```bash
#!/usr/bin/env bash
# Shim: local sibling delegates to the unified crowe-mycelium CLI (local backend).
if [ "$#" -eq 0 ]; then
    exec crowe-mycelium --local chat
fi
exec crowe-mycelium --local run "$@"
```

- [ ] **Step 3: Make executable + verify they parse**

Run:
```bash
chmod +x ~/.local/bin/crowelm-cloud ~/.local/bin/crowelm-mycelium
bash -n ~/.local/bin/crowelm-cloud && bash -n ~/.local/bin/crowelm-mycelium && echo "shims OK"
```
Expected: `shims OK`

- [ ] **Step 4: Commit** (shims live outside the repo; record the change in the repo's CHANGELOG note instead)

```bash
cd ~/Projects/crowe-mycelium-cli
printf '\n## Unreleased\n- Unified CLI: crowelm-cloud/crowelm-mycelium are now shims over `crowe-mycelium --cloud/--local`.\n' >> README.md
git add README.md
git commit -m "docs: note wrapper scripts are now shims over crowe-mycelium"
```

---

## Task 12 (STRETCH): `serve` OpenAI-compatible gateway

> Only do this if Phase 1 still has room; otherwise defer to Phase 1.5 (logged as an open question in the spec). It lets the mycology chat app point at the CLI.

**Files:**
- Create: `crowe_mycelium/serve.py`
- Modify: `crowe_mycelium/cli.py` (add `serve` command), `pyproject.toml` (add `fastapi`, `uvicorn` under an optional `serve` extra)
- Test: `tests/test_serve.py`

- [ ] **Step 1: Add optional extra to `pyproject.toml`**

```toml
[project.optional-dependencies]
serve = ["fastapi>=0.110.0", "uvicorn>=0.29.0"]
```

- [ ] **Step 2: Write the failing test** — `tests/test_serve.py`

```python
from fastapi.testclient import TestClient

from crowe_mycelium.serve import build_app
from tests.conftest import FakeBackend


def test_chat_completions_returns_answer():
    app = build_app(backend=FakeBackend(chunks=["fruiting at 18-23C"]))
    client = TestClient(app)
    resp = client.post("/v1/chat/completions",
                       json={"model": "gemma-4-mycelium-e4b",
                             "messages": [{"role": "user", "content": "temp?"}]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["choices"][0]["message"]["content"] == "fruiting at 18-23C"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_serve.py -v`
Expected: FAIL — `ModuleNotFoundError: crowe_mycelium.serve`

- [ ] **Step 4: Implement `crowe_mycelium/serve.py`**

```python
from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from crowe_mycelium.backends import build_backend
from crowe_mycelium.config import resolve_settings


class _Msg(BaseModel):
    role: str
    content: str


class _Req(BaseModel):
    model: str | None = None
    messages: list[_Msg]
    temperature: float = 0.4


def build_app(backend=None) -> FastAPI:
    backend = backend or build_backend(resolve_settings())
    app = FastAPI(title="crowe-mycelium")

    @app.get("/v1/models")
    def models():
        return {"object": "list", "data": [{"id": "gemma-4-mycelium-e4b", "object": "model"}]}

    @app.post("/v1/chat/completions")
    def chat(req: _Req):
        messages = [{"role": m.role, "content": m.content} for m in req.messages]
        text = "".join(backend.stream_chat(messages, req.temperature))
        return {
            "object": "chat.completion",
            "model": req.model or "gemma-4-mycelium-e4b",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                         "finish_reason": "stop"}],
        }

    return app
```

- [ ] **Step 5: Add the `serve` command to `crowe_mycelium/cli.py`** (after `doctor`)

```python
@main.command()
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8014, show_default=True, type=int)
def serve(host, port) -> None:
    """Run an OpenAI-compatible /v1 gateway over the mycology model."""
    import uvicorn

    from crowe_mycelium.serve import build_app

    uvicorn.run(build_app(), host=host, port=port)
```

- [ ] **Step 6: Install the extra + run tests**

Run: `uv pip install -e ".[dev,serve]" && python -m pytest tests/test_serve.py -v`
Expected: PASS (1 passed)

- [ ] **Step 7: Commit**

```bash
git add crowe_mycelium/serve.py crowe_mycelium/cli.py pyproject.toml tests/test_serve.py
git commit -m "feat(serve): OpenAI-compatible /v1 gateway (optional extra)"
```

---

## Task 13: Finalize — lint, full suite, version bump

**Files:**
- Modify: `pyproject.toml` (version), `crowe_mycelium/__init__.py` (`__version__`)

- [ ] **Step 1: Run ruff and fix any findings**

Run: `cd ~/Projects/crowe-mycelium-cli && ruff check crowe_mycelium tests && ruff format crowe_mycelium tests`
Expected: `All checks passed!` (fix any reported issues, re-run until clean)

- [ ] **Step 2: Run the full test suite**

Run: `python -m pytest`
Expected: all tests PASS (Tasks 1–10, +12 if done)

- [ ] **Step 3: Manual smoke — Plain pipe path (no network needed if local Ollama is up; else expect a clean error to stderr)**

Run: `crowe-mycelium --local run "name one oyster contaminant" | cat`
Expected: an answer on stdout, OR (if local down) a clean `error: ...` on stderr and exit 1 — never a traceback.

- [ ] **Step 4: Bump version to 0.2.0**

In `crowe_mycelium/__init__.py` set `__version__ = "0.2.0"`; in `pyproject.toml` set `version = "0.2.0"`.

- [ ] **Step 5: Commit**

```bash
git add crowe_mycelium/__init__.py pyproject.toml
git commit -m "chore: lint clean, full suite green, bump to 0.2.0"
```

---

## Self-review notes (author check, completed)

- **Spec coverage:** backend abstraction (T1–T5) · cloud-first routing (T4) · renderer abstraction (T6–T7) · design language: ◆/emerald/crest/markdown/tag (T7–T8, T10) · slash palette (T9–T10) · commands incl. `doctor` (T10) and `serve` stretch (T12) · plain-when-piped (T6, T10) · error handling incl. dual-failure message (T4) and stderr separation (T6) · Gemma footer attribution (T8) · folding wrappers into shims (T11) · escalation seam reserved (T4). All spec sections map to a task.
- **Placeholder scan:** none — every code step has full code; the only "stretch" (T12) is gated and self-contained.
- **Type consistency:** `Backend.stream_chat(messages, temperature)` / `health()` and `Renderer.render_stream/notice/error` signatures are identical across all tasks; `Settings`/`resolve_settings`/`build_backend` names match between T5 and T10; `dispatch_slash`/`SlashResult` match between T9 and T10; `store_hint()` defined in T2 is used in T10's doctor.
- **Known Phase-1 limitations (documented in spec):** cloud path is single-turn-flattened (no token, account-auth); `chat --idle` from the old `crowelm-cloud` is intentionally not re-implemented here (the shim maps `--chat` to `crowe-mycelium chat`; idle-closeout can return in a later phase if wanted).
```
