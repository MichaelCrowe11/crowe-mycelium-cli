from crowe_mycelium.render.thinking import crest_frame, PALETTE
from crowe_mycelium.render.rich import RichRenderer


def test_crest_frame_shows_elapsed_and_cycles_color():
    f0 = crest_frame(0, 3)
    assert "thinking" in f0 and "3s" in f0
    assert PALETTE[0] in f0
    assert crest_frame(1, 3) != f0  # spinner/color advances


def test_rich_render_returns_full_text():
    # RichRenderer must still return the accumulated answer (used for history).
    out = RichRenderer().render_stream(iter(["**bold** answer"]))
    assert out == "**bold** answer"


def test_rich_render_accumulates_multiple_chunks():
    out = RichRenderer().render_stream(iter(["Increase ", "FAE ", "now."]))
    assert out == "Increase FAE now."


def test_rich_render_propagates_midstream_error():
    def boom():
        yield "partial"
        raise RuntimeError("backend died")

    import pytest

    with pytest.raises(RuntimeError, match="backend died"):
        RichRenderer().render_stream(boom())


def test_crest_frame_accepts_custom_label():
    from crowe_mycelium.render.thinking import crest_frame

    assert "deliberating" in crest_frame(0, 3, label="deliberating")
    assert "thinking" in crest_frame(0, 3)  # default unchanged


def test_rich_deliberate_runs_fn_and_returns_result():
    assert RichRenderer().deliberate("working", lambda: "DONE") == "DONE"


def test_rich_deliberate_propagates_error():
    import pytest

    def boom():
        raise RuntimeError("sample died")

    with pytest.raises(RuntimeError, match="sample died"):
        RichRenderer().deliberate("working", boom)
