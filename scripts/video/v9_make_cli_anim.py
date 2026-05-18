#!/usr/bin/env python3
"""Render a 65s 1280x720 terminal animation for film_v9 Act 3.

We show only CLI surface that produces deterministic, controllable output
(info / models / --help). We type a `run` command character-by-character
but cut to b-roll BEFORE any model response, so nothing on screen can
be "wrong" model output.

The screencap that originally lived at video/screencap/act3.mp4 contained
a model response that the user flagged as incorrect; this replaces it
with a clean, content-accurate terminal recording.
"""
from __future__ import annotations
import os, subprocess, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT_DIR = Path(__file__).resolve().parents[2] / "video" / "v9" / "cli_anim"
OUT_DIR.mkdir(parents=True, exist_ok=True)
FRAMES_DIR = OUT_DIR / "frames"
FRAMES_DIR.mkdir(exist_ok=True)
W, H = 1280, 720
BG = (13, 17, 23)          # GitHub dark
FG = (220, 220, 220)        # off-white
DIM = (140, 150, 160)
ACCENT = (88, 166, 255)     # blue
GREEN = (87, 192, 124)
AMBER = (255, 191, 0)
RED = (240, 80, 80)
FPS = 30

# Try preferred monospace fonts in order
FONT_CANDIDATES = [
    "/System/Library/Fonts/Menlo.ttc",
    "/System/Library/Fonts/Monaco.ttf",
    "/System/Library/Fonts/SFNSMono.ttf",
    "/Library/Fonts/Menlo.ttc",
]
def load_font(size: int) -> ImageFont.FreeTypeFont:
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()

FONT = load_font(22)
FONT_BOLD = load_font(22)
FONT_SMALL = load_font(16)
LINE_H = 28
LEFT = 40
TOP = 80

# Title bar
TITLE_BAR_H = 56

