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

    def __init__(
        self,
        app: str = "crowe-mycelium-serve",
        func: str = "smoke",
        caller: Optional[Callable[[str], str]] = None,
        health_probe: Optional[Callable[[], object]] = None,
    ):
        self._app = app
        self._func = func
        self._caller = caller  # injectable for tests
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
