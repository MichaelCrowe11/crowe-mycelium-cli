#!/usr/bin/env python3
"""Generate v10 ElevenLabs narration from video/v10/script.json."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "video" / "v10" / "script.json"
OUT = ROOT / "video" / "v10" / "audio"
VOICE_ID_DEFAULT = "BsxQGfHOT8xeJhwW3B2u"
MODEL_ID_DEFAULT = "eleven_v3"


def load_env() -> None:
    env_path = Path.home() / ".env.secrets"
    if not env_path.exists():
        return
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:]
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def synthesize(text: str, out_path: Path, api_key: str, voice_id: str, model_id: str) -> None:
    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": 0.48,
            "similarity_boost": 0.86,
            "style": 0.12,
            "use_speaker_boost": True,
        },
    }
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream?output_format=mp3_44100_192"
    req = urllib.request.Request(
        url,
        method="POST",
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        data=json.dumps(payload).encode("utf-8"),
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            out_path.write_bytes(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:600]
        raise RuntimeError(f"ElevenLabs HTTP {exc.code}: {body}") from exc


def convert_mp3_to_wav(mp3_path: Path, wav_path: Path) -> None:
    subprocess.check_call(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(mp3_path),
            "-ar",
            "48000",
            "-ac",
            "2",
            str(wav_path),
        ]
    )


def duration(path: Path) -> float:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(proc.stdout.strip())


def main() -> int:
    load_env()
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise SystemExit("ELEVENLABS_API_KEY missing from env or ~/.env.secrets")
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID", VOICE_ID_DEFAULT)
    model_id = os.environ.get("ELEVENLABS_MODEL_ID", MODEL_ID_DEFAULT)

    data = json.loads(SCRIPT.read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {
        "voice_id": voice_id,
        "model_id": model_id,
        "acts": [],
    }

    concat_file = OUT / "concat.txt"
    concat_lines: list[str] = []
    silence = OUT / "gap_0_7s.wav"
    subprocess.check_call(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=48000:cl=stereo",
            "-t",
            "0.70",
            str(silence),
        ]
    )

    for act in data["acts"]:
        mp3 = OUT / f"act{act['act']}_{act['slug']}.mp3"
        wav = OUT / f"act{act['act']}_{act['slug']}.wav"
        print(f"Act {act['act']}: {len(act['text'])} chars -> {mp3.name}")
        synthesize(act["text"], mp3, api_key, voice_id, model_id)
        convert_mp3_to_wav(mp3, wav)
        dur = duration(wav)
        manifest["acts"].append({**act, "mp3": mp3.name, "wav": wav.name, "duration": dur})
        concat_lines.append(f"file '{wav}'\n")
        concat_lines.append(f"file '{silence}'\n")
        print(f"  duration {dur:.2f}s")

    concat_file.write_text("".join(concat_lines))
    voice = OUT / "voice.wav"
    subprocess.check_call(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c:a",
            "pcm_s16le",
            str(voice),
        ]
    )
    manifest["voice_wav"] = str(voice.relative_to(ROOT))
    manifest["voice_duration"] = duration(voice)
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"voice: {voice} ({manifest['voice_duration']:.2f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
