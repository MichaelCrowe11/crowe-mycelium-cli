"""Backend client for Gemma 4 Mycelium.

Default backend is Ollama (matches the Special Tech Track and gives the
offline-edge story). The provider abstraction is deliberately thin: if we
add llama.cpp or LiteRT backends later, they slot in behind the same
generate() / stream() surface.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import httpx


REGISTRY_PATH = Path(__file__).parent / "registry.json"
SYSTEM_PROMPT_PATH = Path(__file__).parent / "system_prompt.txt"


@dataclass(frozen=True)
class ModelSpec:
    name: str
    label: str
    backend_name: str
    ollama_tag: str
    base_model: str
    context_window: int
    license: str
    license_url: str


def load_model_spec() -> ModelSpec:
    """Load the single registered model from registry.json."""
    data = json.loads(REGISTRY_PATH.read_text())
    entry = data["models"][0]
    return ModelSpec(
        name=entry["name"],
        label=entry["label"],
        backend_name=entry["backend_name"],
        ollama_tag=entry["ollama_tag"],
        base_model=entry["base_model"],
        context_window=entry["context_window"],
        license=entry["license"],
        license_url=entry["license_url"],
    )


def load_system_prompt() -> str:
    return SYSTEM_PROMPT_PATH.read_text().strip()


def ollama_host() -> str:
    return os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")


def ollama_tag() -> str:
    """Resolved Ollama tag. Env override wins so users can swap in their own pull."""
    return os.environ.get("CROWE_MYCELIUM_OLLAMA_TAG", load_model_spec().ollama_tag)


def check_backend() -> tuple[bool, str]:
    """Return (ok, message) for the configured Ollama backend.

    Verifies the daemon is reachable AND the model tag is present.
    """
    host = ollama_host()
    tag = ollama_tag()
    try:
        r = httpx.get(f"{host}/api/tags", timeout=2.0)
        r.raise_for_status()
    except Exception as e:
        return False, f"Ollama daemon unreachable at {host} ({e.__class__.__name__})"

    names = {m["name"] for m in r.json().get("models", [])}
    if tag not in names and f"{tag}:latest" not in names:
        return False, (
            f"Model '{tag}' not found in Ollama. "
            f"Pull it first: `ollama pull {tag}` "
            f"(or set CROWE_MYCELIUM_OLLAMA_TAG to a tag you have)."
        )
    return True, f"Ollama @ {host}, model {tag}"


def stream_chat(messages: list[dict], temperature: float = 0.4) -> Iterator[str]:
    """Stream a chat completion from Ollama. Yields content chunks as they arrive."""
    host = ollama_host()
    tag = ollama_tag()
    payload = {
        "model": tag,
        "messages": messages,
        "stream": True,
        "options": {"temperature": temperature},
    }
    with httpx.stream("POST", f"{host}/api/chat", json=payload, timeout=120.0) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            chunk = obj.get("message", {}).get("content", "")
            if chunk:
                yield chunk
            if obj.get("done"):
                break
