from crowe_mycelium import wordmark


def test_wide_terminal_gets_multiline_wordmark():
    art = wordmark.render_hero(width=80, backend_label="cloud · modal")
    plain = art.plain if hasattr(art, "plain") else str(art)
    assert plain.count("\n") >= 3  # block wordmark spans multiple lines


def test_narrow_terminal_gets_compact_fallback():
    art = wordmark.render_hero(width=40, backend_label="cloud · modal")
    plain = art.plain if hasattr(art, "plain") else str(art)
    assert "Crowe" in plain and "Mycelium" in plain
    assert plain.count("\n") <= 2  # compact, not the full block


def test_hud_shows_backend_model_version():
    line = wordmark.hud(backend_label="cloud · modal", version="0.3.0")
    plain = line.plain if hasattr(line, "plain") else str(line)
    assert "cloud · modal" in plain
    assert "gemma-4-mycelium-e4b" in plain
    assert "0.3.0" in plain
