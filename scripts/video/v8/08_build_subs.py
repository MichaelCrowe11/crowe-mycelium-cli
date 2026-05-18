#!/usr/bin/env python3
"""Build subtitles.srt for v8.

Knows the timing of each act based on actual audio durations measured
from the source files. Toggles whether to include Act 3 (the live demo).
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]


def dur(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


# Act 1 (real Michael, from Q&A intro): hand-transcribed
ACT1_LINES = [
    (0.0, 4.0,  "My name is Michael Crowe"),
    (4.0, 9.0,  "and I own Southwest Mushrooms."),
    (9.0, 14.0, "Here we cultivate a wide variety"),
    (14.0, 18.0, "of gourmet and medicinal mushrooms."),
    (18.0, 22.0, "I started when I was about fifteen,"),
    (22.0, 25.0, "I just got interested in mushrooms."),
]

# Acts 2/4/5: ElevenLabs voiceover scripts, chunked for readability
EL_LINES = {
    2: [
        "Most AI tools assume the user is in an office.",
        "Growers, farmers, anyone running a real operation,",
        "we don't get that. The connection is bad.",
        "The data is private. The question has to be answered",
        "in the next ten minutes, not after a sync.",
    ],
    4: [
        "Gemma 4 Mycelium is built on Google's Gemma 4.",
        "It's the first open-source model in the Crowe Logic family.",
        "The fine-tune comes from our commercial cultivation library:",
        "Lion's Mane SOP, the Mushroom Grower volumes,",
        "telemetry from our environmental engine.",
        "Released under the Gemma Terms of Use.",
    ],
    5: [
        "Every operator I know has a question",
        "they can't ask a chatbot a thousand miles away.",
        "We started with mushrooms.",
        "The next models in the Crowe Logic family",
        "will start with whoever shows me their grow room next.",
        "Built on Gemma. Made for the work.",
    ],
}


def fmt_ts(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int((t - int(t)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def spread_lines(lines: list[str], window_start: float, window_dur: float) -> list[tuple[float, float, str]]:
    """Spread N lines across a window, each one taking window_dur/N seconds."""
    if not lines:
        return []
    per = window_dur / len(lines)
    return [(window_start + i * per, window_start + (i + 1) * per * 0.95, line)
            for i, line in enumerate(lines)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-act3", action="store_true",
                    help="Include 65s for Act 3 in the timeline")
    ap.add_argument("--act3-dur", type=float, default=65.0,
                    help="Estimated Act 3 demo duration in seconds")
    ap.add_argument("--out", default="video/v8/subtitles.srt")
    args = ap.parse_args()

    el_durs = {a: dur(REPO / f"video/audio/act{a}.mp3") for a in (2, 4, 5)}

    entries: list[tuple[float, float, str]] = []

    # Title (5s) - no subs
    cursor = 5.0

    # Act 1 (25s real Michael)
    for s, e, line in ACT1_LINES:
        entries.append((cursor + s, cursor + e, line))
    cursor += 25.0

    # Act 2 (visual 30s, audio el_durs[2] starting at cursor)
    entries.extend(spread_lines(EL_LINES[2], cursor, el_durs[2]))
    cursor += 30.0

    # Act 3 (optional)
    if args.with_act3:
        cursor += args.act3_dur

    # Act 4
    entries.extend(spread_lines(EL_LINES[4], cursor, el_durs[4]))
    cursor += 30.0

    # Act 5
    entries.extend(spread_lines(EL_LINES[5], cursor, el_durs[5]))

    # Render SRT
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for i, (s, e, text) in enumerate(entries, 1):
        lines.append(str(i))
        lines.append(f"{fmt_ts(s)} --> {fmt_ts(e)}")
        lines.append(text)
        lines.append("")
    out.write_text("\n".join(lines))
    print(f"wrote {out} ({len(entries)} entries, with_act3={args.with_act3})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
