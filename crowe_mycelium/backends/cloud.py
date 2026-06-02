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
