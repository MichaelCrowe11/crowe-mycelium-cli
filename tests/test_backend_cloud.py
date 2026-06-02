from crowe_mycelium.backends.cloud import CloudModalBackend


def test_cloud_sends_full_messages_including_system():
    captured = {}

    def fake_caller(messages, temperature):
        captured["messages"] = messages
        captured["temperature"] = temperature
        yield "cloud "
        yield "answer"

    b = CloudModalBackend(caller=fake_caller)
    msgs = [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "ans1"},
        {"role": "user", "content": "second"},
    ]
    out = list(b.stream_chat(msgs, temperature=0.5))
    assert out == ["cloud ", "answer"]
    # Multi-turn path: full role-separated messages reach the cloud, system included.
    assert captured["messages"] == msgs
    assert captured["temperature"] == 0.5


def test_cloud_health_false_when_probe_raises():
    def boom():
        raise RuntimeError("no modal")

    b = CloudModalBackend(health_probe=boom)
    assert b.health() is False
