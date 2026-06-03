from crowe_mycelium.render.plain import PlainRenderer


def test_plain_writes_answer_to_stdout(capsys):
    out = PlainRenderer().render_stream(iter(["600-", "1200 ppm"]))
    captured = capsys.readouterr()
    assert out == "600-1200 ppm"
    assert "600-1200 ppm" in captured.out
    assert captured.err == ""


def test_plain_diagnostics_go_to_stderr(capsys):
    r = PlainRenderer()
    r.notice("switched to local")
    r.error("cloud down")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "switched to local" in captured.err
    assert "error: cloud down" in captured.err


def test_plain_deliberate_runs_fn_and_returns_result():
    assert PlainRenderer().deliberate("working", lambda: "DONE") == "DONE"
