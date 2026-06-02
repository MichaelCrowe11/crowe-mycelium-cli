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
        return (
            f"Elements model store not readable ({self._store}). "
            f"Plug in / re-seat the drive, or ensure Ollama has the model pulled."
        )
