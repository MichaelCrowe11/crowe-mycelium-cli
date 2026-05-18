#!/usr/bin/env python3
"""Generate ElevenLabs narration audio for each act of the hackathon video.

Reads ``docs/VIDEO_SHOTLIST.md``, extracts the **Voiceover (t)** blocks,
and synthesises one MP3 per act using Michael Crowe's ElevenLabs voice.
Output: ``video/audio/act{1..5}.mp3`` plus a ``video/audio/manifest.json``
linking each act's audio to its expected screen-time window.

The voice settings (model, stability, similarity) are tuned for the same
calm narrative tone used in the Mushroom Grower Vol 1 video. If you want
to override per-act, edit ``ACT_OVERRIDES`` below.

Env:
    ELEVENLABS_API_KEY   ~/.env.secrets canonical
    ELEVENLABS_VOICE_ID  default: Michael's voice (BsxQGfHOT8xeJhwW3B2u)
    ELEVENLABS_MODEL_ID  default: eleven_v3
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SHOTLIST = REPO_ROOT / "docs" / "VIDEO_SHOTLIST.md"
AUDIO_DIR = REPO_ROOT / "video" / "audio"


def _load_env_secrets() -> None:
    env_path = Path.home() / ".env.secrets"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[7:]
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_VO_BLOCK = re.compile(
    r"\*\*Voiceover\s*\(([^)]+)\)\*\*:\s*\n>\s*\"(.+?)\"",
    re.DOTALL,
)

_ACT_HEADER = re.compile(
    r"^##\s*Act\s+(\d+)\s+—\s+(.+?)\s+·\s+(.+)$",
    re.MULTILINE,
)


def parse_shotlist(md: str) -> list[dict]:
    """Return a list of {act, title, window, text} for each VO block."""
    acts = []
    # Find act headers + their VO blocks
    for act_match in _ACT_HEADER.finditer(md):
        act_num = int(act_match.group(1))
        title = act_match.group(2).strip()
        window = act_match.group(3).strip()
        start = act_match.end()
        # Find the next act header (or EOF)
        next_match = _ACT_HEADER.search(md, start)
        end = next_match.start() if next_match else len(md)
        section = md[start:end]
        vo_match = _VO_BLOCK.search(section)
        if not vo_match:
            print(f"  WARN: no voiceover block found in Act {act_num}")
            continue
        sub_window = vo_match.group(1).strip()
        # Clean text: collapse newlines, strip quote runs, normalise dashes
        text = vo_match.group(2)
        text = re.sub(r"\s*\n\s*", " ", text).strip()
        text = text.replace("—", "—").replace("—", "—")
        acts.append({
            "act": act_num,
            "title": title,
            "window": window,
            "vo_window": sub_window,
            "text": text,
            "audio_filename": f"act{act_num}.mp3",
        })
    return acts


def synthesise(act: dict, api_key: str, voice_id: str, model_id: str) -> Path:
    import urllib.request
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    out = AUDIO_DIR / act["audio_filename"]
    payload = {
        "text": act["text"],
        "model_id": model_id,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.85,
        },
    }
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream?output_format=mp3_44100_192"
    req = urllib.request.Request(
        url, method="POST",
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        data=json.dumps(payload).encode("utf-8"),
    )
    print(f"  Act {act['act']} ({act['title']}) — {len(act['text'])} chars → {out.name}")
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise SystemExit(f"ElevenLabs call failed: {exc} — body: {body}")
    except Exception as exc:
        raise SystemExit(f"ElevenLabs call failed: {exc}")
    out.write_bytes(data)
    print(f"    wrote {len(data):,} bytes")
    return out


def main() -> int:
    _load_env_secrets()
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "BsxQGfHOT8xeJhwW3B2u")
    model_id = os.environ.get("ELEVENLABS_MODEL_ID", "eleven_v3")
    if not api_key:
        raise SystemExit("ELEVENLABS_API_KEY not set in env or ~/.env.secrets")

    if not SHOTLIST.exists():
        raise SystemExit(f"shotlist missing: {SHOTLIST}")
    md = SHOTLIST.read_text()
    acts = parse_shotlist(md)
    if not acts:
        raise SystemExit("no acts parsed from VIDEO_SHOTLIST.md")
    print(f"  parsed {len(acts)} acts from VIDEO_SHOTLIST.md")
    print(f"  voice: {voice_id}, model: {model_id}")
    print()

    for act in acts:
        synthesise(act, api_key, voice_id, model_id)

    manifest = {
        "voice_id": voice_id,
        "model_id": model_id,
        "acts": acts,
    }
    (AUDIO_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print()
    print(f"  manifest written: {AUDIO_DIR / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
