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

    def deliberate(self, label: str, fn) -> str:
        print(label, file=sys.stderr)
        return fn()

    def notice(self, msg: str) -> None:
        print(msg, file=sys.stderr)

    def error(self, msg: str) -> None:
        print(f"error: {msg}", file=sys.stderr)
