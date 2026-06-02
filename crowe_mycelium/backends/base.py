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
