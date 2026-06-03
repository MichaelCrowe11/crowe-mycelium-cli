import pytest

from crowe_mycelium.session import dispatch_slash, SlashResult


@pytest.mark.parametrize(
    "cmd,action",
    [
        ("/quit", "quit"),
        ("/exit", "quit"),
        (":q", "quit"),
        ("/help", "help"),
        ("/reset", "reset"),
        ("/info", "info"),
        ("/doctor", "doctor"),
    ],
)
def test_known_commands(cmd, action):
    r = dispatch_slash(cmd)
    assert r.handled and r.action == action


@pytest.mark.parametrize("cmd,arg", [("/local", "local"), ("/cloud", "cloud"), ("/auto", "auto")])
def test_switch_commands(cmd, arg):
    r = dispatch_slash(cmd)
    assert r.handled and r.action == "switch" and r.arg == arg


def test_unknown_slash_is_handled_noop():
    r = dispatch_slash("/wat")
    assert r.handled and r.action == "noop"


def test_plain_text_is_not_a_slash():
    r = dispatch_slash("how do I fruit lion's mane?")
    assert r == SlashResult(handled=False)


def test_search_with_query_dispatches_with_arg():
    r = dispatch_slash("/search oyster wholesale prices")
    assert r.handled and r.action == "search" and r.arg == "oyster wholesale prices"


def test_bare_search_dispatches_empty_arg():
    r = dispatch_slash("/search")
    assert r.handled and r.action == "search" and r.arg == ""


def test_deep_with_query_dispatches_with_arg():
    r = dispatch_slash("/deep how do I diagnose green mold")
    assert r.handled and r.action == "deep" and r.arg == "how do I diagnose green mold"


def test_deep_web_arg_preserved():
    r = dispatch_slash("/deep web oyster prices")
    assert r.handled and r.action == "deep" and r.arg == "web oyster prices"


def test_bare_deep_dispatches_empty_arg():
    r = dispatch_slash("/deep")
    assert r.handled and r.action == "deep" and r.arg == ""
