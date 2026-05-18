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


def _prep_logo(logo_path: Path, target_height: int) -> tuple[int, Image.Image]:
    """Return (x, resized_logo_image) for horizontal centering."""
    logo = Image.open(logo_path).convert("RGBA")
    ratio = target_height / logo.height
    new_w = int(logo.width * ratio)
    logo = logo.resize((new_w, target_height), Image.LANCZOS)
    x = (W - new_w) // 2
    return x, logo


def render_title(logo_path: Path, out: Path) -> None:
    canvas = Image.new("RGB", (W, H), BG)
    target_h = int(H * 0.30)
    x_logo, logo = _prep_logo(logo_path, target_h)
    y_logo = int(H * 0.18)
    canvas.paste(logo, (x_logo, y_logo), logo)

    draw = ImageDraw.Draw(canvas)
    _draw_centered(draw, "CROWE LOGIC PRESENTS",
                   y_logo + target_h + 60, _load_font(36), ACCENT)
    _draw_centered(draw, "Gemma 4 Mycelium",
                   y_logo + target_h + 120, _load_font(96), FG)
    _draw_centered(draw, "Offline AI for Commercial Mushroom Cultivation",
                   y_logo + target_h + 240, _load_font(40), FG)
    _draw_centered(draw, "Submission  .  Gemma 4 Good Hackathon  .  Special Tech Track",
                   y_logo + target_h + 320, _load_font(28), ACCENT)
    canvas.save(out)


def render_end(logo_path: Path, out: Path) -> None:
    canvas = Image.new("RGB", (W, H), BG)
    target_h = int(H * 0.25)
    x_logo, logo = _prep_logo(logo_path, target_h)
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
    _draw_centered(draw, "Built on Gemma  .  Released under Gemma Terms of Use",
                   y, _load_font(26), ACCENT)
    canvas.save(out)


def render_lower_third(logo_path: Path, out: Path) -> None:
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))

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
    draw.text((x + target_h + 16, y + 28), "Crowe Logic  .  Southwest Mushrooms",
              font=_load_font(20), fill=ACCENT)
    canvas.save(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    default_logo = str(Path.home() /
                       "Projects/crowelogic-website/public/crowe-logic-mark-512.png")
    ap.add_argument("--logo", default=default_logo)
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
