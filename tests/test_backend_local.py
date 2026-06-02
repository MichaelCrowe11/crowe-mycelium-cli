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


def test_local_defaults_are_not_truncating(monkeypatch):
    import crowe_mycelium.model as m

    captured = {}

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": "ok"}}

    def fake_post(url, json, timeout):
        captured["options"] = json["options"]
        return FakeResp()

    monkeypatch.setattr(m.httpx, "post", fake_post)
    list(m.stream_chat([{"role": "user", "content": "hi"}]))
    # A full cultivation answer must not be cut off at 160 tokens / 1024 ctx.
    assert captured["options"]["num_predict"] >= 512
    assert captured["options"]["num_ctx"] >= 2048
