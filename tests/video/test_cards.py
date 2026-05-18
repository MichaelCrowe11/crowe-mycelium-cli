"""Tests for v8 card rendering."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parents[2] / "scripts" / "video" / "v8"
sys.path.insert(0, str(SCRIPT_DIR))
spec = importlib.util.spec_from_file_location("cards", SCRIPT_DIR / "05_cards.py")
cards = importlib.util.module_from_spec(spec)
sys.modules["cards"] = cards
spec.loader.exec_module(cards)


LOGO_PATH = Path.home() / "Projects/crowelogic-website/public/crowe-logic-mark-512.png"


def test_title_card_dimensions(tmp_path):
    out = tmp_path / "title.png"
    cards.render_title(LOGO_PATH, out)
    img = Image.open(out)
    assert img.size == (1920, 1080)
    assert img.mode in ("RGB", "RGBA")


def test_end_card_non_trivial(tmp_path):
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
    assert img.mode == "RGBA"
