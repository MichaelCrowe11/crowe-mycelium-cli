"""Paste-safe REPL input via prompt-toolkit.

Bare console.input() reads line-at-a-time, so a multi-line paste gets shredded
and the prompt tag interleaves into the captured text. A prompt-toolkit
PromptSession captures a bracketed paste as one submission, offers slash-command
completion, and keeps per-session history. Non-TTY (piped) input falls back to
builtin input() so `run`/pipes keep working.
"""

from __future__ import annotations

import sys

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import InMemoryHistory

from crowe_mycelium.session import QUIT, SIMPLE, SWITCH


def slash_commands() -> list[str]:
    """All REPL slash commands, derived from the dispatcher (single source)."""
    cmds = set(SWITCH) | set(SIMPLE) | set(QUIT)
    return sorted(cmds)


def build_session() -> PromptSession:
    completer = WordCompleter(slash_commands(), sentence=False)
    return PromptSession(completer=completer, history=InMemoryHistory())


def read_input(session, tag: str) -> str:
    """Read one user submission. TTY → prompt-toolkit session; else builtin input."""
    if not sys.stdin.isatty():
        return input()
    return session.prompt(tag)
