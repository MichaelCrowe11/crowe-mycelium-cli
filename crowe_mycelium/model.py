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


def ollama_timeout_seconds() -> float:
    """Request timeout for local Ollama calls.

    Gemma 4 E4B can cold-load slowly on 16GB unified-memory Macs. Keep the
    default high enough for first launch while still allowing demos/tests to
    tighten it via env.
    """
    raw = os.environ.get("CROWE_MYCELIUM_OLLAMA_TIMEOUT_S", "600")
    try:
        return max(10.0, float(raw))
    except ValueError:
        return 600.0


def ollama_think_enabled() -> bool:
    """Whether to request Ollama thinking-channel output.

    The public CLI should return visible answer text, not spend the whole token
    budget in a hidden `thinking` field. Advanced users can opt in explicitly.
    """
    return os.environ.get("CROWE_MYCELIUM_THINK", "0").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


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


def _int_env(name: str, default: int, minimum: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default


def stream_chat(messages: list[dict], temperature: float = 0.4) -> Iterator[str]:
    """Yield a chat completion from Ollama.

    Ollama 0.24.0 currently behaves poorly with Gemma 4 E4B on the streaming
    path in this repo: the model may spend the entire budget in `thinking`, and
    local streaming probes can hang or 500. The non-streaming endpoint with
    `think: false` returns visible content reliably, so the public CLI uses that
    deterministic path while preserving the generator API used by cli.py.
    """
    host = ollama_host()
    tag = ollama_tag()
    payload = {
        "model": tag,
        "messages": messages,
        "stream": False,
        "think": ollama_think_enabled(),
        "options": {
            "temperature": temperature,
            "num_ctx": _int_env("CROWE_MYCELIUM_NUM_CTX", 2048, 512),
            "num_predict": _int_env("CROWE_MYCELIUM_NUM_PREDICT", 512, 32),
        },
    }
    r = httpx.post(
        f"{host}/api/chat",
        json=payload,
        timeout=ollama_timeout_seconds(),
    )
    r.raise_for_status()
    obj = r.json()
    content = obj.get("message", {}).get("content", "")
    if content:
        yield content
        return

    thinking = obj.get("message", {}).get("thinking", "")
    if thinking:
        raise RuntimeError(
            "Ollama returned hidden thinking but no visible answer. "
            "Keep CROWE_MYCELIUM_THINK unset or set it to 0."
        )
    raise RuntimeError("Ollama returned an empty answer.")
