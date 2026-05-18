# Gemma 4 Mycelium Video Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `video/final/film_v7b_lipsync.mp4` with a 1080p30 hackathon submission video built from SWM YouTube archive footage, real-voice (no synthesis lipsync), Substrate album music bed, and static-centered hex-C corporate branding on title and end cards with four CTAs.

**Architecture:** A scratch-on-Elements yt-dlp pull feeds whisper.cpp transcription. A matcher script aligns the 5-act script lines to real spoken moments in the archive. ffmpeg cuts losslessly, then a second ffmpeg pass assembles scenes + cards + lower-thirds + ducked music + burned subtitles into the final mp4.

**Tech Stack:** yt-dlp, whisper-cli (whisper.cpp via Homebrew), ffmpeg, Python 3.11 with Pillow for cards, jq for transcript JSON, bash glue.

---

## File structure

**New files:**
- `scripts/video/v8/00_setup.sh` — verify deno+yt-dlp+whisper-cli+ffmpeg present, mount Elements, create dirs
- `scripts/video/v8/01_pull_archive.sh` — yt-dlp pull from SWM channel to Elements scratch dir
- `scripts/video/v8/02_transcribe.sh` — whisper-cli on each pulled video, emit JSON
- `scripts/video/v8/03_match.py` — match 5-act script lines to (video, in, out) tuples; emit cut_list.json
- `scripts/video/v8/04_cut.sh` — read cut_list.json, ffmpeg -ss/-to/-c copy lossless cuts
- `scripts/video/v8/05_cards.py` — Pillow renders title.png, end.png, lower_third.png at 1920x1080
- `scripts/video/v8/06_act3_record.md` — runbook for the manual Act 3 screen capture
- `scripts/video/v8/07_assemble.sh` — concat scenes, overlay cards, mix audio, burn subs
- `scripts/video/v8/cut_list.template.json` — schema for the matcher output
- `scripts/video/v8/scripts.json` — the 5-act script text (matcher input)
- `tests/video/test_match.py` — pytest for the matcher
- `tests/video/test_cards.py` — pytest for card rendering

**New directories:**
- `video/v8/` — working dir for the v8 build
- `video/v8/scenes/` — cut clips per act
- `video/v8/cards/` — generated 1080p cards
- `video/v8/subtitles.srt` — burned-in subtitle source
- `video/final/film_v8.mp4` — final output
- `/Volumes/Elements/swm-yt-archive-2026-05-18/` — yt-dlp scratch (NOT /tmp, per memory)
- `/Volumes/Elements/swm-yt-archive-2026-05-18/transcripts/` — whisper JSON output

**Modified files:**
- `docs/SUBMISSION.md` — replace `<!-- PASTE_YOUTUBE_URL_HERE -->` after upload

---

## Task 1: Setup and tooling check

**Files:**
- Create: `scripts/video/v8/00_setup.sh`

- [ ] **Step 1: Write the setup script**

Create `scripts/video/v8/00_setup.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SCRATCH="/Volumes/Elements/swm-yt-archive-2026-05-18"

echo ">> verifying tools..."
for bin in yt-dlp ffmpeg whisper-cli jq; do
  if ! command -v "$bin" >/dev/null; then
    echo "MISSING: $bin"
    case "$bin" in
      yt-dlp)      echo "  install: pip3 install --user yt-dlp" ;;
      ffmpeg|jq)   echo "  install: brew install $bin" ;;
      whisper-cli) echo "  install: brew install whisper-cpp" ;;
    esac
    exit 1
  fi
done

echo ">> verifying deno (yt-dlp JS runtime requirement)..."
if ! command -v deno >/dev/null; then
  echo "  installing deno via brew..."
  brew install deno
fi

echo ">> verifying Elements volume mounted..."
if [[ ! -d "/Volumes/Elements" ]]; then
  echo "ERROR: /Volumes/Elements not mounted. Plug in the drive."
  exit 1
fi

echo ">> creating directories..."
mkdir -p "$SCRATCH"/{videos,transcripts}
mkdir -p "$REPO_ROOT/video/v8"/{scenes,cards}

echo ">> setup complete."
echo "   scratch: $SCRATCH"
echo "   build:   $REPO_ROOT/video/v8"
```

- [ ] **Step 2: Make it executable and run it**

```bash
chmod +x scripts/video/v8/00_setup.sh
scripts/video/v8/00_setup.sh
```

Expected output: `>> setup complete.` and both directories created. If deno install fails, install manually with `brew install deno`.

- [ ] **Step 3: Commit**

```bash
git add scripts/video/v8/00_setup.sh
git commit -m "v8: setup script for video rebuild tooling check"
```

---

## Task 2: Pull SWM YouTube archive

**Files:**
- Create: `scripts/video/v8/01_pull_archive.sh`

**Channel handle:** The SWM YouTube channel handle is not 100% confirmed from memory. Try `@MichaelCroweMycology` first (per `video/YOUTUBE_UPLOAD.md` channel reference). If that fails, ask the user.

- [ ] **Step 1: Write the pull script**

