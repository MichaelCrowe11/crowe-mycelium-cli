#!/usr/bin/env python3
"""Render branded title + outro cards for the hackathon film.

Brand: Crowe Logic Inc. corporate identity (parent) + Crowe Mycology
sub-brand (product). Palette is gold #bfa669 on ink. Marks pulled from
~/Desktop/crowe-logic-design-system/assets/. Outputs PNG at 1280x720, then
the assemble script wraps them in MP4 segments.
"""
from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "video" / "cards"
OUT_DIR.mkdir(parents=True, exist_ok=True)

BRAND_DIR = Path.home() / "Desktop" / "crowe-logic-design-system" / "assets"
CORP_MARK = BRAND_DIR / "04-corporate-mark-transparent.png"
AVATAR = BRAND_DIR / "06-assistant-avatar.png"

INK = (10, 10, 10)
GOLD = (191, 166, 105)
GOLD_DIM = (191, 166, 105, 110)

W, H = 1280, 720


def _font(size: int, mono: bool = False) -> ImageFont.FreeTypeFont:
    if mono:
        path = "/System/Library/Fonts/Menlo.ttc"
    else:
        path = "/System/Library/Fonts/HelveticaNeue.ttc"
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size)


def _center_text(draw, y, text, font, fill=GOLD):
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    draw.text(((W - w) / 2, y), text, font=font, fill=fill)


def _paste_mark(canvas, mark_path: Path, max_h: int, y_center: int):
    mark = Image.open(mark_path).convert("RGBA")
    # scale to max_h preserving aspect
    ratio = max_h / mark.height
    nw = int(mark.width * ratio)
    nh = max_h
    mark = mark.resize((nw, nh), Image.LANCZOS)
    x = int((W - nw) / 2)
    y = int(y_center - nh / 2)
    canvas.alpha_composite(mark, (x, y))


def _eyebrow_pill(draw, y, text):
    # Mono uppercase, tracking-ish via inserted spaces, gold hairline 30% alpha
    label = "  ".join(list(text.upper()))
    font = _font(16, mono=True)
    bbox = draw.textbbox((0, 0), label, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    pad_x, pad_y = 18, 8
    pw = tw + pad_x * 2
    ph = th + pad_y * 2
    x = int((W - pw) / 2)
    # Hairline border at 30% alpha — draw thin gold rectangle
    draw.rectangle([x, y, x + pw, y + ph], outline=GOLD_DIM[:3], width=1)
    # Gold dot on the left
    dot_r = 4
    dy = y + ph // 2
    dx = x + 10
    draw.ellipse([dx - dot_r, dy - dot_r, dx + dot_r, dy + dot_r], fill=GOLD)
    draw.text((x + pad_x + 16, y + pad_y - 2), label, font=font, fill=GOLD)
    return y + ph


def _paste_avatar_circular(canvas, avatar_path: Path, diameter: int, y_center: int):
    """Paste the avatar with a circular alpha mask so its baked-in cream
    background doesn't read as a square card-in-card."""
    avatar = Image.open(avatar_path).convert("RGB")
    side = min(avatar.size)
    left = (avatar.width - side) // 2
    top = (avatar.height - side) // 2
    avatar = avatar.crop((left, top, left + side, top + side)).resize(
        (diameter, diameter), Image.LANCZOS
    )
    mask = Image.new("L", (diameter, diameter), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, diameter, diameter), fill=255)
    avatar.putalpha(mask)
    x = int((W - diameter) / 2)
    y = int(y_center - diameter / 2)
    canvas.alpha_composite(avatar, (x, y))