def new_canvas() -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    # Title bar
    d.rectangle((0, 0, W, TITLE_BAR_H), fill=(22, 27, 34))
    # Window controls
    for i, color in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        cx = 28 + i * 24
        d.ellipse((cx-7, 20, cx+7, 34), fill=color)
    # Title text
    d.text((W//2 - 130, 18), "crowe-mycelium  ·  zsh", font=FONT_SMALL, fill=DIM)
    return img

def render_lines(lines: list[tuple[str, tuple]], frame_idx: int) -> Path:
    """Render a frame with given lines (text, color). Last entry can include a cursor."""
    img = new_canvas()
    d = ImageDraw.Draw(img)
    y = TOP
    for text, color in lines:
        d.text((LEFT, y), text, font=FONT, fill=color)
        y += LINE_H
    # Save
    out = FRAMES_DIR / f"frame_{frame_idx:06d}.png"
    img.save(out)
    return out

# Build the timeline as a sequence of (duration_seconds, lines) states.
# Cursor is shown via the last line ending with "█" or "_".
PROMPT = "michael@crowe ~/Projects/crowe-mycelium-cli %"

def prompt_line(text: str = "", cursor: bool = True) -> tuple[str, tuple]:
    block = "▌" if cursor else ""
    return (f"{PROMPT} {text}{block}", FG)

def output_lines(text_block: str) -> list[tuple[str, tuple]]:
    return [(ln, FG) for ln in text_block.rstrip().split("\n")]

# Timeline -----------------------------------------------------------
timeline: list[tuple[float, list[tuple[str, tuple]]]] = []

# Scene 1: empty prompt (2s)
timeline.append((2.0, [prompt_line("")]))

# Scene 2: typing `crowe-mycelium --help` (3s) - show progressive states
help_cmd = "crowe-mycelium --help"
for i in range(1, len(help_cmd) + 1):
    timeline.append((0.07, [prompt_line(help_cmd[:i])]))

# Scene 3: help output (5s)
help_out = """Usage: crowe-mycelium [OPTIONS] COMMAND [ARGS]...

  Crowe Mycelium - offline cultivation intelligence built on Gemma 4.

Commands:
  chat    Start an interactive chat session.
  info    Show model and backend status.
  models  List registered models.
  run     Run a single prompt and stream the answer to stdout."""
timeline.append((5.0, [prompt_line(help_cmd, cursor=False)] + output_lines(help_out) + [("", FG), prompt_line("")]))

# Scene 4: typing `crowe-mycelium info` (2.5s)
info_cmd = "crowe-mycelium info"
prior4 = [prompt_line(help_cmd, cursor=False)] + output_lines(help_out)[:4] + [("...", DIM), ("", FG)]
for i in range(1, len(info_cmd) + 1):
    timeline.append((0.07, prior4 + [prompt_line(info_cmd[:i])]))

# Scene 5: info output (6s) - Crowe Logic identity card
info_out = """ ┌──────────────────────────────────────────────────────────┐
 │  model         gemma-4-mycelium-e4b                       │
 │  label         Gemma 4 Mycelium                           │
 │  base          google/gemma-4-e4b (Gemma 4)               │
 │  ollama tag    Mcrowe1210/gemma-4-mycelium-e4b            │
 │  context       8192                                       │
 │  license       Gemma Terms of Use                         │
 └──────────────────────────────────────────────────────────┘
 Gemma 4 Mycelium is built on Google Gemma."""
timeline.append((6.0, prior4 + [prompt_line(info_cmd, cursor=False)] + output_lines(info_out) + [("", FG), prompt_line("")]))

# Scene 6: typing `crowe-mycelium models` (2.5s)
models_cmd = "crowe-mycelium models"
prior6 = prior4 + [prompt_line(info_cmd, cursor=False)] + output_lines(info_out)[-3:] + [("", FG)]
for i in range(1, len(models_cmd) + 1):
    timeline.append((0.07, prior6 + [prompt_line(models_cmd[:i])]))

# Scene 7: models output (5s)
models_out = """ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  name                   label              base
 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  gemma-4-mycelium-e4b   Gemma 4 Mycelium   google/gemma-4-e4b
 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""
timeline.append((5.0, prior6 + [prompt_line(models_cmd, cursor=False)] + output_lines(models_out) + [("", FG), prompt_line("")]))

# Scene 8: typing `crowe-mycelium chat` (2.5s)
chat_cmd = "crowe-mycelium chat"
prior8 = prior6 + [prompt_line(models_cmd, cursor=False)] + output_lines(models_out)[-3:] + [("", FG)]
for i in range(1, len(chat_cmd) + 1):
    timeline.append((0.07, prior8 + [prompt_line(chat_cmd[:i])]))

# Scene 9: chat banner (3s)
chat_banner = """Crowe Mycelium · Gemma 4 Mycelium · offline mode
Type your question, or :q to quit.

>"""
prior9 = prior8 + [prompt_line(chat_cmd, cursor=False)] + output_lines(chat_banner)
timeline.append((3.0, prior9[:-1] + [("> ▌", ACCENT)]))

# Scene 10: typing a real grower question (8s, slow)
question = "what would cause pink spots on a lion's mane fruiting block?"
for i in range(1, len(question) + 1):
    timeline.append((0.13, prior9[:-1] + [(f"> {question[:i]}▌", ACCENT)]))

# Scene 11: hold full question, blinking cursor (2s) - then cuts to b-roll
timeline.append((2.0, prior9[:-1] + [(f"> {question}", ACCENT), ("", FG), ("[thinking...]", AMBER)]))

# --------------------------------------------------------------------
total = sum(t for t, _ in timeline)
print(f"Total timeline: {total:.2f}s across {len(timeline)} states")

# Render frames - for each state, emit (duration*FPS) duplicates
frame_idx = 0
for dur, lines in timeline:
    n_frames = max(1, int(round(dur * FPS)))
    p = render_lines(lines, frame_idx)
    for _ in range(n_frames - 1):
        # symlink duplicate frames to save IO
        frame_idx += 1
        dup = FRAMES_DIR / f"frame_{frame_idx:06d}.png"
        if dup.exists():
            dup.unlink()
        dup.symlink_to(p.name)
    frame_idx += 1

print(f"Rendered {frame_idx} frames at {FPS}fps")

# Compose to mp4
out_mp4 = OUT_DIR.parent / "cli_anim.mp4"
cmd = [
    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
    "-framerate", str(FPS),
    "-i", str(FRAMES_DIR / "frame_%06d.png"),
    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
    "-pix_fmt", "yuv420p",
    "-vf", f"fps={FPS}",
    "-movflags", "+faststart",
    str(out_mp4),
]
subprocess.check_call(cmd)
print(f"Wrote {out_mp4}")

# Probe
import json
dur_proc = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "default=noprint_wrappers=1:nokey=1", str(out_mp4)],
                           capture_output=True, text=True)
print(f"Final duration: {dur_proc.stdout.strip()}s")