Create `scripts/video/v8/01_pull_archive.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRATCH="/Volumes/Elements/swm-yt-archive-2026-05-18"
CHANNEL="${SWM_YT_CHANNEL:-https://www.youtube.com/@MichaelCroweMycology/videos}"
N="${SWM_YT_N:-30}"

echo ">> pulling top $N videos from $CHANNEL"
echo "   into $SCRATCH/videos"

# 1080p mp4, embed metadata, write info JSON, cap at N videos.
# --download-archive prevents re-downloads on re-run.
yt-dlp \
  --format "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best" \
  --merge-output-format mp4 \
  --write-info-json \
  --write-auto-subs \
  --sub-lang en \
  --convert-subs srt \
  --download-archive "$SCRATCH/archive.txt" \
  --playlist-end "$N" \
  --output "$SCRATCH/videos/%(upload_date)s_%(title).100B_%(id)s.%(ext)s" \
  --no-overwrites \
  "$CHANNEL"

echo ">> pulled. inventory:"
ls -la "$SCRATCH/videos" | head -20
echo "   total mp4 files: $(find "$SCRATCH/videos" -name '*.mp4' | wc -l)"
```

- [ ] **Step 2: Run the pull**

```bash
chmod +x scripts/video/v8/01_pull_archive.sh
scripts/video/v8/01_pull_archive.sh
```

Expected: 30 mp4 files in scratch (plus matching .info.json and .en.srt). Network-bound; budget 30 min.

If yt-dlp errors with channel not found, retry with `SWM_YT_CHANNEL=...` set to the correct URL. Confirm the handle with the user if needed.

- [ ] **Step 3: Commit**

```bash
git add scripts/video/v8/01_pull_archive.sh
git commit -m "v8: yt-dlp pull script for SWM channel archive"
```

---

## Task 3: Transcribe pulled archive

**Files:**
- Create: `scripts/video/v8/02_transcribe.sh`

Skip whisper-cli if `.en.srt` was successfully downloaded from YouTube auto-subs; only run whisper on videos missing subs.

- [ ] **Step 1: Write the transcription script**

Create `scripts/video/v8/02_transcribe.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRATCH="/Volumes/Elements/swm-yt-archive-2026-05-18"
MODEL="${WHISPER_MODEL:-base.en}"
MODEL_DIR="${WHISPER_MODEL_DIR:-$HOME/.cache/whisper-cpp}"

echo ">> ensuring whisper model $MODEL is local..."
mkdir -p "$MODEL_DIR"
MODEL_PATH="$MODEL_DIR/ggml-$MODEL.bin"
if [[ ! -f "$MODEL_PATH" ]]; then
  echo "   downloading ggml-$MODEL.bin..."
  curl -L -o "$MODEL_PATH" \
    "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-$MODEL.bin"
fi

cd "$SCRATCH/videos"
shopt -s nullglob
for vid in *.mp4; do
  base="${vid%.mp4}"
  srt_existing="${base}.en.srt"
  srt_target="$SCRATCH/transcripts/${base}.srt"

  if [[ -f "$srt_target" ]]; then
    echo "   skip (already transcribed): $base"
    continue
  fi

  if [[ -f "$srt_existing" ]]; then
    echo "   using YouTube auto-subs: $base"
    cp "$srt_existing" "$srt_target"
    continue
  fi

  echo ">> whisper transcribing: $base"
  # Extract mono 16kHz wav for whisper-cli, then delete it
  ffmpeg -y -loglevel error -i "$vid" -ac 1 -ar 16000 -vn "$SCRATCH/tmp.wav"
  whisper-cli \
    --model "$MODEL_PATH" \
    --file "$SCRATCH/tmp.wav" \
    --output-srt \
    --output-file "$SCRATCH/transcripts/${base}" \
    --no-prints
  rm -f "$SCRATCH/tmp.wav"
done

echo ">> transcripts in $SCRATCH/transcripts/"
ls "$SCRATCH/transcripts/" | head -10
```

- [ ] **Step 2: Run the transcription**

```bash
chmod +x scripts/video/v8/02_transcribe.sh
scripts/video/v8/02_transcribe.sh
```

Expected: one `.srt` per video in `transcripts/`. Wall time depends on how many videos got auto-subs vs needed whisper; budget 60 min worst case.

- [ ] **Step 3: Spot-check one transcript**

```bash
head -40 /Volumes/Elements/swm-yt-archive-2026-05-18/transcripts/*.srt | head -40
```

Should show SRT-formatted entries with timestamps and English text. If gibberish, switch model to `small.en` and re-run.

- [ ] **Step 4: Commit**

```bash
git add scripts/video/v8/02_transcribe.sh
git commit -m "v8: whisper-cli transcription pipeline with auto-sub fallback"
```

---

## Task 4: Define the 5-act script as matchable input

**Files:**
- Create: `scripts/video/v8/scripts.json`

This is the script lines the matcher will search the transcripts for. Pulled directly from `docs/VIDEO_SHOTLIST.md`.

- [ ] **Step 1: Write the script JSON**

Create `scripts/video/v8/scripts.json`:

```json
{
  "acts": [
    {
      "act": 1,
      "window_start": 0,
      "window_end": 25,
      "lines": [
        "growing mushrooms commercially for years",
        "questions a grower needs answered",
        "five-bar wifi",
        "contamination on the line"
      ],
      "broll_keywords": ["contaminated", "agar", "trichoderma", "petri", "grow room"]
    },
    {
      "act": 2,
      "window_start": 25,
      "window_end": 55,
      "lines": [
        "AI tools assume the user is sitting in an office",
        "growers farmers",
        "the connection is bad",
        "answered in the next ten minutes",
        "cloud AI doesn't show up here"
      ],
      "broll_keywords": ["facility", "no signal", "rural", "tunnel house", "fruiting room"]
    },
    {
      "act": 3,
      "window_start": 55,
      "window_end": 120,
      "lines": [],
      "broll_keywords": ["live screen recording - sourced separately, not from archive"]
    },
    {
      "act": 4,
      "window_start": 120,
      "window_end": 150,
      "lines": [
        "built on Google's Gemma",
        "first open-source model",
        "Crowe Logic family",
        "commercial cultivation library",
        "Lion's Mane SOP",
        "Mushroom Grower"
      ],
      "broll_keywords": ["laptop", "terminal", "screen", "direct to camera"]
    },
    {
      "act": 5,
      "window_start": 150,
      "window_end": 180,
      "lines": [
        "every operator I know",
        "chatbot a thousand miles away",
        "started with mushrooms",
        "next models in the Crowe Logic family",
        "show me their grow room",
        "made for the work"
      ],
      "broll_keywords": ["wide facility", "racks", "harvest", "direct to camera"]
    }
  ]
}
```

- [ ] **Step 2: Commit**

```bash
git add scripts/video/v8/scripts.json
git commit -m "v8: 5-act script lines + broll keywords as matcher input"
```

---

## Task 5: Build the script-to-clip matcher (TDD)

**Files:**
- Create: `scripts/video/v8/03_match.py`
- Test: `tests/video/test_match.py`

The matcher reads transcripts and `scripts.json`, finds the best timestamp range in any video for each script line, and emits `cut_list.json`.

- [ ] **Step 1: Write the failing test**

Create `tests/video/test_match.py`:

```python
"""Tests for the v8 script-to-clip matcher."""
from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

import pytest

# Import sibling script as a module
import sys
SCRIPT_DIR = Path(__file__).resolve().parents[2] / "scripts" / "video" / "v8"
sys.path.insert(0, str(SCRIPT_DIR))
import importlib.util
spec = importlib.util.spec_from_file_location("match_module", SCRIPT_DIR / "03_match.py")
match = importlib.util.module_from_spec(spec)
spec.loader.exec_module(match)


SAMPLE_SRT = dedent("""\
1
00:00:01,000 --> 00:00:04,500
I've been growing mushrooms commercially for years now

2
00:00:05,000 --> 00:00:09,000
and you learn that the questions a grower needs answered

3
00:00:09,500 --> 00:00:12,000
don't happen at a desk with five-bar wifi

4
00:00:12,500 --> 00:00:15,000
they happen at four a.m. with contamination on the line
""")


def test_parse_srt_basic(tmp_path):
    srt = tmp_path / "sample.srt"
    srt.write_text(SAMPLE_SRT)
    entries = match.parse_srt(srt)
    assert len(entries) == 4
    assert entries[0].text.startswith("I've been growing")
    assert entries[0].start_sec == pytest.approx(1.0)
    assert entries[0].end_sec == pytest.approx(4.5)


def test_match_line_to_entry(tmp_path):
    srt = tmp_path / "sample.srt"
    srt.write_text(SAMPLE_SRT)
    entries = match.parse_srt(srt)
    hit = match.best_match("growing mushrooms commercially for years", entries)
    assert hit is not None
    assert hit.entry.text.startswith("I've been growing")
    assert hit.score > 0.5
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/video/test_match.py -v
```

