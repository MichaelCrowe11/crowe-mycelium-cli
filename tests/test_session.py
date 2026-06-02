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
