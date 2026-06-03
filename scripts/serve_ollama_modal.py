"""Serve Gemma 4 Mycelium as a scale-to-zero GPU endpoint on Modal.

The model already lives, complete, on the Ollama registry at
``Mcrowe1210/gemma-4-mycelium-e4b`` (9.6 GB, includes the mycology system
prompt). This deploys it as an on-demand HTTP endpoint:

    * GPU (T4) — fits the 9.6 GB model + KV cache, cheapest Modal GPU.
    * Scale-to-zero — ``min_containers=0`` means ~$0 when idle; you only pay
      GPU-seconds while a request (plus a short warm window) is in flight.
    * Model baked into the image — pulled once at build time so cold starts
      don't re-download 9.6 GB. (To update the model: rebuild the image.)
    * Ollama's own HTTP server is exposed directly, so you get BOTH the native
      ``/api/chat`` + ``/api/generate`` and the OpenAI-compatible
      ``/v1/chat/completions`` on one URL.

Deploy:   modal deploy scripts/serve_ollama_modal.py
Tear down: modal app stop crowe-mycelium-serve

Gemma attribution: this serves a Gemma 4 derivative under the Gemma Terms of
Use (https://ai.google.dev/gemma/terms).
"""

import os
import subprocess

import modal

APP_NAME = "crowe-mycelium-serve"
MODEL = "Mcrowe1210/gemma-4-mycelium-e4b"  # public Ollama-registry tag
GPU = "L4"  # 24 GB; ~2-3x faster than T4 for this 9.6 GB model. Bump to "A10G" for more.

# Cost-safety default: the endpoint requires Modal proxy-auth tokens so a random
# scanner can't run up GPU bills. Set to False for a fully public demo URL.
REQUIRE_AUTH = True

# --- Image: install Ollama, then bake the model in as a cached layer ----------
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install(
        "curl", "ca-certificates", "zstd"
    )  # zstd: ollama installer extracts a .zst archive
    .run_commands("curl -fsSL https://ollama.com/install.sh | sh")
    .run_commands(
        # `ollama pull` needs the daemon, so start it, wait for it, pull, done.
        # The blobs land in /root/.ollama and persist in this image layer.
        "bash -c '"
        "OLLAMA_HOST=127.0.0.1:11434 ollama serve & "
        "for i in $(seq 1 60); do "
        "  curl -sf http://127.0.0.1:11434/ >/dev/null && break; sleep 1; "
        "done; "
        f"OLLAMA_HOST=127.0.0.1:11434 ollama pull {MODEL}"
        "'"
    )
    # Keep the model resident in VRAM across requests within a warm container,
    # so a burst doesn't reload weights on every call.
    .env({"OLLAMA_HOST": "0.0.0.0:11434", "OLLAMA_KEEP_ALIVE": "24h"})
)

app = modal.App(APP_NAME, image=image)


@app.function(
    gpu=GPU,
    min_containers=0,  # scale to zero — no idle cost
    scaledown_window=300,  # stay warm 5 min after last request (absorb bursts)
    timeout=600,
)
@modal.web_server(port=11434, startup_timeout=180, requires_proxy_auth=REQUIRE_AUTH)
def serve():
    """Boot Ollama; Modal proxies the public URL to its port 11434."""
    subprocess.Popen(
        ["ollama", "serve"],
        env={**os.environ, "OLLAMA_HOST": "0.0.0.0:11434"},
    )


# smoke is the scale-to-zero verification path (called via `modal run`).
# The always-warm box has moved to `chat` below; smoke no longer keeps a
# container warm 24/7.
@app.function(gpu=GPU, timeout=600, min_containers=0)
def smoke(prompt: str = "What CO2 range for oyster fruiting? One short sentence."):
    """Run the baked-in model on the GPU and return its answer.

    Verification path that needs no proxy-auth token: ``modal run`` invokes this
    with your CLI account creds, proving the model loads on the L4 and answers.
    """
    import json
    import time
    import urllib.request

    subprocess.Popen(
        ["ollama", "serve"],
        env={**os.environ, "OLLAMA_HOST": "127.0.0.1:11434"},
        stdout=subprocess.DEVNULL,  # keep the verbose llama-server logs out of client output
        stderr=subprocess.DEVNULL,
    )
    for _ in range(60):  # wait for the daemon
        try:
            urllib.request.urlopen("http://127.0.0.1:11434/", timeout=2)
            break
        except Exception:
            time.sleep(1)

    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/chat",
        data=json.dumps(
            {"model": MODEL, "messages": [{"role": "user", "content": prompt}], "stream": False}
        ).encode(),
        headers={"Content-Type": "application/json"},
    )
    resp = json.loads(urllib.request.urlopen(req, timeout=300).read())
    return resp["message"]["content"]


# Scale-to-zero: ~$0 when idle (vs an always-warm L4 ~= $576/mo). The model is
# baked into the image, so a cold start is just container boot (~2-3 min on the
# first call after idle), NOT a 9.6 GB re-download; warm calls stay fast within
# scaledown_window. To kill cold starts for heavy use, set min_containers=1.
@app.function(gpu=GPU, timeout=600, min_containers=0, scaledown_window=300)
def chat(messages: list, temperature: float = 0.4):
    """Stream a chat completion token-by-token from the baked-in model.

    A Modal *generator* function: the CLI consumes it with `chat.remote_gen(...)`.
    The CLI sends the full role-separated `messages` (system + history + user),
    so the per-request system prompt overrides the Modelfile-baked one and
    multi-turn context is preserved.
    """
    import json
    import time
    import urllib.request

    subprocess.Popen(
        ["ollama", "serve"],
        env={**os.environ, "OLLAMA_HOST": "127.0.0.1:11434"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(60):  # wait for the daemon
        try:
            urllib.request.urlopen("http://127.0.0.1:11434/", timeout=2)
            break
        except Exception:
            time.sleep(1)

    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/chat",
        data=json.dumps(
            {
                "model": MODEL,
                "messages": messages,
                "stream": True,
                "options": {"temperature": temperature},
            }
        ).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        for raw in resp:  # Ollama streams line-delimited JSON objects
            line = raw.decode().strip()
            if not line:
                continue
            obj = json.loads(line)
            delta = obj.get("message", {}).get("content", "")
            if delta:
                yield delta
            if obj.get("done"):
                break


@app.local_entrypoint()
def main(prompt: str = "What CO2 range for oyster fruiting? One short sentence."):
    print("Q:", prompt)
    print("A:", smoke.remote(prompt))
