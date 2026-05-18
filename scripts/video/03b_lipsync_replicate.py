#!/usr/bin/env python3
"""Submit lip-sync jobs to Replicate (devxpy/cog-wav2lip) for all 4 acts.

Replicate's Wav2Lip model re-animates the speaker's mouth in a video to match
a new audio track. Same shape as sync.so but with a different backend — we
fall back here because the sync.so account is paywall-suspended.

Wav2Lip is generally lower-quality than sync-3 (less subtle phoneme matching)
but it gets the lip movement directionally right, and for a 3-minute hackathon
video with rapid cuts and brief on-camera moments, it's enough.

Inputs are uploaded directly to Replicate (no GCS roundtrip needed). Jobs run
in parallel server-side.

Output: ``video/synced/act{1,2,4,5}.mp4``
"""

from __future__ import annotations

import os
import re
import sys
import time
import pathlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import Request, urlopen


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
AUDIO_DIR = REPO_ROOT / "video" / "audio"
SOURCE_DIR = REPO_ROOT / "video" / "source"
SYNCED_DIR = REPO_ROOT / "video" / "synced"
LOG_DIR = REPO_ROOT / "video" / "logs"

# devxpy/cog-wav2lip is the canonical Wav2Lip-HQ runner on Replicate.
# We pin to a recent stable version. If this errors, fetch the latest with
#   replicate.models.get("devxpy/cog-wav2lip").latest_version.id
MODEL_REF = "devxpy/cog-wav2lip:8d65e3f4f4298520e079198b493c25adfc43c058ffec924f2aefc8010ed25eef"
ACTS = [1, 2, 4, 5]


def _load_env_secrets() -> None:
    p = pathlib.Path.home() / ".env.secrets"
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[7:]
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def submit_one(act: int) -> dict:
    import replicate
    video = SOURCE_DIR / f"act{act}.mp4"
    audio = AUDIO_DIR / f"act{act}.wav"
    if not audio.exists():
        audio = AUDIO_DIR / f"act{act}.mp3"
    out = SYNCED_DIR / f"act{act}.mp4"
    log = LOG_DIR / f"replicate_act{act}.log"

    if out.exists():
        return {"act": act, "status": "exists", "out": str(out)}

    if not video.exists() or not audio.exists():
        return {"act": act, "status": "missing_input",
                "video": str(video), "audio": str(audio)}

    log.parent.mkdir(parents=True, exist_ok=True)
    out.parent.mkdir(parents=True, exist_ok=True)

    with log.open("w") as fh:
        fh.write(f"act={act}\nvideo={video}\naudio={audio}\nmodel={MODEL_REF}\n\n")
        fh.flush()
        try:
            with video.open("rb") as v, audio.open("rb") as a:
                output = replicate.run(
                    MODEL_REF,
                    input={
                        "face": v,
                        "audio": a,
                        # Wav2Lip-specific knobs. pad_top/bottom help when the
                        # head is centered but extending the mouth-detection
                        # bounding box reduces miss rate on partial faces.
                        "pads": "0 20 0 0",
                        "smooth": True,
                        # Don't resize — keep source resolution.
                        "resize_factor": 1,
                    },
                )
            fh.write(f"\noutput: {output}\n")
            fh.flush()
        except Exception as exc:
            fh.write(f"\nERROR: {type(exc).__name__}: {exc}\n")
            return {"act": act, "status": "submit_failed", "error": str(exc)}

    # `output` is a FileOutput or URL string depending on replicate version
    url = str(output) if not isinstance(output, str) else output
    if hasattr(output, "url"):
        url = output.url

    # Download
    try:
        req = Request(url, headers={"User-Agent": "crowe-mycelium-cli/0.1"})
        with urlopen(req, timeout=600) as resp, out.open("wb") as fh_out:
            while chunk := resp.read(1024 * 1024):
                fh_out.write(chunk)
    except Exception as exc:
        return {"act": act, "status": "download_failed", "url": url, "error": str(exc)}

    return {"act": act, "status": "ok", "out": str(out),
            "size_mb": out.stat().st_size / 1e6}


def main() -> int:
    _load_env_secrets()
    if not os.environ.get("REPLICATE_API_TOKEN"):
        raise SystemExit("REPLICATE_API_TOKEN not set")

    SYNCED_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    print(f"=== submitting {len(ACTS)} lip-sync jobs to Replicate ({MODEL_REF.split(':')[0]}) ===")
    results = []
    with ThreadPoolExecutor(max_workers=len(ACTS)) as pool:
        futures = {pool.submit(submit_one, a): a for a in ACTS}
        for fut in as_completed(futures):
            act = futures[fut]
            try:
                res = fut.result()
            except Exception as exc:
                res = {"act": act, "status": "exception", "error": str(exc)}
            results.append(res)
            print(f"  act{res['act']}: {res['status']}", end="")
            if res.get("size_mb"):
                print(f"  ({res['size_mb']:.1f} MB)")
            elif res.get("error"):
                print(f"  — {res['error'][:120]}")
            else:
                print()

    n_ok = sum(1 for r in results if r["status"] in ("ok", "exists"))
    print(f"\nDONE: {n_ok}/{len(ACTS)} acts synced")
    return 0 if n_ok == len(ACTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
