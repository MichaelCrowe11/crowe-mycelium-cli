from crowe_mycelium import deep
from crowe_mycelium.config import Settings
from crowe_mycelium.search import SearchResult


class _StreamBackend:
    def __init__(self, chunks):
        self._chunks = chunks

    def stream_chat(self, messages, temperature=0.4):
        yield from self._chunks


def test_collect_sample_joins_stream():
    assert deep.collect_sample(_StreamBackend(["a", "b", "c"]), [], 0.8) == "abc"


def test_build_judge_messages_includes_candidates_query_and_instruction():
    msgs = deep.build_judge_messages("SYS", "why no pinning?", ["ans one", "ans two"])
    assert msgs[0] == {"role": "system", "content": "SYS"}
    user = msgs[1]["content"]
    assert "why no pinning?" in user
    assert "ans one" in user and "ans two" in user
    assert "reconcile" in user.lower()
    assert "agreement:" in user.lower()


def test_deep_samples_default_and_env(monkeypatch):
    monkeypatch.delenv("CROWE_MYCELIUM_DEEP_SAMPLES", raising=False)
    assert deep.deep_samples() == 3
    monkeypatch.setenv("CROWE_MYCELIUM_DEEP_SAMPLES", "5")
    assert deep.deep_samples() == 5
    monkeypatch.setenv("CROWE_MYCELIUM_DEEP_SAMPLES", "1")  # floored at 2
    assert deep.deep_samples() == 2


def test_deep_temperature_default_and_env(monkeypatch):
    monkeypatch.delenv("CROWE_MYCELIUM_DEEP_TEMPERATURE", raising=False)
    assert deep.deep_temperature() == 0.8
    monkeypatch.setenv("CROWE_MYCELIUM_DEEP_TEMPERATURE", "0.5")
    assert deep.deep_temperature() == 0.5


class _DeepBackend:
    """First N stream_chat calls return the samples; the next returns the judge."""

    def __init__(self, samples, judge):
        self._samples = list(samples)
        self._judge = judge
        self.calls = 0

    def stream_chat(self, messages, temperature=0.4):
        self.calls += 1
        if self.calls <= len(self._samples):
            yield self._samples[self.calls - 1]
        else:
            yield self._judge


class _RecRenderer:
    def __init__(self):
        self.labels = []
        self.streamed = []
        self.errors = []
        self.notices = []

    def deliberate(self, label, fn):
        self.labels.append(label)
        return fn()

    def render_stream(self, chunks):
        text = "".join(chunks)
        self.streamed.append(text)
        return text

    def error(self, msg):
        self.errors.append(msg)

    def notice(self, msg):
        self.notices.append(msg)


def _bm(history, system, user):
    return [{"role": "user", "content": user}]


def test_run_deep_samples_then_judges(monkeypatch):
    monkeypatch.setenv("CROWE_MYCELIUM_DEEP_SAMPLES", "3")
    be = _DeepBackend(samples=["s1", "s2", "s3"], judge="reconciled")
    r = _RecRenderer()
    history = []
    deep.run_deep("how do I diagnose green mold", be, "SYS", history, Settings(), r, _bm)
    assert len(r.labels) == 3  # three hidden samples
    assert r.streamed == ["reconciled"]  # one judge stream
    assert history[-2:] == [
        ("user", "how do I diagnose green mold"),
        ("assistant", "reconciled"),
    ]


def test_run_deep_degrades_when_all_samples_empty():
    be = _DeepBackend(samples=["", "  ", ""], judge="never")
    r = _RecRenderer()
    deep.run_deep("how do I diagnose mold", be, "SYS", [], Settings(), r, _bm)
    assert r.errors and "no answers" in r.errors[0]
    assert r.streamed == []  # no judge call when nothing to reconcile


def test_run_deep_grounds_when_query_needs_live_info(monkeypatch):
    class _FakeSearcher:
        def search(self, query, max_results=5):
            return [SearchResult("Title", "http://src", "snippet")]

    monkeypatch.setattr(deep, "build_searcher", lambda settings: _FakeSearcher())
    be = _DeepBackend(samples=["s1", "s2", "s3"], judge="rec")
    r = _RecRenderer()
    captured = {}

    def bm(history, system, user):
        captured["user"] = user
        return [{"role": "user", "content": user}]

    deep.run_deep("current oyster prices", be, "SYS", [], Settings(), r, bm)
    assert "http://src" in captured["user"]  # grounding injected into the turn
    assert "[1]" in captured["user"]


def test_run_deep_force_web_grounds_even_without_live_signal(monkeypatch):
    monkeypatch.setenv("CROWE_MYCELIUM_DEEP_SAMPLES", "2")

    class _FakeSearcher:
        def search(self, query, max_results=5):
            return [SearchResult("T", "http://forced", "snip")]

    monkeypatch.setattr(deep, "build_searcher", lambda settings: _FakeSearcher())
    be = _DeepBackend(samples=["s1", "s2"], judge="rec")
    r = _RecRenderer()
    captured = {}

    def bm(history, system, user):
        captured["user"] = user
        return [{"role": "user", "content": user}]

    # A plain knowledge question (no live-info signal), but force_web=True must
    # still ground it in a search.
    deep.run_deep("how do I fruit lion's mane", be, "SYS", [], Settings(), r, bm, force_web=True)
    assert "http://forced" in captured["user"]
