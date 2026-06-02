from fastapi.testclient import TestClient

from crowe_mycelium.serve import build_app
from tests.conftest import FakeBackend


def test_chat_completions_returns_answer():
    app = build_app(backend=FakeBackend(chunks=["fruiting at 18-23C"]))
    client = TestClient(app)
    resp = client.post(
        "/v1/chat/completions",
        json={"model": "gemma-4-mycelium-e4b", "messages": [{"role": "user", "content": "temp?"}]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["choices"][0]["message"]["content"] == "fruiting at 18-23C"
