#!/usr/bin/env python3
"""Match script lines from scripts.json to transcript entries.

Outputs cut_list.json with one (video, in, out) tuple per script line.
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
        body_lines = [
            line for line in lines
            if not SRT_TIMESTAMP_RE.search(line) and not line.strip().isdigit()
        ]
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
        act_out = {"act": act["act"], "line_matches": []}
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
