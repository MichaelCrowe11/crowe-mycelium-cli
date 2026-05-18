#!/usr/bin/env python3
"""Render a cinematic mobile use-case animation for film_v10.

The UI does not show a fabricated live transcript. It shows a controlled
use-case capture: the grower question, the offline local-model state, and the
conservative triage behavior the shipped Modelfile is designed to enforce.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "video" / "v10" / "usecase_ui"
FRAMES = OUT / "frames"
OUT.mkdir(parents=True, exist_ok=True)
FRAMES.mkdir(exist_ok=True)

W, H = 1280, 720
FPS = 30

BG = (11, 15, 19)
INK = (236, 238, 235)
MUTED = (151, 159, 151)
LINE = (54, 63, 58)
MOSS = (93, 142, 92)
MOSS_DARK = (30, 70, 48)
GOLD = (218, 178, 96)
RUST = (179, 96, 64)
CARD = (22, 30, 27)
PHONE = (17, 22, 20)
PHONE_SCREEN = (238, 240, 232)
PHONE_TEXT = (24, 29, 24)


FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/SFNS.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]
MONO_CANDIDATES = [
    "/System/Library/Fonts/Menlo.ttc",
    "/System/Library/Fonts/Monaco.ttf",
]


def font(size: int, mono: bool = False) -> ImageFont.FreeTypeFont:
    candidates = MONO_CANDIDATES if mono else FONT_CANDIDATES
    for item in candidates:
        if os.path.exists(item):
            try:
                return ImageFont.truetype(item, size)
            except OSError:
                continue
    return ImageFont.load_default()


F12 = font(12)
F14 = font(14)
F16 = font(16)
F18 = font(18)
F20 = font(20)
F24 = font(24)
F30 = font(30)
F36 = font(36)
F44 = font(44)
M16 = font(16, mono=True)
M18 = font(18, mono=True)


def rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], radius: int, fill, outline=None, width=1) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def wrap(draw: ImageDraw.ImageDraw, text: str, font_obj, max_w: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for word in words:
        test = word if not cur else f"{cur} {word}"
        if draw.textbbox((0, 0), test, font=font_obj)[2] <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def text_block(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, font_obj, fill, max_w: int, line_h: int) -> int:
    x, y = xy
    for line in wrap(draw, text, font_obj, max_w):
        draw.text((x, y), line, font=font_obj, fill=fill)
        y += line_h
    return y


def base_frame() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    for i in range(0, W, 80):
        color = (13 + i % 20, 19, 17)
        draw.line((i, 0, i - 360, H), fill=color, width=1)
    draw.rectangle((0, 0, W, H), outline=(28, 36, 30), width=2)
    return img, draw


def draw_side_panel(draw: ImageDraw.ImageDraw, phase: int) -> None:
    draw.text((70, 72), "Gemma 4 Mycelium", font=F44, fill=INK)
    draw.text((72, 126), "Offline grow-room triage", font=F24, fill=GOLD)
    y = 186
    cards = [
        ("Use case", "Pink wet spots on a lion's mane block before clean-room work."),
        ("Constraint", "No reliable connection. Private cultivation notes stay local."),
        ("Model behavior", "Ask context first. Refuse single-clue contamination guesses."),
        ("Next action", "Isolate, photograph, mark spread, check odor and texture, then decide."),
    ]
    for idx, (title, body) in enumerate(cards):
        active = phase >= idx
        fill = CARD if active else (17, 22, 20)
        outline = MOSS if active else LINE
        rounded(draw, (70, y, 580, y + 92), 8, fill, outline=outline, width=2 if active else 1)
        draw.text((92, y + 14), title.upper(), font=F14, fill=GOLD if active else MUTED)
        text_block(draw, (92, y + 38), body, F18, INK if active else MUTED, 450, 24)
        y += 108
    draw.text((74, 650), "Runs locally via Ollama. Built on Gemma.", font=F18, fill=MUTED)


def draw_phone(draw: ImageDraw.ImageDraw, progress: float) -> None:
    px, py, pw, ph = 704, 38, 364, 644
    rounded(draw, (px, py, px + pw, py + ph), 36, PHONE, outline=(74, 83, 74), width=3)
    rounded(draw, (px + 18, py + 18, px + pw - 18, py + ph - 18), 26, PHONE_SCREEN)
    draw.rounded_rectangle((px + 152, py + 30, px + 212, py + 38), radius=4, fill=(42, 48, 42))

    sx, sy = px + 34, py + 58
    draw.text((sx, sy), "Mycelium", font=F30, fill=PHONE_TEXT)
    draw.text((sx, sy + 34), "Offline mode", font=F16, fill=MOSS_DARK)
    rounded(draw, (px + pw - 124, sy + 2, px + pw - 44, sy + 30), 14, (210, 234, 205), outline=(132, 179, 120))
    draw.text((px + pw - 104, sy + 8), "LOCAL", font=F12, fill=MOSS_DARK)

    y = sy + 78
    rounded(draw, (sx, y, sx + 296, y + 92), 12, (255, 255, 250), outline=(210, 215, 204))
    draw.text((sx + 16, y + 14), "Grower note", font=F16, fill=MUTED)
    text_block(
        draw,
        (sx + 16, y + 38),
        "Pink wet spots on lion's mane block. Edge of room, humid morning.",
        F18,
        PHONE_TEXT,
        264,
        22,
    )

    y += 112
    if progress > 0.18:
        rounded(draw, (sx, y, sx + 296, y + 82), 12, (233, 243, 230), outline=(158, 191, 146))
        draw.text((sx + 16, y + 14), "Model asks", font=F16, fill=MOSS_DARK)
        text_block(draw, (sx + 16, y + 38), "Species, source, odor, texture, timeline, photo.", F18, PHONE_TEXT, 264, 22)

    y += 102
    if progress > 0.38:
        rounded(draw, (sx, y, sx + 296, y + 138), 12, (255, 250, 234), outline=(225, 191, 113))
        draw.text((sx + 16, y + 14), "Triage", font=F16, fill=RUST)
        steps = ["1. Isolate suspect block", "2. Photograph and mark spread", "3. Do not open near clean bench", "4. Transfer only from clean growth"]
        ty = y + 40
        for step in steps:
            draw.text((sx + 16, ty), step, font=F16, fill=PHONE_TEXT)
            ty += 23

    y += 158
    if progress > 0.68:
        rounded(draw, (sx, y, sx + 296, y + 70), 12, (28, 41, 34), outline=(84, 130, 86))
        draw.text((sx + 16, y + 14), "Crowe Mycelium CLI", font=F16, fill=GOLD)
        draw.text((sx + 16, y + 40), "Mcrowe1210/gemma-4-mycelium-e4b", font=F12, fill=(222, 231, 219))


def draw_terminal(draw: ImageDraw.ImageDraw, tick: int) -> None:
    x, y, w, h = 655, 485, 520, 168
    rounded(draw, (x, y, x + w, y + h), 10, (9, 12, 15), outline=(70, 86, 76))
    draw.text((x + 18, y + 14), "michael@crowe % crowe-mycelium info", font=M16, fill=(205, 220, 206))
    lines = [
        "model   gemma-4-mycelium-e4b",
        "base    google/gemma-4-e4b",
        "tag     Mcrowe1210/gemma-4-mycelium-e4b",
        "mode    local / offline",
    ]
    ty = y + 48
    count = min(len(lines), max(0, tick // 24))
    for line in lines[:count]:
        draw.text((x + 18, ty), line, font=M16, fill=(169, 210, 170))
        ty += 24


def frame_at(t: float) -> Image.Image:
    img, draw = base_frame()
    progress = min(1.0, t / 58.0)
    phase = 0
    if t > 12:
        phase = 1
    if t > 24:
        phase = 2
    if t > 38:
        phase = 3
    draw_side_panel(draw, phase)
    draw_phone(draw, progress)
    if t > 44:
        draw_terminal(draw, int((t - 44) * FPS))
    return img


def main() -> int:
    duration = 62.0
    total_frames = int(duration * FPS)
    for i in range(total_frames):
        img = frame_at(i / FPS)
        img.save(FRAMES / f"frame_{i:06d}.png", quality=95)
        if i % 300 == 0:
            print(f"frame {i}/{total_frames}")
    out = ROOT / "video" / "v10" / "usecase_ui.mp4"
    subprocess.check_call(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-framerate",
            str(FPS),
            "-i",
            str(FRAMES / "frame_%06d.png"),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(out),
        ]
    )
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
