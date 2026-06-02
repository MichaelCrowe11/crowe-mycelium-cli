"""Turn web results into a grounded prompt turn + a Sources footer.

The CLI appends `format_grounding(...)` to the user message so the model answers
over the fetched results and cites them as [n]; `sources_text(...)` is printed
(dim) after the answer so the links are always visible.
"""

from __future__ import annotations

import re

from crowe_mycelium.search import SearchResult

# Conservative live-info signals — used only to OFFER a search, never to search
# silently. Plus any 4-digit year >= 2025.
_LIVE_TERMS = (
    "current",
    "latest",
    "today",
    "this week",
    "right now",
    "as of",
    "price",
    "cost",
    "news",
    "weather",
    "in stock",
    "available now",
)
_YEAR_RE = re.compile(r"\b(20[2-9]\d)\b")


def needs_live_info(text: str) -> bool:
    t = text.lower()
    if any(term in t for term in _LIVE_TERMS):
        return True
    m = _YEAR_RE.search(t)
    return bool(m and int(m.group(1)) >= 2025)


def format_grounding(query: str, results: list[SearchResult]) -> str:
    lines = [f"[{i}] {r.title} — {r.snippet} ({r.url})" for i, r in enumerate(results, 1)]
    body = "\n".join(lines)
    return (
        f"{query}\n\n"
        f"Use ONLY these web search results to answer, and cite sources inline as [n]. "
        f"If they don't answer the question, say so plainly.\n\n"
        f"{body}"
    )


def sources_text(results: list[SearchResult]) -> str:
    lines = [f"[{i}] {r.url}" for i, r in enumerate(results, 1)]
    return "Sources:\n" + "\n".join(lines)
