#!/usr/bin/env python3
"""Create SRT captions for film_v10 from the v10 script and audio manifest."""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "video" / "v10" / "script.json"
MANIFEST = ROOT / "video" / "v10" / "audio" / "manifest.json"
OUT = ROOT / "video" / "v10" / "film_v10.srt"


def fmt(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def chunks(text: str, max_chars: int = 68) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    out: list[str] = []
    for sentence in sentences:
        if len(sentence) <= max_chars:
            out.append(sentence)
            continue
        words = sentence.split()
        cur = ""
        for word in words:
            test = word if not cur else f"{cur} {word}"
            if len(test) <= max_chars:
                cur = test
            else:
                out.append(cur)
                cur = word
        if cur:
            out.append(cur)
    return out


def main() -> int:
    script = json.loads(SCRIPT.read_text())
    manifest = json.loads(MANIFEST.read_text())
    durations = {item["act"]: float(item["duration"]) for item in manifest["acts"]}

    t = 0.0
    index = 1
    lines: list[str] = []
    for act in script["acts"]:
        act_no = act["act"]
        dur = durations[act_no]
        parts = chunks(act["text"])
        total_chars = sum(len(part) for part in parts) or 1
        cursor = t
        for part in parts:
            part_dur = max(1.25, dur * (len(part) / total_chars))
            start = cursor
            end = min(t + dur, cursor + part_dur)
            lines.extend([str(index), f"{fmt(start)} --> {fmt(end)}", part, ""])
            index += 1
            cursor = end
        t += dur + 0.70
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
