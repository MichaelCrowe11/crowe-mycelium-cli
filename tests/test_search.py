from crowe_mycelium.search import DuckDuckGoSearcher, SearchResult

# Minimal fixture matching the VERIFIED DDG-lite structure:
# <a ... href="URL" class='result-link'>TITLE</a> (single-quoted class, href first)
# <td ... class='result-snippet'>SNIPPET</td>
FIXTURE = """
<html><body>
<a rel="nofollow" href="https://a.example/1" class='result-link'>Alpha Title</a>
<td class='result-snippet'>Alpha snippet text.</td>
<a rel="nofollow" href="https://b.example/2" class='result-link'>Beta &amp; Title</a>
<td class='result-snippet'>Beta snippet <b>bold</b> text.</td>
</body></html>
"""


def test_parses_results_from_fixture():
    s = DuckDuckGoSearcher(fetch=lambda q: FIXTURE)
    out = s.search("anything", max_results=5)
    assert len(out) == 2
    assert out[0] == SearchResult(
        title="Alpha Title", url="https://a.example/1", snippet="Alpha snippet text."
    )
    # HTML entities decoded, inner tags stripped/collapsed
    assert out[1].title == "Beta & Title"
    assert out[1].snippet == "Beta snippet bold text."


def test_max_results_caps_output():
    s = DuckDuckGoSearcher(fetch=lambda q: FIXTURE)
    assert len(s.search("x", max_results=1)) == 1


def test_empty_or_garbage_html_returns_empty():
    s = DuckDuckGoSearcher(fetch=lambda q: "<html></html>")
    assert s.search("x") == []


def test_fetch_error_returns_empty():
    def boom(q):
        raise RuntimeError("network down")

    s = DuckDuckGoSearcher(fetch=boom)
    assert s.search("x") == []
