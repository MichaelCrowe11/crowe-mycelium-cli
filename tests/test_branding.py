from rich.text import Text

from crowe_mycelium import branding


def test_hero_is_crowe_first_and_omits_gemma():
    t = branding.hero("auto · cloud-first")
    plain = t.plain if isinstance(t, Text) else str(t)
    assert "Crowe Logic" in plain
    assert "Mycelium" in plain
    assert "cultivation" in plain
    assert "Gemma" not in plain  # attribution lives in the footer, not the hero


def test_footer_text_carries_required_attribution():
    assert "built with Gemma" in branding.footer_text()


def test_backend_tag_wraps_label():
    assert "cloud · modal" in branding.backend_tag("cloud · modal")
