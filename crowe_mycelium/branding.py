"""Compact Rich-based UI matching the Crowe Logic aesthetic.

This is a stripped-down sibling of cli/branding.py in crowe-logic-foundry.
Kept intentionally small so the CLI starts fast and stays portable.
"""

from __future__ import annotations

from rich.console import Console
from rich.text import Text

console = Console()

CROWE_DIM = "grey50"


def info(msg: str) -> None:
    console.print(f"[{CROWE_DIM}]{msg}[/]")


def error(msg: str) -> None:
    console.print(f"[bold red]error[/] {msg}")


# --- Emerald peer-design palette (Phase 1 redesign) ---
EMERALD = "green3"
EMERALD_BRIGHT = "bright_green"
DIM = "grey50"
MARK = "◆"


def hero(backend_label: str) -> Text:
    """Clean, Crowe-first welcome line. Gemma attribution is NOT here (footer)."""
    t = Text()
    t.append(f"{MARK} ", style=EMERALD_BRIGHT)
    t.append("Crowe Logic ", style=f"bold {EMERALD_BRIGHT}")
    t.append("· ", style=DIM)
    t.append("Mycelium", style=f"bold {EMERALD}")
    t.append("        cultivation", style=DIM)
    t.append(f"\n  backend: {backend_label}   ·   /help", style=DIM)
    return t


def footer_text() -> str:
    """Required Gemma attribution — rendered dim, once per session."""
    return "built with Gemma · Gemma Terms apply (https://ai.google.dev/gemma/terms)"


def footer() -> None:
    console.print(f"[{DIM}]{footer_text()}[/]")


def backend_tag(label: str) -> str:
    """Prompt tag showing the active backend, e.g. [cloud · modal]."""
    return f"[{DIM}]\\[{label}][/]"


def turn_separator() -> None:
    """A thin dim rule between turns so the transcript doesn't read as a wall."""
    console.print(f"[{DIM}]" + "─" * 24 + "[/]")
