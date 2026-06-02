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
