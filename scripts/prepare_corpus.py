#!/usr/bin/env python3
"""Build the Gemma 4 Mycelium training corpus.

Sources:
- Lion's Mane Commercial SOP (markdown manuscript)
- The Mushroom Grower Vol 1 & Vol 2 (XeLaTeX sources)
- Mycelium EI Engine (technical READMEs + Python module docstrings)

Output:
- ``data/corpus.jsonl`` with one record per chunk:
  ``{"text": "<chapter or section>", "source": "<filename>", "section": "<chapter title>"}``
- ``data/instruct.jsonl`` with instruction-response pairs derived from
  section structure (chapter title becomes the instruction, body becomes
  the response). Suitable for LoRA SFT.

This script is intentionally dependency-free (stdlib only) so it can run
on Kaggle without a pre-install step.

Usage:
    python scripts/prepare_corpus.py              # writes to ./data/
    python scripts/prepare_corpus.py --out /path  # custom output dir
    python scripts/prepare_corpus.py --max 8192   # cap chunk size (chars)
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterator


REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECTS = Path.home() / "Projects"

# Source paths — each entry is a (label, path) tuple. Missing paths are
# logged but do not abort the run; this script must be robust against
# future repo moves.
SOURCES: list[tuple[str, Path]] = [
    ("lions-mane-sop",       PROJECTS / "southwest-mushrooms" / "lions-mane-sop" / "draft" / "manuscript.md"),
    ("mushroom-grower-vol1", Path.home() / "mushroom-book-production" / "vol1" / "latex" / "body.tex"),
    ("mushroom-grower-vol2", Path.home() / "mushroom-book-production" / "vol2" / "latex" / "body.tex"),
    ("mycelium-ei-readme",   PROJECTS / "crios-nova" / "mycelium-ei-lang" / "README.md"),
    ("mycelium-ei-roadmap",  PROJECTS / "crios-nova" / "mycelium-ei-lang" / "DEVELOPMENT_ROADMAP.md"),
    ("mycelium-ei-opt",      PROJECTS / "crios-nova" / "mycelium-ei-lang" / "OPTIMIZATION_AND_ROADMAP.md"),
]

# Cultivation-specific keyword filter for the python module corpus — we
# pull *docstrings* from these files (skip the implementation body) since
# the goal is biological/cultivation knowledge, not algorithm internals.
MYCELIUM_PY_DOC_SOURCES = [
    PROJECTS / "crios-nova" / "mycelium-ei-lang" / "cultivation_monitor.py",
    PROJECTS / "crios-nova" / "mycelium-ei-lang" / "bio_algorithms.py",
    PROJECTS / "crios-nova" / "mycelium-ei-lang" / "bio_ml_integration.py",
]


# ── LaTeX cleaning ────────────────────────────────────────────────────────
# These regexes strip XeLaTeX markup to leave the underlying prose. They
# are deliberately conservative — when in doubt, keep the text.

_RX_LATEX_COMMAND_WITH_ARG = re.compile(r"\\(?:label|hypertarget|index|protect|phantomsection|hyperref|addcontentsline|input|include|usepackage|documentclass)\{[^}]*\}")
_RX_LATEX_CMD_TWO_ARGS = re.compile(r"\\(?:href|hyperref)\{[^}]*\}\{([^}]*)\}")
_RX_CHAPTER = re.compile(r"\\chapter\*?\{([^}]*)\}")
_RX_SECTION = re.compile(r"\\(?:section|subsection|subsubsection|paragraph)\*?\{([^}]*)\}")
_RX_TEXT_FORMAT = re.compile(r"\\(?:textit|textbf|emph|texttt|textsc|underline)\{([^}]*)\}")
_RX_QUOTE_TS = re.compile(r"\\textquotesingle\s*")
_RX_QUOTE_DB = re.compile(r"\\textquotedbl\s*")
_RX_BS_ESCAPE = re.compile(r"\\(?P<c>[%&_#$])")
_RX_LATEX_LEFTOVER_CMD = re.compile(r"\\[A-Za-z@]+\*?(?:\[[^\]]*\])?(?:\{[^}]*\})?")
_RX_BRACES = re.compile(r"[{}]")
_RX_WHITESPACE = re.compile(r"[ \t]+")
_RX_NEWLINES = re.compile(r"\n{3,}")


def clean_latex(text: str) -> str:
    """Strip LaTeX markup to plain prose. Preserves paragraph structure."""
    text = _RX_LATEX_COMMAND_WITH_ARG.sub("", text)
    text = _RX_LATEX_CMD_TWO_ARGS.sub(r"\1", text)  # \href{url}{label} → label
    text = _RX_CHAPTER.sub(r"\n\n# \1\n\n", text)
    text = _RX_SECTION.sub(r"\n\n## \1\n\n", text)
    text = _RX_TEXT_FORMAT.sub(r"\1", text)
    text = _RX_QUOTE_TS.sub("'", text)
    text = _RX_QUOTE_DB.sub('"', text)
    text = _RX_BS_ESCAPE.sub(r"\g<c>", text)
    text = _RX_LATEX_LEFTOVER_CMD.sub("", text)
    text = _RX_BRACES.sub("", text)
    text = _RX_WHITESPACE.sub(" ", text)
    text = _RX_NEWLINES.sub("\n\n", text)
    return text.strip()


# ── Chunking ──────────────────────────────────────────────────────────────


_RX_HEADING = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)


def split_by_heading(text: str, source: str) -> Iterator[dict]:
    """Split a markdown-ish document into chunks keyed on headings.

    Each chunk gets a stable ``section`` label (the most recent heading).
    Documents with no headings yield a single chunk.
    """
    matches = list(_RX_HEADING.finditer(text))
    if not matches:
        yield {"source": source, "section": "(root)", "text": text.strip()}
        return

    # Body before the first heading, if any.
    first = matches[0]
    pre = text[:first.start()].strip()
    if pre:
        yield {"source": source, "section": "(preamble)", "text": pre}

    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section_title = m.group(2).strip()
        body = text[m.end():end].strip()
        if body:
            yield {"source": source, "section": section_title, "text": body}


def cap_chunks(records: Iterator[dict], max_chars: int) -> Iterator[dict]:
    """Split any record whose text exceeds ``max_chars`` on paragraph breaks."""
    for rec in records:
        text = rec["text"]
        if len(text) <= max_chars:
            yield rec
            continue
        # Greedy paragraph-bounded split.
        paragraphs = text.split("\n\n")
        cur: list[str] = []
        cur_len = 0
        part = 1
        for para in paragraphs:
            plen = len(para) + 2
            if cur and cur_len + plen > max_chars:
                yield {
                    **rec,
                    "section": f"{rec['section']} (part {part})",
                    "text": "\n\n".join(cur),
                }
                part += 1
                cur = [para]
                cur_len = plen
            else:
                cur.append(para)
                cur_len += plen
        if cur:
            yield {
                **rec,
                "section": f"{rec['section']} (part {part})" if part > 1 else rec["section"],
                "text": "\n\n".join(cur),
            }


# ── Source readers ────────────────────────────────────────────────────────


def read_source(path: Path) -> str | None:
    if not path.exists():
        print(f"  WARN: source missing: {path}")
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".tex":
        text = clean_latex(text)
    return text


def extract_py_docstrings(path: Path) -> str:
    """Pull module-level + function/class docstrings from a Python file.

    Falls back to the leading docstring block if AST parsing fails — better
    a degraded extraction than zero coverage.
    """
    import ast
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    parts: list[str] = []
    mod_doc = ast.get_docstring(tree)
    if mod_doc:
        parts.append(f"# {path.stem}\n\n{mod_doc}")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node)
            if doc:
                parts.append(f"## {node.name}\n\n{doc}")
    return "\n\n".join(parts)


# ── Instruction-pair derivation ───────────────────────────────────────────


_INSTRUCTION_TEMPLATES = [
    "Explain: {section}",
    "What does '{section}' cover in mushroom cultivation?",
    "Walk me through {section}.",
    "Tell me about {section}.",
    "From a commercial cultivation perspective: {section}",
]


def to_instruction_pair(chunk: dict, template_idx: int = 0) -> dict:
    section = chunk["section"]
    if section in ("(root)", "(preamble)") or section.startswith("(part"):
        instruction = "Share what you know about commercial mushroom cultivation."
    else:
        template = _INSTRUCTION_TEMPLATES[template_idx % len(_INSTRUCTION_TEMPLATES)]
        instruction = template.format(section=section)
    return {
        "instruction": instruction,
        "input": "",
        "output": chunk["text"],
        "source": chunk["source"],
    }


# ── Main ──────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "data")
    parser.add_argument("--max", type=int, default=8192,
                        help="Max characters per chunk (default 8192).")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    corpus_path = args.out / "corpus.jsonl"
    instruct_path = args.out / "instruct.jsonl"

    chunks: list[dict] = []

    # Markdown / LaTeX sources
    for label, path in SOURCES:
        text = read_source(path)
        if text is None:
            continue
        for chunk in cap_chunks(split_by_heading(text, label), args.max):
            chunks.append(chunk)

    # Python docstring sources (cultivation modules only)
    for path in MYCELIUM_PY_DOC_SOURCES:
        if not path.exists():
            print(f"  WARN: source missing: {path}")
            continue
        ds = extract_py_docstrings(path)
        if not ds:
            continue
        for chunk in cap_chunks(split_by_heading(ds, f"mycelium-ei-{path.stem}"), args.max):
            chunks.append(chunk)

    # Write corpus (raw chunks)
    with corpus_path.open("w") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    # Write instruction-tuned pairs
    pairs = [to_instruction_pair(c, i) for i, c in enumerate(chunks)]
    with instruct_path.open("w") as f:
        for p in pairs:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    # Summary
    total_chars = sum(len(c["text"]) for c in chunks)
    by_source: dict[str, int] = {}
    for c in chunks:
        by_source[c["source"]] = by_source.get(c["source"], 0) + len(c["text"])
    print(f"Wrote {len(chunks)} chunks ({total_chars:,} chars total) to:")
    print(f"  {corpus_path}")
    print(f"  {instruct_path}")
    print()
    print("By source:")
    for source, chars in sorted(by_source.items(), key=lambda kv: -kv[1]):
        print(f"  {source:30s} {chars:>10,} chars")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
