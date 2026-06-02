from crowe_mycelium.config import Settings, resolve_settings
from crowe_mycelium.backends import build_backend
from crowe_mycelium.backends.router import AutoBackend
from crowe_mycelium.backends.local import LocalOllamaBackend
from crowe_mycelium.backends.cloud import CloudModalBackend


def test_default_backend_is_auto(monkeypatch):
    monkeypatch.delenv("CROWE_MYCELIUM_BACKEND", raising=False)
    assert resolve_settings().backend == "auto"


def test_explicit_arg_overrides_env(monkeypatch):
    monkeypatch.setenv("CROWE_MYCELIUM_BACKEND", "cloud")
    assert resolve_settings(backend="local").backend == "local"


def test_invalid_backend_falls_back_to_auto(monkeypatch):
    monkeypatch.setenv("CROWE_MYCELIUM_BACKEND", "banana")
    assert resolve_settings().backend == "auto"


def test_factory_builds_right_type():
    assert isinstance(build_backend(Settings(backend="local")), LocalOllamaBackend)
    assert isinstance(build_backend(Settings(backend="cloud")), CloudModalBackend)
    assert isinstance(build_backend(Settings(backend="auto")), AutoBackend)
