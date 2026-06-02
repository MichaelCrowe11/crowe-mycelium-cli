from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from crowe_mycelium.backends import build_backend
from crowe_mycelium.config import resolve_settings


class _Msg(BaseModel):
    role: str
    content: str


class _Req(BaseModel):
    model: str | None = None
    messages: list[_Msg]
    temperature: float = 0.4


def build_app(backend=None) -> FastAPI:
    backend = backend or build_backend(resolve_settings())
    app = FastAPI(title="crowe-mycelium")

    @app.get("/v1/models")
    def models():
        return {"object": "list", "data": [{"id": "gemma-4-mycelium-e4b", "object": "model"}]}

    @app.post("/v1/chat/completions")
    def chat(req: _Req):
        messages = [{"role": m.role, "content": m.content} for m in req.messages]
        text = "".join(backend.stream_chat(messages, req.temperature))
        return {
            "object": "chat.completion",
            "model": req.model or "gemma-4-mycelium-e4b",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }
            ],
        }

    return app
