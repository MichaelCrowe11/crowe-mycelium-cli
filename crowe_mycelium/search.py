"""Web search for grounding the mycology model's answers.

The model can't self-trigger tools on this Ollama stack (probe-confirmed 400 on
a tools request), so the CLI runs search itself. v1 ships a keyless DuckDuckGo
backend that hits the lite HTML endpoint directly (the `ddgs` library rotates to
a Yahoo backend that fails under Tailscale MagicDNS). A provider-agnostic
`Searcher` seam reserves Brave/Tavily for later.
"""

from __future__ import annotations

import html
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Optional

import httpx

DDG_LITE_URL = "https://lite.duckduckgo.com/lite/"

# VERIFIED structure (2026-06-02): single-quoted class, href before class.
_LINK_RE = re.compile(
    r"<a\s+[^>]*?href=\"([^\"]+)\"[^>]*?class='result-link'[^>]*?>(.*?)</a>", re.S
)
_SNIPPET_RE = re.compile(r"class='result-snippet'[^>]*>(.*?)</td>", re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str


def _clean(s: str) -> str:
    """Strip inner tags, decode entities, collapse whitespace."""
    return _WS_RE.sub(" ", html.unescape(_TAG_RE.sub("", s))).strip()


class Searcher(ABC):
    """Returns web results for a query. Backends are interchangeable behind this."""

    @abstractmethod
    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        raise NotImplementedError


class DuckDuckGoSearcher(Searcher):
    """Keyless DuckDuckGo via the lite HTML endpoint.

    `fetch` is an injectable seam (query -> raw HTML) so tests never hit the
    network; the default posts to the lite endpoint.
    """

    def __init__(self, fetch: Optional[Callable[[str], str]] = None):
        self._fetch = fetch or self._default_fetch

    def _default_fetch(self, query: str) -> str:
        r = httpx.post(
            DDG_LITE_URL,
            data={"q": query},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10.0,
        )
        r.raise_for_status()
        return r.text

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        try:
            html_text = self._fetch(query)
        except Exception:
            return []  # caller degrades to an ungrounded answer
        links = _LINK_RE.findall(html_text)
        snippets = [_clean(s) for s in _SNIPPET_RE.findall(html_text)]
        results: list[SearchResult] = []
        for i, (href, title) in enumerate(links[:max_results]):
            results.append(
                SearchResult(
                    title=_clean(title),
                    url=href,
                    snippet=snippets[i] if i < len(snippets) else "",
                )
            )
        return results
