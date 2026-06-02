from crowe_mycelium.model import load_system_prompt


def test_identity_is_crowe_first_no_gemma_blurt():
    sp = load_system_prompt().lower()
    # The model must NOT be told to introduce itself as a Gemma fine-tune.
    assert "fine-tune of google's gemma" not in sp
    assert "crowe mycelium" in sp
    assert "cultivation intelligence" in sp


def test_capability_honesty_rule_present():
    sp = load_system_prompt().lower()
    assert "cannot browse the web" in sp
    assert "tools" in sp
