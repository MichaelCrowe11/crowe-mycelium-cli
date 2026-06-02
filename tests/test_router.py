import pytest

from crowe_mycelium.backends.router import AutoBackend
from tests.conftest import FakeBackend


def _msgs():
    return [{"role": "user", "content": "hi"}]


def test_auto_prefers_cloud_when_healthy():
    cloud = FakeBackend(name="cloud", chunks=["from cloud"], healthy=True)
    local = FakeBackend(name="local", chunks=["from local"], healthy=True)
    r = AutoBackend(cloud=cloud, local=local)
    assert list(r.stream_chat(_msgs())) == ["from cloud"]
    assert r.label == "cloud · test"


def test_auto_falls_back_to_local_when_cloud_down():
    cloud = FakeBackend(name="cloud", healthy=False)
    local = FakeBackend(name="local", chunks=["from local"], healthy=True)
    r = AutoBackend(cloud=cloud, local=local)
    assert list(r.stream_chat(_msgs())) == ["from local"]
    assert r.label == "local · test"


def test_auto_raises_when_both_down():
    r = AutoBackend(cloud=FakeBackend(healthy=False), local=FakeBackend(healthy=False))
    with pytest.raises(RuntimeError, match="No backend available"):
        list(r.stream_chat(_msgs()))


def test_fell_back_flag_tracks_fallback():
    # cloud healthy -> no fallback
    r = AutoBackend(
        cloud=FakeBackend(name="cloud", chunks=["c"], healthy=True),
        local=FakeBackend(name="local", chunks=["l"], healthy=True),
    )
    list(r.stream_chat(_msgs()))
    assert r.fell_back is False
    # cloud down, local up -> fell back
    r2 = AutoBackend(
        cloud=FakeBackend(name="cloud", healthy=False),
        local=FakeBackend(name="local", chunks=["l"], healthy=True),
    )
    list(r2.stream_chat(_msgs()))
    assert r2.fell_back is True


def test_escalate_seam_is_stored_but_unused_in_phase1():
    esc = FakeBackend(name="forge")
    r = AutoBackend(cloud=FakeBackend(), local=FakeBackend(), escalate=esc)
    assert r.escalate is esc  # reserved for Phase 5; not routed to yet
