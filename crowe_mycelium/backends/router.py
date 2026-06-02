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
