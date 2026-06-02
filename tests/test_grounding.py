from crowe_mycelium.grounding import needs_live_info, format_grounding, sources_text
from crowe_mycelium.search import SearchResult

RESULTS = [
    SearchResult("Oyster prices 2026", "https://a.example/p", "Around $6-12/lb."),
    SearchResult("Market report", "https://b.example/m", "Wholesale trends."),
]


def test_needs_live_info_true_for_live_signals():
    assert needs_live_info("what is the current price of oyster mushrooms")
    assert needs_live_info("latest news on mushroom market")
    assert needs_live_info("oyster prices in 2026")


def test_needs_live_info_false_for_knowledge_questions():
    assert not needs_live_info("how do I fruit lion's mane")
    assert not needs_live_info("what substrate for oysters")


def test_needs_live_info_true_for_research_and_domains():
    assert needs_live_info("can you research crowelm.com")
    assert needs_live_info("look up southwest mushrooms")
    assert needs_live_info("find out about https://example.org")


def test_format_grounding_includes_query_results_and_cite_instruction():
    g = format_grounding("oyster price?", RESULTS)
    assert "oyster price?" in g
    assert "[1]" in g and "[2]" in g
    assert "https://a.example/p" in g
    assert "cite" in g.lower()


def test_sources_text_lists_each_url_numbered():
    s = sources_text(RESULTS)
    assert "Sources:" in s
    assert "[1] https://a.example/p" in s
    assert "[2] https://b.example/m" in s
