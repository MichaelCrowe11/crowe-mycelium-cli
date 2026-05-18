#!/usr/bin/env python3
"""Render a scripted-typewriter terminal demo for Act 3.

This is NOT a screen capture — it's a brand-styled animation of the same
prompt + response a viewer would see if they ran the command themselves.
The response is real model output (captured in advance via
``ollama run Mcrowe1210/gemma-4-mycelium-e4b``); only the typing animation
is synthesised so we get controlled pacing and brand-consistent visuals.

Frame sequence:
    0.0s   blank terminal with cursor blinking, gold-on-ink prompt
    1.0s   prompt typed char-by-char (~28 chars/sec)
    +0.6s  press Enter, cursor moves to next line
    +1.2s  model "thinking" — spinner dots
    +Ns    response streamed char-by-char (~55 chars/sec)
    +2.0s  hold final frame

Output: video/screencap/act3.mp4 at 1280x720 25fps yuv420p (drop-in
replacement for the placeholder card; the recut script auto-uses it).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_MP4 = REPO_ROOT / "video" / "screencap" / "act3.mp4"
TMP = REPO_ROOT / "video" / "tmp_act3_frames"
PROMPT_FILE = Path("/tmp/myc_prompt.txt")
RESPONSE_FILE = Path("/tmp/myc_response.txt")

W, H = 1280, 720
FPS = 25
BG = (24, 24, 28)           # desktop wallpaper-ish dark grey behind terminal
TERM_BG = (16, 16, 19)      # terminal window interior
TITLE_BG = (38, 38, 42)     # title bar
GOLD = (191, 166, 105)
DIM_TEXT = (220, 220, 220)
SUBTLE = (140, 140, 140)
SHELL_PROMPT_USER = "crowelogic@mycelium"
SHELL_PROMPT_PATH = "~"
SHELL_PROMPT_CHAR = "%"
TYPE_CPS_USER = 28      # typing speed for user prompt
TYPE_CPS_MODEL = 55     # streaming speed for model response
THINK_SECONDS = 1.2
HOLD_SECONDS = 2.0
INTRO_SECONDS = 0.8

# Terminal window dimensions (inset on the 1280x720 frame)
WIN_W, WIN_H = 1000, 560
WIN_X = (W - WIN_W) // 2
WIN_Y = (H - WIN_H) // 2 - 10
TITLE_H = 28

# Layout inside window
PAD_X, PAD_Y = 36, 24
LINE_HEIGHT = 22
FONT_SIZE = 14
WRAP_COLS = 92


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    # Menlo Bold for prompts is a nice cinematic look
    path = "/System/Library/Fonts/Menlo.ttc"
    try:
        return ImageFont.truetype(path, size, index=1 if bold else 0)
    except OSError:
        return ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", size)


def _wrap(text: str, cols: int) -> list[str]:
    out = []
    for para in text.splitlines():
        if not para.strip():
            out.append("")
            continue
        words = para.split(" ")
        line = ""
        for w in words:
            if len(line) + len(w) + 1 <= cols:
                line = (line + " " + w) if line else w
            else:
                out.append(line)
                line = w
        if line:
            out.append(line)
    return out


def _frame(prompt_typed: str, response_typed: list[str], thinking: int = 0,
           cursor_on: bool = True, with_prompt_newline: bool = False) -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    font_p = _font(FONT_SIZE, bold=True)
    font_r = _font(FONT_SIZE)

    # Terminal window — title bar + interior
    # Title bar
    draw.rounded_rectangle(
        [WIN_X, WIN_Y, WIN_X + WIN_W, WIN_Y + TITLE_H],
        radius=8, fill=TITLE_BG,
    )
    # Traffic-light buttons (macOS style)
    lights_y = WIN_Y + TITLE_H // 2
    for i, color in enumerate([(252, 99, 93), (252, 188, 47), (40, 200, 64)]):
        cx = WIN_X + 16 + i * 18
        draw.ellipse([cx - 6, lights_y - 6, cx + 6, lights_y + 6], fill=color)
    # Title text
    title_text = "ollama — Mcrowe1210/gemma-4-mycelium-e4b — 92x24"
    tf = _font(11)
    tb = draw.textbbox((0, 0), title_text, font=tf)
    tw = tb[2] - tb[0]
    draw.text((WIN_X + (WIN_W - tw) / 2, WIN_Y + 7), title_text, font=tf, fill=(200, 200, 200))
    # Interior
    draw.rounded_rectangle(
        [WIN_X, WIN_Y + TITLE_H, WIN_X + WIN_W, WIN_Y + WIN_H],
        radius=8, fill=TERM_BG,
    )
    # Cover the rounded top corners of the interior with a square top so the
    # title bar reads as a unified window (avoid overlapping rounded edges).
    draw.rectangle([WIN_X, WIN_Y + TITLE_H, WIN_X + WIN_W, WIN_Y + TITLE_H + 10], fill=TERM_BG)

    interior_x0 = WIN_X + PAD_X
    interior_y0 = WIN_Y + TITLE_H + PAD_Y

    # Prompt line
    prompt_prefix = f"{SHELL_PROMPT_USER} {SHELL_PROMPT_PATH} {SHELL_PROMPT_CHAR} "
    y = interior_y0
    bbox = draw.textbbox((0, 0), prompt_prefix, font=font_p)
    draw.text((interior_x0, y), prompt_prefix, font=font_p, fill=GOLD)
    px = interior_x0 + (bbox[2] - bbox[0])
    draw.text((px, y), prompt_typed, font=font_r, fill=DIM_TEXT)
    if cursor_on and not with_prompt_newline and thinking == 0 and not response_typed:
        cw = draw.textbbox((0, 0), "M", font=font_r)
        ch = cw[3] - cw[1]
        cur_x = px + draw.textbbox((0, 0), prompt_typed, font=font_r)[2]
        draw.rectangle([cur_x + 2, y + 2, cur_x + 10, y + ch + 2], fill=GOLD)

    y += LINE_HEIGHT
    if with_prompt_newline and thinking > 0:
        dot_str = "." * thinking
        draw.text((interior_x0, y), f"  {dot_str}", font=font_r, fill=SUBTLE)
        y += LINE_HEIGHT

    if response_typed:
        y += 4
        for line in response_typed:
            draw.text((interior_x0, y), line, font=font_r, fill=DIM_TEXT)
            y += LINE_HEIGHT
        if cursor_on:
            last = response_typed[-1] if response_typed else ""
            lx = interior_x0 + draw.textbbox((0, 0), last, font=font_r)[2]
            ly = y - LINE_HEIGHT
            cw = draw.textbbox((0, 0), "M", font=font_r)
            ch = cw[3] - cw[1]
            draw.rectangle([lx + 2, ly + 2, lx + 10, ly + ch + 2], fill=GOLD)

    # Brand caption under the window (replaces previous full-width footer)
    cap_y = WIN_Y + WIN_H + 20
    draw.ellipse([WIN_X, cap_y + 4, WIN_X + 6, cap_y + 10], fill=GOLD)
    draw.text((WIN_X + 14, cap_y), "C R O W E   L O G I C   M Y C O L O G Y",
              font=_font(11), fill=(150, 130, 80))

    return img


def _typing_progress(total_chars: int, cps: float, t: float) -> int:
    return min(total_chars, int(t * cps))


def main():
    if not RESPONSE_FILE.exists() or RESPONSE_FILE.stat().st_size < 50:
        print(f"ERROR: {RESPONSE_FILE} missing or empty — run the ollama prompt first")
        sys.exit(2)
    if not PROMPT_FILE.exists():
        print(f"ERROR: {PROMPT_FILE} missing")
        sys.exit(2)

    prompt_q = PROMPT_FILE.read_text().strip()
    # Strip the "Q: " prefix if present so what's shown is the actual question
    if prompt_q.startswith("Q: "):
        prompt_q = prompt_q[3:]
    response = RESPONSE_FILE.read_text().strip()

    # Wrap response to terminal width
    wrapped = _wrap(response, WRAP_COLS)
    # Cap to ~14 visible lines so cursor stays on screen (after header + prompt + dots)
    MAX_LINES = 18
    if len(wrapped) > MAX_LINES:
        wrapped = wrapped[:MAX_LINES - 1] + [wrapped[MAX_LINES - 1][:80] + " ..."]

    # The literal line that gets typed
    typed_line = f'ollama run Mcrowe1210/gemma-4-mycelium-e4b "{prompt_q}"'
    n_prompt = len(typed_line)

    n_response_chars = sum(len(l) + 1 for l in wrapped)  # +1 for line break pacing
    t_prompt = n_prompt / TYPE_CPS_USER
    t_response = n_response_chars / TYPE_CPS_MODEL
    total_t = INTRO_SECONDS + t_prompt + 0.4 + THINK_SECONDS + t_response + HOLD_SECONDS

    # Cap at 60 seconds (target ~Act 3 duration)
    if total_t > 60:
        # Trim response by reducing visible lines
        target = 60 - (INTRO_SECONDS + t_prompt + 0.4 + THINK_SECONDS + HOLD_SECONDS)
        target_chars = int(target * TYPE_CPS_MODEL)
        # Re-truncate
        new_lines = []
        running = 0
        for l in wrapped:
            if running + len(l) + 1 > target_chars:
                room = target_chars - running
                if room > 10:
                    new_lines.append(l[: room - 4] + " ...")
                break
            new_lines.append(l)
            running += len(l) + 1
        wrapped = new_lines
        n_response_chars = sum(len(l) + 1 for l in wrapped)
        t_response = n_response_chars / TYPE_CPS_MODEL
        total_t = INTRO_SECONDS + t_prompt + 0.4 + THINK_SECONDS + t_response + HOLD_SECONDS

    print(f"  prompt: {n_prompt} chars over {t_prompt:.2f}s")
    print(f"  response: {len(wrapped)} lines / {n_response_chars} chars over {t_response:.2f}s")
    print(f"  total: {total_t:.2f}s ({int(total_t * FPS)} frames)")

    if TMP.exists():
        shutil.rmtree(TMP)
    TMP.mkdir(parents=True)

    frame_idx = 0
    t = 0.0
    dt = 1.0 / FPS

    while t < total_t:
        # Determine phase
        if t < INTRO_SECONDS:
            shown_prompt = ""
            thinking = 0
            shown_response = []
            cursor = (int(t * 2) % 2 == 0)
            with_newline = False
        elif t < INTRO_SECONDS + t_prompt:
            local_t = t - INTRO_SECONDS
            n = _typing_progress(n_prompt, TYPE_CPS_USER, local_t)
            shown_prompt = typed_line[:n]
            thinking = 0
            shown_response = []
            cursor = True
            with_newline = False
        elif t < INTRO_SECONDS + t_prompt + 0.4:
            shown_prompt = typed_line
            thinking = 0
            shown_response = []
            cursor = (int(t * 3) % 2 == 0)
            with_newline = False
        elif t < INTRO_SECONDS + t_prompt + 0.4 + THINK_SECONDS:
            shown_prompt = typed_line
            local_t = t - (INTRO_SECONDS + t_prompt + 0.4)
            thinking = min(3, int(local_t * 3) + 1)
            shown_response = []
            cursor = False
            with_newline = True
        elif t < INTRO_SECONDS + t_prompt + 0.4 + THINK_SECONDS + t_response:
            shown_prompt = typed_line
            local_t = t - (INTRO_SECONDS + t_prompt + 0.4 + THINK_SECONDS)
            n = _typing_progress(n_response_chars, TYPE_CPS_MODEL, local_t)
            shown_response = []
            consumed = 0
            for line in wrapped:
                remaining = n - consumed
                if remaining <= 0:
                    break
                if remaining >= len(line):
                    shown_response.append(line)
                    consumed += len(line) + 1
                else:
                    shown_response.append(line[:remaining])
                    break
            thinking = 3
            cursor = (int(t * 2) % 2 == 0)
            with_newline = True
        else:
            shown_prompt = typed_line
            thinking = 3
            shown_response = wrapped
            cursor = (int(t * 2) % 2 == 0)
            with_newline = True

        img = _frame(shown_prompt, shown_response, thinking=thinking,
                     cursor_on=cursor, with_prompt_newline=with_newline)
        img.save(TMP / f"frame_{frame_idx:05d}.png")
        frame_idx += 1
        t += dt

    print(f"  rendered {frame_idx} frames → {TMP}")
    print("  encoding mp4...")
    OUT_MP4.parent.mkdir(parents=True, exist_ok=True)
    # Synthesise a typewriter-clack ambient audio track? skip — silent for now.
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-framerate", str(FPS),
        "-i", str(TMP / "frame_%05d.png"),
        "-f", "lavfi", "-t", f"{total_t:.3f}", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-pix_fmt", "yuv420p",
        "-c:v", "libx264", "-preset", "slow", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        str(OUT_MP4),
    ], check=True)

    shutil.rmtree(TMP)
    print(f"  ✓ {OUT_MP4} ({OUT_MP4.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
