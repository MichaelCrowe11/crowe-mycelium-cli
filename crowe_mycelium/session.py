from __future__ import annotations

from dataclasses import dataclass

QUIT = {"/quit", "/exit", ":q"}
SWITCH = {"/local": "local", "/cloud": "cloud", "/auto": "auto"}
SIMPLE = {"/help": "help", "/reset": "reset", "/info": "info", "/doctor": "doctor"}


@dataclass(frozen=True)
class SlashResult:
    handled: bool
    action: str = ""
    arg: str = ""


def dispatch_slash(text: str) -> SlashResult:
    c = text.strip()
    if c in QUIT:
        return SlashResult(True, "quit")
    if c in SIMPLE:
        return SlashResult(True, SIMPLE[c])
    if c in SWITCH:
        return SlashResult(True, "switch", SWITCH[c])
    if c == "/search" or c.startswith("/search "):
        return SlashResult(True, "search", c[len("/search") :].strip())
    if c.startswith("/"):
        return SlashResult(True, "noop")
    return SlashResult(False)
