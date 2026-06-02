from crowe_mycelium.backends import local as local_mod
from crowe_mycelium.backends.local import LocalOllamaBackend


def test_local_streams_via_model(monkeypatch):
    monkeypatch.setattr(
        local_mod._model, "stream_chat", lambda messages, temperature=0.4: iter(["600-1200 ppm"])
    )
    b = LocalOllamaBackend()
    assert b.name == "local"
    assert list(b.stream_chat([{"role": "user", "content": "co2?"}])) == ["600-1200 ppm"]


def test_local_health_reflects_check_backend(monkeypatch):
    monkeypatch.setattr(local_mod._model, "check_backend", lambda: (True, "ok"))
    assert LocalOllamaBackend().health() is True
    monkeypatch.setattr(local_mod._model, "check_backend", lambda: (False, "down"))
    assert LocalOllamaBackend().health() is False


def test_local_store_hint_when_elements_absent(monkeypatch, tmp_path):
    b = LocalOllamaBackend(store=str(tmp_path / "nope"))
    assert "Elements" in b.store_hint()
