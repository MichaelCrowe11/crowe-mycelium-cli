#!/usr/bin/env python3
"""Generate cinematic B-roll for the hackathon film via Azure Sora 2.

Reads ``video/sora-prompts.json`` (each entry: out / seconds / size / prompt)
and submits each to the AZURE_SORA_DEPLOYMENT_NAME deployment. Polls for
completion, downloads result MP4s to ``video/sora/``. Cached: skips any
output file that already exists and is non-trivial size.

Env required (auto-sourced from ~/Projects/crowe-logic-foundry/.env if not set):
    AZURE_SORA_ENDPOINT
    AZURE_SORA_API_KEY
    AZURE_SORA_DEPLOYMENT_NAME  (default: sora-2)

Pattern lifted from ~/Projects/crowe-theorem-demo-film/scripts/05-generate-sora.py.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPTS_PATH = REPO_ROOT / "video" / "sora-prompts.json"
OUT_DIR = REPO_ROOT / "video" / "sora"
OUT_DIR.mkdir(parents=True, exist_ok=True)

FOUNDRY_ENV = Path.home() / "Projects" / "crowe-logic-foundry" / ".env"
if FOUNDRY_ENV.exists():
    for line in FOUNDRY_ENV.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

ENDPOINT = (os.environ.get("AZURE_SORA_ENDPOINT") or "").strip().rstrip("/")
API_KEY = (os.environ.get("AZURE_SORA_API_KEY") or "").strip()
DEPLOYMENT = (
    os.environ.get("AZURE_SORA_DEPLOYMENT_NAME")
    or os.environ.get("AZURE_SORA_DEPLOYMENT")
    or "sora-2"
).strip()

SUBMIT_INTERVAL_S = 10.0
POLL_INTERVAL_S = 20
TIMEOUT_S = 1500
MAX_RETRY = 6
RETRY_CODES = {429, 500, 502, 503, 504}
ACTIVE = {"queued", "in_progress", "preprocessing", "running", "processing"}
SUCCESS = {"completed", "succeeded"}
FAILED = {"failed", "cancelled", "canceled"}

_last_submit = [0.0]


def normalize_endpoint(base: str) -> str:
    base = base.rstrip("/")
    if base.endswith("/openai/v1"):
        return base
    if base.endswith("/openai"):
        return f"{base}/v1"
    return f"{base}/openai/v1"


def _throttle():
    now = time.time()
    wait = SUBMIT_INTERVAL_S - (now - _last_submit[0])
    if wait > 0:
        time.sleep(wait)
    _last_submit[0] = time.time()


def submit(client, base, payload):
    delay = 10.0
    for attempt in range(MAX_RETRY):
        _throttle()
        r = client.post(
            f"{base}/videos",
            headers={"Authorization": f"Bearer {API_KEY}", "api-key": API_KEY},
            json=payload,
        )
        if r.status_code in RETRY_CODES:
            print(f"    {r.status_code} (try {attempt+1}/{MAX_RETRY}); sleep {delay:.0f}s")
            time.sleep(delay)
            delay *= 2
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError("exhausted retries")


def poll(client, base, video_id):
    started = time.monotonic()
    while True:
        r = client.get(
            f"{base}/videos/{video_id}",
            headers={"Authorization": f"Bearer {API_KEY}", "api-key": API_KEY},
        )
        r.raise_for_status()
        v = r.json()
        if isinstance(v.get("data"), list) and v["data"]:
            v = v["data"][0]
        status = (v.get("status") or "").lower()
        if status in SUCCESS:
            return v
        if status in FAILED:
            raise RuntimeError(f"failed: {v.get('error') or v}")
        if status not in ACTIVE:
            raise RuntimeError(f"unexpected status: {status}")
        if time.monotonic() - started >= TIMEOUT_S:
            raise TimeoutError(f"timeout, last status={status}")
        time.sleep(POLL_INTERVAL_S)


def download(client, base, video_id, out_path):
    r = client.get(
        f"{base}/videos/{video_id}/content",
        headers={"Authorization": f"Bearer {API_KEY}", "api-key": API_KEY},
        timeout=httpx.Timeout(300.0),
    )
    r.raise_for_status()
    out_path.write_bytes(r.content)
    return len(r.content)


def main() -> int:
    if not ENDPOINT or not API_KEY:
        print(
            "AZURE_SORA_ENDPOINT / AZURE_SORA_API_KEY missing. "
            "Check ~/Projects/crowe-logic-foundry/.env or your shell env.",
            file=sys.stderr,
        )
        return 2

    base = normalize_endpoint(ENDPOINT)
    prompts = json.loads(PROMPTS_PATH.read_text())
    print(f"endpoint: {base}")
    print(f"deployment: {DEPLOYMENT}")
    print(f"prompts: {len(prompts)}")
    print()

    failures = []
    with httpx.Client(timeout=httpx.Timeout(120.0, connect=30.0)) as client:
        for i, p in enumerate(prompts, 1):
            out_path = OUT_DIR / p["out"]
            if out_path.exists() and out_path.stat().st_size > 1000:
                print(f"  [{i}/{len(prompts)}] cached: {p['out']}")
                continue
            payload = {
                "model": DEPLOYMENT,
                "prompt": p["prompt"],
                "size": p.get("size", "1280x720"),
                "seconds": str(p.get("seconds", 8)),
            }
            print(f"  [{i}/{len(prompts)}] submitting {p['out']} ({payload['seconds']}s @ {payload['size']})")
            try:
                v = submit(client, base, payload)
                vid = v.get("id")
                print(f"      queued, video_id={vid}")
                final = poll(client, base, vid)
                n = download(client, base, vid, out_path)
                print(f"      OK {p['out']} ({n/1024/1024:.1f} MB)")
            except Exception as exc:
                print(f"      FAIL {p['out']}: {exc.__class__.__name__}: {exc}")
                failures.append(p["out"])

    if failures:
        print(f"\nFailed: {', '.join(failures)}")
        return 1
    print(f"\nDone. Clips in {OUT_DIR}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