def make_title_card() -> Path:
    img = Image.new("RGBA", (W, H), INK + (255,))
    draw = ImageDraw.Draw(img)
    if AVATAR.exists():
        _paste_avatar_circular(img, AVATAR, diameter=200, y_center=230)
    _eyebrow_pill(draw, 360, "presents")
    _center_text(draw, 430, "Gemma 4 Mycelium", _font(64))
    _center_text(draw, 520, "an offline cultivation intelligence", _font(22), fill=(180, 180, 180))
    _center_text(draw, 560, "built on Gemma 4 by Crowe Logic", _font(22), fill=(180, 180, 180))
    out = OUT_DIR / "title_card.png"
    img.convert("RGB").save(out)
    return out


def make_outro_card() -> Path:
    img = Image.new("RGBA", (W, H), INK + (255,))
    draw = ImageDraw.Draw(img)
    _center_text(draw, 90, "Gemma 4 Mycelium", _font(44))
    _center_text(draw, 150, "domain-adapted Gemma 4 for commercial cultivation",
                 _font(18), fill=(170, 170, 170))

    # Two-column URL block: artifacts left, sites right
    url_font = _font(17, mono=True)
    section_font = _font(13)

    # Section headers (small mono uppercase)
    _center_text(draw, 220, "M O D E L   ·   C O D E   ·   A D A P T E R",
                 section_font, fill=(150, 130, 80))
    _center_text(draw, 252, "ollama.com/Mcrowe1210/gemma-4-mycelium-e4b", url_font, fill=GOLD)
    _center_text(draw, 280, "github.com/MichaelCrowe11/crowe-mycelium-cli", url_font, fill=GOLD)
    _center_text(draw, 308, "huggingface.co/crowelogic/gemma-4-mycelium-e4b-lora", url_font, fill=GOLD)

    _center_text(draw, 370, "C R O W E   L O G I C",
                 section_font, fill=(150, 130, 80))
    _center_text(draw, 402, "crowelogic.com", url_font, fill=GOLD)
    _center_text(draw, 430, "mycology.crowelogic.com", url_font, fill=GOLD)

    # Hackathon attribution
    _center_text(draw, 500, "submitted to the Gemma 4 Good Hackathon",
                 _font(16), fill=(140, 140, 140))
    _center_text(draw, 525, "built on Gemma by Google DeepMind",
                 _font(16), fill=(140, 140, 140))

    if CORP_MARK.exists():
        _paste_mark(img, CORP_MARK, max_h=60, y_center=640)
    out = OUT_DIR / "outro_card.png"
    img.convert("RGB").save(out)
    return out


def make_act3_card() -> Path:
    """Replacement for the generic Act 3 placeholder with brand styling."""
    img = Image.new("RGBA", (W, H), INK + (255,))
    draw = ImageDraw.Draw(img)
    _eyebrow_pill(draw, 280, "act 3")
    _center_text(draw, 340, "Live Demo", _font(56))
    mono = _font(20, mono=True)
    _center_text(draw, 430, "$ ollama run Mcrowe1210/gemma-4-mycelium-e4b", mono, fill=GOLD)
    _center_text(draw, 470, "(record terminal — cultivation prompt, airplane mode)", _font(18), fill=(140, 140, 140))
    out = OUT_DIR / "act3_card.png"
    img.convert("RGB").save(out)
    return out


def make_corner_watermark() -> Path:
    """Small Crowe Logic corner mark for overlay on talking-head shots."""
    if not CORP_MARK.exists():
        return None
    mark = Image.open(CORP_MARK).convert("RGBA")
    ratio = 60 / mark.height
    mark = mark.resize((int(mark.width * ratio), 60), Image.LANCZOS)
    # Add 50% opacity
    alpha = mark.split()[-1].point(lambda p: int(p * 0.55))
    mark.putalpha(alpha)
    out = OUT_DIR / "corner_watermark.png"
    mark.save(out)
    return out


if __name__ == "__main__":
    t = make_title_card()
    o = make_outro_card()
    a = make_act3_card()
    w = make_corner_watermark()
    print(f"wrote {t}")
    print(f"wrote {o}")
    print(f"wrote {a}")
    print(f"wrote {w}")
