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
    def deliberate(self, label: str, fn) -> str:
        """Run `fn` (a no-arg callable returning text) while showing a labeled
        working indicator; return fn()'s result. Used to collect hidden samples."""
        raise NotImplementedError

    @abstractmethod
    def notice(self, msg: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def error(self, msg: str) -> None:
        raise NotImplementedError
