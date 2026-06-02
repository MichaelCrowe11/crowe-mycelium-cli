from __future__ import annotations

from crowe_mycelium.backends.base import Backend
from crowe_mycelium.backends.cloud import CloudModalBackend
from crowe_mycelium.backends.local import LocalOllamaBackend
from crowe_mycelium.backends.router import AutoBackend


def build_backend(settings) -> Backend:
    """Construct the Backend for the resolved settings."""
    local = LocalOllamaBackend()
    cloud = CloudModalBackend(app=settings.cloud_app, func=settings.cloud_func)
    if settings.backend == "local":
        return local
    if settings.backend == "cloud":
        return cloud
    return AutoBackend(cloud=cloud, local=local)
