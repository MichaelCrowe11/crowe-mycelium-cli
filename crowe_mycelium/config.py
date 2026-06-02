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