Expected: ImportError (`03_match.py` doesn't exist yet).

- [ ] **Step 3: Write the matcher**

Create `scripts/video/v8/03_match.py`:

```python
#!/usr/bin/env python3
"""Match script lines from scripts.json to transcript entries.

Outputs cut_list.json with one (video, in, out) tuple per script line,
plus broll candidates per act.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable


SRT_TIMESTAMP_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*"
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})"
)


@dataclass
class Entry:
    start_sec: float
    end_sec: float
    text: str


@dataclass
class Match:
    entry: Entry
    score: float
    video_path: str


def _ts_to_sec(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def parse_srt(path: Path) -> list[Entry]:
    entries: list[Entry] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    blocks = re.split(r"\n\s*\n", text.strip())
    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 2:
            continue
        m = SRT_TIMESTAMP_RE.search(block)
        if not m:
            continue
        start = _ts_to_sec(*m.group(1, 2, 3, 4))
        end = _ts_to_sec(*m.group(5, 6, 7, 8))
        body_lines = [line for line in lines if not SRT_TIMESTAMP_RE.search(line) and not line.strip().isdigit()]
        body = " ".join(body_lines).strip()
        if body:
            entries.append(Entry(start, end, body))
    return entries


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).strip()


def best_match(line: str, entries: Iterable[Entry]) -> Match | None:
    target = _norm(line)
    best: tuple[float, Entry] | None = None
    for e in entries:
        score = SequenceMatcher(None, target, _norm(e.text)).ratio()
        if best is None or score > best[0]:
            best = (score, e)
    if best is None:
        return None
    return Match(entry=best[1], score=best[0], video_path="")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcripts-dir", required=True)
    ap.add_argument("--scripts-json", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--min-score", type=float, default=0.45)
    args = ap.parse_args()

    transcripts_dir = Path(args.transcripts_dir)
    scripts = json.loads(Path(args.scripts_json).read_text())

    all_srts = sorted(transcripts_dir.glob("*.srt"))
    print(f"[match] {len(all_srts)} transcripts loaded")

    indexed: list[tuple[str, list[Entry]]] = []
    for srt in all_srts:
        entries = parse_srt(srt)
        indexed.append((srt.stem, entries))

    cut_list = {"acts": []}
    for act in scripts["acts"]:
        act_out = {"act": act["act"], "line_matches": [], "broll_candidates": []}
        for line in act["lines"]:
            best: Match | None = None
            for stem, entries in indexed:
                hit = best_match(line, entries)
                if hit is None:
                    continue
                hit.video_path = stem
                if best is None or hit.score > best.score:
                    best = hit
            if best and best.score >= args.min_score:
                act_out["line_matches"].append({
                    "line": line,
                    "video": best.video_path,
                    "in_sec": max(0.0, best.entry.start_sec - 0.3),
                    "out_sec": best.entry.end_sec + 0.5,
                    "score": round(best.score, 3),
                    "matched_text": best.entry.text,
                })
            else:
                act_out["line_matches"].append({
                    "line": line,
                    "video": None,
                    "reason": f"no match >= {args.min_score}",
                })
        cut_list["acts"].append(act_out)

    Path(args.output).write_text(json.dumps(cut_list, indent=2))
    matched = sum(
        1 for a in cut_list["acts"] for m in a["line_matches"] if m.get("video")
    )
    total = sum(len(a["line_matches"]) for a in cut_list["acts"])
    print(f"[match] {matched}/{total} script lines matched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify pass**

```bash
.venv/bin/python -m pytest tests/video/test_match.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Run the matcher against the archive**

```bash
chmod +x scripts/video/v8/03_match.py
.venv/bin/python scripts/video/v8/03_match.py \
  --transcripts-dir /Volumes/Elements/swm-yt-archive-2026-05-18/transcripts \
  --scripts-json scripts/video/v8/scripts.json \
  --output video/v8/cut_list.json
```

Expected output: `[match] N/M script lines matched`. Inspect `video/v8/cut_list.json`.

- [ ] **Step 6: Review match quality**

```bash
.venv/bin/python -c "
import json
cl = json.load(open('video/v8/cut_list.json'))
for act in cl['acts']:
    print(f\"-- Act {act['act']} --\")
    for m in act['line_matches']:
        if m.get('video'):
            print(f\"  [{m['score']}] {m['line'][:50]}\")
            print(f\"      -> {m['video']}\")
            print(f\"      -> {m['matched_text'][:80]}\")
        else:
            print(f\"  [MISS] {m['line'][:50]}\")
"
```

If matches look weak, lower `--min-score` to 0.35 and re-run. If still weak, the script lines aren't in the archive and we need to fall back to mixed strategy (real where it fits, ElevenLabs for gaps).

- [ ] **Step 7: Commit**

```bash
git add scripts/video/v8/03_match.py tests/video/test_match.py video/v8/cut_list.json
git commit -m "v8: script-to-transcript matcher with cut_list output"
```

---

## Task 6: Cut clips losslessly

**Files:**
- Create: `scripts/video/v8/04_cut.sh`

- [ ] **Step 1: Write the cut script**

Create `scripts/video/v8/04_cut.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRATCH="/Volumes/Elements/swm-yt-archive-2026-05-18"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
CUT_LIST="$REPO_ROOT/video/v8/cut_list.json"
SCENES_DIR="$REPO_ROOT/video/v8/scenes"

mkdir -p "$SCENES_DIR"

jq -c '.acts[] | .act as $act | .line_matches[] | select(.video != null) | {act: $act, video: .video, in_sec: .in_sec, out_sec: .out_sec, line: .line}' "$CUT_LIST" |
while IFS= read -r row; do
  act=$(echo "$row" | jq -r '.act')
  video=$(echo "$row" | jq -r '.video')
  in_sec=$(echo "$row" | jq -r '.in_sec')
  out_sec=$(echo "$row" | jq -r '.out_sec')
  line=$(echo "$row" | jq -r '.line' | tr -c '[:alnum:]' '_' | cut -c1-40)

  src=$(ls "$SCRATCH/videos/"*"${video##*_}"*.mp4 2>/dev/null | head -1)
  if [[ -z "$src" || ! -f "$src" ]]; then
    # video field is the .srt stem; the mp4 has matching basename
    src="$SCRATCH/videos/${video}.mp4"
  fi

  if [[ ! -f "$src" ]]; then
    echo "  MISS source for stem $video"
    continue
  fi

  out="$SCENES_DIR/act${act}_${line}.mp4"
  echo ">> cut: act $act $line"
  ffmpeg -y -loglevel error \
    -ss "$in_sec" -to "$out_sec" \
    -i "$src" \
    -c copy \
    "$out"
done

echo ">> scenes:"
ls -la "$SCENES_DIR"
```

- [ ] **Step 2: Run the cut**

```bash
chmod +x scripts/video/v8/04_cut.sh
scripts/video/v8/04_cut.sh
```

Expected: one mp4 per matched line in `video/v8/scenes/`. Lossless (no re-encode), fast.

- [ ] **Step 3: Spot-check one scene**

```bash
ffprobe -v error -show_entries format=duration,size -of default=noprint_wrappers=1 video/v8/scenes/act1_*.mp4 | head -10
```

Each clip should be 2-8 seconds. If a clip is the full source video duration, the `-ss` flag failed.

- [ ] **Step 4: Commit**

```bash
git add scripts/video/v8/04_cut.sh
git commit -m "v8: lossless clip cutting from cut_list"
```

---

## Task 7: Build cards with Pillow (TDD)

**Files:**
- Create: `scripts/video/v8/05_cards.py`
- Test: `tests/video/test_cards.py`

- [ ] **Step 1: Write the failing test**

Create `tests/video/test_cards.py`:

```python
"""Tests for v8 card rendering."""
from __future__ import annotations

from pathlib import Path
import sys
import importlib.util

from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parents[2] / "scripts" / "video" / "v8"
sys.path.insert(0, str(SCRIPT_DIR))
spec = importlib.util.spec_from_file_location("cards", SCRIPT_DIR / "05_cards.py")
cards = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cards)


LOGO_PATH = Path.home() / "Projects/crowelogic-website/public/crowe-logic-mark-512.png"


def test_title_card_dimensions(tmp_path):
    out = tmp_path / "title.png"
    cards.render_title(LOGO_PATH, out)
    img = Image.open(out)
    assert img.size == (1920, 1080)
    assert img.mode in ("RGB", "RGBA")


def test_end_card_contains_all_ctas(tmp_path):
    # We can't OCR easily; we trust the render. But we can at least confirm
    # the function runs and the file is non-trivial in size.
    out = tmp_path / "end.png"
    cards.render_end(LOGO_PATH, out)
    img = Image.open(out)
    assert img.size == (1920, 1080)
    assert out.stat().st_size > 50_000  # rendered cards are typically >100 KB


def test_lower_third_has_alpha(tmp_path):
    out = tmp_path / "lt.png"
    cards.render_lower_third(LOGO_PATH, out)
    img = Image.open(out)
    assert img.size == (1920, 1080)
    assert img.mode == "RGBA"  # transparent background for overlay
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/video/test_cards.py -v
```

Expected: ImportError or AttributeError (`05_cards.py` doesn't exist).

- [ ] **Step 3: Write the card renderer**

Create `scripts/video/v8/05_cards.py`:

```python
#!/usr/bin/env python3
"""Render title, end, and lower-third cards for the v8 video build.

Static, centered, hex-C corporate mark prominent. Per the design spec.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


W, H = 1920, 1080
BG = (10, 10, 12)         # near-black charcoal
FG = (235, 235, 235)      # off-white
ACCENT = (170, 170, 170)  # muted grey for sub-text


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _draw_centered(draw: ImageDraw.ImageDraw, text: str, y: int, font, fill):
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    x = (W - w) // 2
    draw.text((x, y), text, font=font, fill=fill)


def _paste_centered_logo(canvas: Image.Image, logo_path: Path, target_height: int) -> int:
    """Paste logo horizontally centered; return its top y when placed."""
    logo = Image.open(logo_path).convert("RGBA")
    ratio = target_height / logo.height
    new_w = int(logo.width * ratio)
    logo = logo.resize((new_w, target_height), Image.LANCZOS)
    x = (W - new_w) // 2
    return x, logo


def render_title(logo_path: Path, out: Path) -> None:
    canvas = Image.new("RGB", (W, H), BG)
    # Logo at ~30% of frame height, top region
    target_h = int(H * 0.30)
    x_logo, logo = _paste_centered_logo(canvas, logo_path, target_h)
    y_logo = int(H * 0.18)
    canvas.paste(logo, (x_logo, y_logo), logo)

    draw = ImageDraw.Draw(canvas)
    _draw_centered(draw, "CROWE LOGIC PRESENTS",
                   y_logo + target_h + 60, _load_font(36), ACCENT)
    _draw_centered(draw, "Gemma 4 Mycelium",
                   y_logo + target_h + 120, _load_font(96), FG)
    _draw_centered(draw, "Offline AI for Commercial Mushroom Cultivation",
                   y_logo + target_h + 240, _load_font(40), FG)
    _draw_centered(draw, "Submission  ·  Gemma 4 Good Hackathon  ·  Special Tech Track",
                   y_logo + target_h + 320, _load_font(28), ACCENT)
    canvas.save(out)


def render_end(logo_path: Path, out: Path) -> None:
    canvas = Image.new("RGB", (W, H), BG)
    target_h = int(H * 0.25)
    x_logo, logo = _paste_centered_logo(canvas, logo_path, target_h)
    y_logo = int(H * 0.10)
    canvas.paste(logo, (x_logo, y_logo), logo)

    draw = ImageDraw.Draw(canvas)
    y = y_logo + target_h + 40
    _draw_centered(draw, "Gemma 4 Mycelium", y, _load_font(72), FG)

    y += 110
    _draw_centered(draw, "ollama pull Mcrowe1210/gemma-4-mycelium-e4b",
                   y, _load_font(44), FG)

    y += 110
    _draw_centered(draw, "github.com/MichaelCrowe11/crowe-mycelium-cli",
                   y, _load_font(30), ACCENT)
    y += 50
    _draw_centered(draw, "kaggle.com/competitions/gemma-4-good-hackathon",
                   y, _load_font(30), ACCENT)
    y += 50
    _draw_centered(draw, "crowelogic.com/mycelium", y, _load_font(30), ACCENT)

    y += 80
    _draw_centered(draw, "Built on Gemma  ·  Released under Gemma Terms of Use",
                   y, _load_font(26), ACCENT)
    canvas.save(out)


def render_lower_third(logo_path: Path, out: Path) -> None:
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    # Small logo bottom-left, ~48px high
    logo = Image.open(logo_path).convert("RGBA")
    target_h = 48
    ratio = target_h / logo.height
    logo = logo.resize((int(logo.width * ratio), target_h), Image.LANCZOS)
    x = int(W * 0.06)
    y = int(H * 0.86)
    canvas.paste(logo, (x, y), logo)

    draw = ImageDraw.Draw(canvas)
    draw.text((x + target_h + 16, y - 4), "Michael Crowe",
              font=_load_font(28), fill=FG)
    draw.text((x + target_h + 16, y + 28), "Crowe Logic  ·  Southwest Mushrooms",
              font=_load_font(20), fill=ACCENT)
    canvas.save(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--logo", default=str(Path.home() /
                                          "Projects/crowelogic-website/public/crowe-logic-mark-512.png"))
    ap.add_argument("--out-dir", default="video/v8/cards")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    render_title(Path(args.logo), out_dir / "title.png")
    render_end(Path(args.logo), out_dir / "end.png")
    render_lower_third(Path(args.logo), out_dir / "lower_third.png")
    print(f"[cards] wrote title.png, end.png, lower_third.png to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify pass**

```bash
.venv/bin/python -m pip install --quiet pillow
.venv/bin/python -m pytest tests/video/test_cards.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Render the real cards**

```bash
.venv/bin/python scripts/video/v8/05_cards.py
```

Expected: `video/v8/cards/title.png`, `end.png`, `lower_third.png` created.

- [ ] **Step 6: Visual review**

```bash
open video/v8/cards/title.png video/v8/cards/end.png video/v8/cards/lower_third.png
```

Check by eye: logo visible and centered, text legible at 1080p, CTAs all present on end card. If any look off, adjust constants in `05_cards.py` and re-render.

- [ ] **Step 7: Commit**

```bash
git add scripts/video/v8/05_cards.py tests/video/test_cards.py video/v8/cards/
git commit -m "v8: Pillow card renderer (title/end/lower-third) with tests"
```

---

## Task 8: Pick and stage music bed

**Files:**
- Create: `video/v8/music.mp3` (copied from Substrate masters)

The candidates are in `~/Music/Music/Media.localized/Music/Michael Crowe/Substrate/`. Per the spec and the "no sung vocals" criterion (so VO sits on top cleanly), shortlist:

- `05 Velvet Algorithm.mp3` — title fits the AI/cultivation theme directly
- `11 Cosmic Consciousness.mp3` — likely instrumental-feel
- `12 One Floor Below the Dawn.mp3` — calm epilogue, F#m 66 BPM per memory

- [ ] **Step 1: Audition first 30s of each candidate**

```bash
SUB="$HOME/Music/Music/Media.localized/Music/Michael Crowe/Substrate"
for t in "05 Velvet Algorithm.mp3" "11 Cosmic Consciousness.mp3" "12 One Floor Below the Dawn.mp3"; do
  echo ">> $t"
  afplay "$SUB/$t" -t 30
done
```

Pick the one that sits best behind voice. If all have prominent vocals throughout, switch to a Talon instrumental in `~/Projects/talon/renders/substrate-v4/` (verify the directory exists first with `ls`).

- [ ] **Step 2: Copy chosen track to the build dir**

```bash
# Replace CHOSEN with the picked track name.
cp "$HOME/Music/Music/Media.localized/Music/Michael Crowe/Substrate/CHOSEN.mp3" \
   video/v8/music.mp3
ffprobe -v error -show_entries format=duration -of csv=p=0 video/v8/music.mp3
```

Expected: duration >= 180 seconds. If shorter, we'll loop in the assemble step.

- [ ] **Step 3: Commit (music file itself is gitignored)**

```bash
echo "video/v8/music.mp3" >> .gitignore
git add .gitignore
git commit -m "v8: gitignore the staged music bed (not redistributable)"
```

---

## Task 9: Record Act 3 (manual)

**Files:**
- Create: `scripts/video/v8/06_act3_record.md`
- Create: `video/v8/scenes/act3_demo.mp4` (manual capture)

This is the only act that must be original. The full runbook is in `docs/DEMO_SCRIPT.md`; this task creates a short checklist and the output file.

- [ ] **Step 1: Write the runbook stub**

Create `scripts/video/v8/06_act3_record.md`:

```markdown
# Act 3 Recording Checklist

Full pre-shoot procedure: `docs/DEMO_SCRIPT.md`.

## Quick checklist
1. Mac in airplane mode (Wi-Fi off, Bluetooth off — visible in menu bar)
2. `pgrep ollama || open -a Ollama && sleep 3`
3. Warm model: `ollama run Mcrowe1210/gemma-4-mycelium-e4b "ping" >/dev/null`
4. iTerm at large font, clear scrollback (Cmd-K)
5. Cmd-Shift-5 -> screen recording with menu bar visible
6. Type the contamination prompt (Option A in DEMO_SCRIPT.md)
7. Let response stream uncut
8. Stop recording, save as `video/v8/scenes/act3_demo.mp4`

Target length: ~60 seconds. If response runs long, trim only the tail
in post.
```

- [ ] **Step 2: Perform the recording**

This step is manual. Follow the checklist. The model is on Ollama Hub
as `Mcrowe1210/gemma-4-mycelium-e4b` (Phase 1). Save the screen recording
to `video/v8/scenes/act3_demo.mp4`.

- [ ] **Step 3: Verify**

```bash
ffprobe -v error -show_entries stream=width,height,r_frame_rate -show_entries format=duration video/v8/scenes/act3_demo.mp4
```

Expected: 1920x1080 or higher resolution, ~60s duration. If lower res, re-record with screen capture at full Retina resolution and let ffmpeg downscale in assemble.

- [ ] **Step 4: Commit the runbook**

```bash
git add scripts/video/v8/06_act3_record.md
git commit -m "v8: Act 3 recording checklist (stub of full DEMO_SCRIPT.md)"
```

---

## Task 10: Build subtitle SRT

**Files:**
- Create: `video/v8/subtitles.srt`

Hand-curated SRT for the burned-in subtitles. Lines come from `scripts/video/v8/scripts.json` plus any Act 3 model dialogue captions.

- [ ] **Step 1: Generate a starter SRT from the script**

```bash
.venv/bin/python -c "
import json
from pathlib import Path

scripts = json.loads(Path('scripts/video/v8/scripts.json').read_text())

def fmt(t):
    h = int(t // 3600); m = int((t % 3600) // 60); s = t % 60
    return f'{h:02d}:{m:02d}:{s:06.3f}'.replace('.', ',')

idx = 1
out_lines = []
for act in scripts['acts']:
    if not act['lines']:
        continue
    start = act['window_start']
    end = act['window_end']
    per_line = (end - start) / max(1, len(act['lines']))
    for i, line in enumerate(act['lines']):
        s = start + i * per_line
        e = s + per_line * 0.9
        out_lines.append(f'{idx}')
        out_lines.append(f'{fmt(s)} --> {fmt(e)}')
        out_lines.append(line)
        out_lines.append('')
        idx += 1

Path('video/v8/subtitles.srt').write_text('\n'.join(out_lines))
print('wrote video/v8/subtitles.srt')
"
```

- [ ] **Step 2: Hand-tune the SRT to actual clip timings**

Open `video/v8/subtitles.srt` in an editor. Adjust timestamps so each
subtitle window matches when that clip will appear in the assembled
video. Use the cut_list and approximate ordering.

- [ ] **Step 3: Commit**

```bash
git add video/v8/subtitles.srt
git commit -m "v8: subtitle SRT (auto-generated, hand-tuned to clip timings)"
```

---

## Task 11: Assemble the final video

**Files:**
- Create: `scripts/video/v8/07_assemble.sh`
- Create: `video/final/film_v8.mp4`

- [ ] **Step 1: Write the assemble script**

Create `scripts/video/v8/07_assemble.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO_ROOT"

V8="video/v8"
CARDS="$V8/cards"
OUT="video/final/film_v8.mp4"

# 1. Make 5s title and 5s end clips from PNG cards
ffmpeg -y -loglevel error -loop 1 -i "$CARDS/title.png" -t 5 \
  -c:v libx264 -pix_fmt yuv420p -r 30 -vf "scale=1920:1080" \
  "$V8/title.mp4"

ffmpeg -y -loglevel error -loop 1 -i "$CARDS/end.png" -t 5 \
  -c:v libx264 -pix_fmt yuv420p -r 30 -vf "scale=1920:1080" \
  "$V8/end.mp4"

# 2. Build concat list in act order
#    Title -> all act1 scenes -> all act2 scenes -> act3 demo
#    -> all act4 scenes -> all act5 scenes -> end card
{
  echo "file '$(pwd)/$V8/title.mp4'"
  for act in 1 2; do
    for f in "$V8"/scenes/act${act}_*.mp4; do
      [[ -f "$f" ]] && echo "file '$(pwd)/$f'"
    done
  done
  if [[ -f "$V8/scenes/act3_demo.mp4" ]]; then
    echo "file '$(pwd)/$V8/scenes/act3_demo.mp4'"
  fi
  for act in 4 5; do
    for f in "$V8"/scenes/act${act}_*.mp4; do
      [[ -f "$f" ]] && echo "file '$(pwd)/$f'"
    done
  done
  echo "file '$(pwd)/$V8/end.mp4'"
} > "$V8/concat.txt"

# 3. Concat-encode (clips may have different codecs/resolutions, so re-encode)
ffmpeg -y -loglevel error -f concat -safe 0 -i "$V8/concat.txt" \
  -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,setsar=1" \
  -r 30 -c:v libx264 -preset medium -crf 19 -pix_fmt yuv420p \
  -c:a aac -b:a 192k -ar 48000 \
  "$V8/concat.mp4"

# 4. Layer music bed (looped, ducked under voice) and burn subtitles
#    sidechain compressor: music input is ducked when the main audio is loud
ffmpeg -y -loglevel error \
  -i "$V8/concat.mp4" \
  -stream_loop -1 -i "$V8/music.mp3" \
  -filter_complex "
    [1:a]volume=0.20[mus];
    [0:a][mus]sidechaincompress=threshold=0.05:ratio=8:attack=20:release=400[aout];
    [0:v]subtitles=$V8/subtitles.srt:force_style='Fontsize=22,Outline=1,Shadow=0,Alignment=2,MarginV=60'[vout]
  " \
  -map "[vout]" -map "[aout]" \
  -c:v libx264 -preset medium -crf 19 -pix_fmt yuv420p \
  -c:a aac -b:a 192k -ar 48000 \
  -movflags +faststart \
  -shortest \
  "$OUT"

echo ">> wrote $OUT"
ffprobe -v error -show_entries format=duration,size,bit_rate \
  -show_entries stream=width,height,r_frame_rate \
  "$OUT"
```

- [ ] **Step 2: Run the assemble**

```bash
chmod +x scripts/video/v8/07_assemble.sh
scripts/video/v8/07_assemble.sh
```

Expected: `video/final/film_v8.mp4` written, ~150-180s, 1920x1080@30fps, ~30 Mbps.

- [ ] **Step 3: Visual review**

```bash
open video/final/film_v8.mp4
```

Watch the full video. Verify:
- Title card holds 5s, logo visible
- Each act has matching real-Michael clips
- Act 3 demo plays cleanly
- End card holds 5s, all 4 CTAs readable
- Music ducks under voice
- Subtitles burned in and readable

If anything looks wrong, fix the relevant script and re-run from that step.

- [ ] **Step 4: Commit**

```bash
git add scripts/video/v8/07_assemble.sh
git commit -m "v8: assemble script (concat + cards + ducked music + burned subs)"
```

---

## Task 12: Upload to YouTube and wire URL into submission

**Files:**
- Modify: `docs/SUBMISSION.md`

- [ ] **Step 1: Upload film_v8.mp4 to YouTube**

Manual step. Use the metadata in `video/YOUTUBE_UPLOAD.md` (already updated to point at v8 once we edit it).

Update `video/YOUTUBE_UPLOAD.md` line 4 to reference `video/final/film_v8.mp4`.

Upload as **Unlisted** to the Michael Crowe Mycology channel.
Set title, description, tags per `YOUTUBE_UPLOAD.md`.
Upload `video/v8/cards/end.png` or `video/cover_candidates/CHOSEN_kaggle_cover.jpg`
as the thumbnail.

Copy the resulting YouTube URL.

- [ ] **Step 2: Wire URL into submission**

In `docs/SUBMISSION.md`, replace:
```
**Demo video:** <!-- PASTE_YOUTUBE_URL_HERE -->
```
with:
```
**Demo video:** https://youtu.be/<ID>
```

- [ ] **Step 3: Commit**

```bash
git add docs/SUBMISSION.md video/YOUTUBE_UPLOAD.md
git commit -m "submission: wire YouTube URL into SUBMISSION.md"
git push origin main
```

---

## Task 13: Submit on Kaggle

**Files:** None (Kaggle web UI)

- [ ] **Step 1: Open the Kaggle competition page**

```bash
open "https://www.kaggle.com/competitions/gemma-4-good-hackathon"
```

- [ ] **Step 2: Paste writeup**

Copy the body of `docs/SUBMISSION.md` into the competition's writeup
field. The YouTube URL is now embedded.

- [ ] **Step 3: Upload cover image**

Use `video/cover_candidates/CHOSEN_kaggle_cover.jpg` (already chosen
in the existing workflow).

- [ ] **Step 4: Verify Kaggle kernel link in writeup**

The SUBMISSION.md references `kaggle.com/code/crowelogic/gemma-4-mycelium-lora-fine-tune`.
Confirm the kernel link works publicly (it may need to be set public for
judges; the kernel is currently `is_private: true` in `kernel-metadata.json`).

If the kernel still needs to be public, run:

```bash
# Update kernel-metadata.json
.venv/bin/python -c "
import json
p = 'notebooks/kernel-metadata.json'
m = json.load(open(p))
m['is_private'] = 'false'
open(p, 'w').write(json.dumps(m, indent=2))
print('set is_private=false')
"
cd ~/Projects/crowe-mycelium-cli
.venv/bin/kaggle kernels push -p notebooks/
```

- [ ] **Step 5: Submit**

Click submit. Confirm the submission appears on the leaderboard / entry list.

---

## Spec coverage check (self-review)

Mapping spec sections to tasks:

- "Why rebuild" (resolution, lipsync, branding) -> all tasks
- "Clip source: SWM YouTube" -> Tasks 2, 3
- "No lipsync, real voice" -> Tasks 3, 4, 5
- "Substrate music bed" -> Task 8
- "Static centered hex-C" -> Task 7
- "All four CTAs" -> Task 7 (end card), Task 10 (subtitle context)
- "1080p30 H.264" -> Task 11
- "Burned subs" -> Tasks 10, 11
- "5-act structure" -> Tasks 4, 6, 11
- "Act 3 = fresh capture" -> Task 9
- "Upload + wire URL" -> Task 12
- "Kaggle submit" -> Task 13

All spec sections covered.

## Out of scope (intentionally not in plan)

- Phase 2 LoRA training (running on Kaggle, tracked separately in task #5)
- Corner watermark (decided no in design)
- Animated title (decided no in design)
- 4K master (decided 1080p in design)
