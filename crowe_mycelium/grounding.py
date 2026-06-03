"""Turn web results into a grounded prompt turn + a Sources footer.

The CLI appends `format_grounding(...)` to the user message so the model answers
over the fetched results and cites them as [n]; `sources_text(...)` is printed
(dim) after the answer so the links are always visible.
"""

from __future__ import annotations

import re

from crowe_mycelium.search import SearchResult

# Conservative live-info signals — used only to OFFER a search, never to search
# silently. Plus any 4-digit year >= 2025, and any URL / bare domain.
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
    "research",
    "look up",
    "lookup",
    "find out",
    "search for",
    "website",
    "recent",
)
_YEAR_RE = re.compile(r"\b(20[2-9]\d)\b")
_URL_RE = re.compile(r"https?://|www\.|\b[\w-]+\.(?:com|org|net|io|ai|co|gov|edu)\b")


def needs_live_info(text: str) -> bool:
    t = text.lower()
    if any(term in t for term in _LIVE_TERMS):
        return True
    if _URL_RE.search(t):
        return True
    m = _YEAR_RE.search(t)
    return bool(m and int(m.group(1)) >= 2025)


# Leading politeness to strip before matching a search command.
_POLITE_PREFIXES = ("can you ", "could you ", "would you ", "please ", "pls ", "hey ")

# Explicit "search the web for X" phrasings, longest-first so the most specific
# prefix wins (e.g. "search the web for " before "search ").
_SEARCH_PREFIXES = (
    "search the web for ",
    "search the web ",
    "search web for ",
    "search web ",
    "search online for ",
    "search online ",
    "search the internet for ",
    "search the internet ",
    "browse the web for ",
    "browse the web ",
    "browse for ",
    "look online for ",
    "find online ",
    "search for ",
    "look up ",
    "google ",
    "browse ",
)


def extract_search_query(text: str) -> str | None:
    """Return the query X if the message is an explicit 'search the web for X'
    style command, else None.

    Lets natural-language search intent ("search web for new strains", "look up
    oyster prices") run a real search DIRECTLY instead of only being offered or,
    worse, slipping past the heuristic and getting an unhelpful "I can't browse"
    reply. The CLI checks this before the softer needs_live_info() offer.
    """
    t = text.strip()
    low = t.lower()
    for pre in _POLITE_PREFIXES:
        if low.startswith(pre):
            t = t[len(pre) :].strip()
            low = t.lower()
            break
    for pre in _SEARCH_PREFIXES:
        if low.startswith(pre):
            query = t[len(pre) :].strip()
            # A lone trailing preposition (e.g. "search the web for") is not a
            # usable query — treat it as no search.
            if query.lower() in ("", "for", "about", "on", "online", "web", "the web"):
                return None
            return query
    return None


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
