"""Compact Rich-based UI matching the Crowe Logic aesthetic.

This is a stripped-down sibling of cli/branding.py in crowe-logic-foundry.
Kept intentionally small so the CLI starts fast and stays portable.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich import box

console = Console()

CROWE_ACCENT = "bright_green"
CROWE_DIM = "grey50"
GEMMA_ACCENT = "bright_blue"


def welcome(model_label: str, base_model: str, backend_label: str) -> None:
    """Show the startup banner."""
    title = Text()
    title.append("Crowe Logic ", style=f"bold {CROWE_ACCENT}")
    title.append("·", style=CROWE_DIM)
    title.append(f" {model_label}", style=f"bold {GEMMA_ACCENT}")

    body = Text()
    body.append("Built on ", style=CROWE_DIM)
    body.append("Gemma", style=f"bold {GEMMA_ACCENT}")
    body.append(f" ({base_model})\n", style=CROWE_DIM)
    body.append("Backend: ", style=CROWE_DIM)
    body.append(backend_label, style="white")
    body.append("\n\nType your question. ", style=CROWE_DIM)
    body.append("/help", style="bold")
    body.append(" for commands, ", style=CROWE_DIM)
    body.append("/quit", style="bold")
    body.append(" to exit.", style=CROWE_DIM)

    console.print(Panel(body, title=title, border_style=CROWE_ACCENT, box=box.ROUNDED))


def user_prefix() -> str:
    return f"[bold {CROWE_ACCENT}]you[/] "


def model_prefix(label: str) -> str:
    return f"[bold {GEMMA_ACCENT}]{label}[/] "


def info(msg: str) -> None:
    console.print(f"[{CROWE_DIM}]{msg}[/]")


def error(msg: str) -> None:
    console.print(f"[bold red]error[/] {msg}")


def attribution_footer() -> None:
    """Required Gemma attribution rendered once per session.

    Per the Gemma Terms of Use, derivatives must surface Gemma attribution
    in user-facing experiences.
    """
    console.print(
        f"[{CROWE_DIM}]Gemma 4 Mycelium is built on Google Gemma. "
        f"Use is subject to the Gemma Terms of Use "
        f"(https://ai.google.dev/gemma/terms).[/]"
    )


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
