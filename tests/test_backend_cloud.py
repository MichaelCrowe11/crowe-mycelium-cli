from crowe_mycelium.backends.cloud import CloudModalBackend, flatten_messages


def test_flatten_uses_last_user_and_includes_history():
    msgs = [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "ans1"},
        {"role": "user", "content": "second"},
    ]
    out = flatten_messages(msgs)
    assert "SYS" not in out  # system is baked into the cloud model
    assert "first" in out and "ans1" in out and "second" in out
    assert out.rstrip().endswith("second")


def test_cloud_streams_one_chunk_via_injected_caller():
    captured = {}
    b = CloudModalBackend(caller=lambda p: (captured.setdefault("p", p), "cloud answer")[-1])
    out = list(b.stream_chat([{"role": "user", "content": "hi"}]))
    assert out == ["cloud answer"]
    assert "hi" in captured["p"]


def test_cloud_health_false_when_caller_lookup_raises():
    def boom():
        raise RuntimeError("no modal")

    b = CloudModalBackend(health_probe=boom)
    assert b.health() is False
