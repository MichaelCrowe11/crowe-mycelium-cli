"""Tests for the v8 script-to-clip matcher."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from textwrap import dedent

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[2] / "scripts" / "video" / "v8"
sys.path.insert(0, str(SCRIPT_DIR))
spec = importlib.util.spec_from_file_location("match_module", SCRIPT_DIR / "03_match.py")
match = importlib.util.module_from_spec(spec)
sys.modules["match_module"] = match  # required for dataclass module lookup on 3.12+
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
