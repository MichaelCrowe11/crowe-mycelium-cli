from crowe_mycelium import prompt


def test_slash_commands_cover_all_repl_commands():
    cmds = set(prompt.slash_commands())
    assert {"/local", "/cloud", "/auto", "/info", "/reset", "/doctor", "/help", "/quit"} <= cmds


def test_read_input_non_tty_falls_back_to_builtin_input(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    monkeypatch.setattr("builtins.input", lambda *_: "piped line")
    # session is unused on the non-TTY path; pass a sentinel to prove it.
    out = prompt.read_input(session=None, tag="[cloud] ▸ ")
    assert out == "piped line"


def test_read_input_tty_uses_session_prompt(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    class FakeSession:
        def __init__(self):
            self.called_with = None

        def prompt(self, message):
            self.called_with = message
            return "typed line"

    s = FakeSession()
    out = prompt.read_input(session=s, tag="[cloud] ▸ ")
    assert out == "typed line"
    assert "[cloud]" in str(s.called_with)
