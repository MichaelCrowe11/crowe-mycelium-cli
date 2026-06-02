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
        # True after a turn where cloud was unreachable and we used local instead.
        # The CLI reads this to surface a "⚠ cloud unreachable → local" notice.
        self.fell_back: bool = False

    @property
    def label(self) -> str:
        return self._active.label if self._active else "auto · cloud-first"

    def health(self) -> bool:
        return self.cloud.health() or self.local.health()

    def stream_chat(self, messages, temperature: float = 0.4) -> Iterator[str]:
        # Probe cloud once (this value also decides fell_back) — no double probe.
        if self.cloud.health():
            chosen, self.fell_back = self.cloud, False
        elif self.local.health():
            chosen, self.fell_back = self.local, True
        else:
            self.fell_back = False
            raise RuntimeError(
                "No backend available: cloud unreachable and local (Elements/Ollama) "
                "is down. Plug in Elements, or check the Modal app "
                "(`modal app list | grep mycel`)."
            )
        self._active = chosen
        yield from chosen.stream_chat(messages, temperature=temperature)
