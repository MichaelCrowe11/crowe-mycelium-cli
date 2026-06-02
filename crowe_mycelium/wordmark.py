"""Block wordmark + status HUD — peer branding with crowe-logic / deepparallel.

Wide terminals get a bold multi-line ANSI-shadow block wordmark; narrow
terminals fall back to a compact one-line mark. The HUD shows the always-visible
context: backend, model, GPU, version.
"""

from __future__ import annotations

from rich.text import Text

EMERALD = "green3"
EMERALD_BRIGHT = "bright_green"
DIM = "grey50"
MARK = "◆"
MODEL_NAME = "gemma-4-mycelium-e4b"
CLOUD_GPU = "L4"
# The block wordmark is 67 cols wide; below this we use the compact mark.
NARROW_THRESHOLD = 69

# ANSI-shadow "MYCELIUM" (generated with pyfiglet, baked static — not a runtime
# dep). Tests assert line count / compact fallback, not exact glyphs.
_WORDMARK = (
    '███╗   ███╗██╗   ██╗ ██████╗███████╗██╗     ██╗██╗   ██╗███╗   ███╗\n'
    '████╗ ████║╚██╗ ██╔╝██╔════╝██╔════╝██║     ██║██║   ██║████╗ ████║\n'
    '██╔████╔██║ ╚████╔╝ ██║     █████╗  ██║     ██║██║   ██║██╔████╔██║\n'
    '██║╚██╔╝██║  ╚██╔╝  ██║     ██╔══╝  ██║     ██║██║   ██║██║╚██╔╝██║\n'
    '██║ ╚═╝ ██║   ██║   ╚██████╗███████╗███████╗██║╚██████╔╝██║ ╚═╝ ██║\n'
    '╚═╝     ╚═╝   ╚═╝    ╚═════╝╚══════╝╚══════╝╚═╝ ╚═════╝ ╚═╝     ╚═╝'
)


def render_hero(width: int, backend_label: str) -> Text:
    """The startup hero: bold block wordmark (wide) or compact mark (narrow)."""
    if width < NARROW_THRESHOLD:
        t = Text()
        t.append(f"{MARK} ", style=EMERALD_BRIGHT)
        t.append("Crowe ", style=f"bold {EMERALD_BRIGHT}")
        t.append("Mycelium", style=f"bold {EMERALD}")
        t.append("  · cultivation intelligence", style=DIM)
        return t

    t = Text()
    t.append(f"{MARK} CROWE LOGIC\n\n", style=f"bold {EMERALD_BRIGHT}")
    t.append(_WORDMARK, style=f"bold {EMERALD}")
    t.append("\n  cultivation intelligence", style=DIM)
    return t


def hud(backend_label: str, version: str, gpu: str = CLOUD_GPU) -> Text:
    """Always-visible status line: backend · model · gpu · version."""
    t = Text()
    t.append("backend ", style=DIM)
    t.append(backend_label, style="white")
    t.append(f" ({gpu})", style=DIM)
    t.append("   ·   model ", style=DIM)
    t.append(MODEL_NAME, style="white")
    t.append("   ·   ", style=DIM)
    t.append(f"v{version}", style=DIM)
    return t
