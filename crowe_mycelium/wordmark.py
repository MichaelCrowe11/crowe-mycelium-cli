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
    "███╗   ███╗██╗   ██╗ ██████╗███████╗██╗     ██╗██╗   ██╗███╗   ███╗\n"
    "████╗ ████║╚██╗ ██╔╝██╔════╝██╔════╝██║     ██║██║   ██║████╗ ████║\n"
    "██╔████╔██║ ╚████╔╝ ██║     █████╗  ██║     ██║██║   ██║██╔████╔██║\n"
    "██║╚██╔╝██║  ╚██╔╝  ██║     ██╔══╝  ██║     ██║██║   ██║██║╚██╔╝██║\n"
    "██║ ╚═╝ ██║   ██║   ╚██████╗███████╗███████╗██║╚██████╔╝██║ ╚═╝ ██║\n"
    "╚═╝     ╚═╝   ╚═╝    ╚═════╝╚══════╝╚══════╝╚═╝ ╚═════╝ ╚═╝     ╚═╝"
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


def hud(backend_label: str, version: str, gpu: str | None = CLOUD_GPU) -> Text:
    """Always-visible status line: backend · [gpu ·] model · version.

    `gpu` is shown only when set — pass None for local (no cloud GPU) so the
    HUD doesn't misleadingly claim an L4 for on-device inference.
    """
    t = Text()
    t.append("backend ", style=DIM)
    t.append(backend_label, style="white")
    if gpu:
        t.append(f" ({gpu})", style=DIM)
    t.append("   ·   model ", style=DIM)
    t.append(MODEL_NAME, style="white")
    t.append("   ·   ", style=DIM)
    t.append(f"v{version}", style=DIM)
    return t


def animate_hero(console, width: int) -> None:
    """Animated startup reveal of the block wordmark.

    A left-to-right 'mycelial colonization' sweep: the glyphs fill in column by
    column with a bright leading edge, then settle to steady emerald. Falls back
    to a static print on narrow terminals or non-TTYs (piping) so nothing breaks.
    """
    import time

    from rich.live import Live

    if width < NARROW_THRESHOLD or not getattr(console, "is_terminal", False):
        console.print(render_hero(width, ""))
        return

    rows = _WORDMARK.split("\n")
    w = max(len(r) for r in rows)
    padded = [r.ljust(w) for r in rows]

    console.print(Text(f"{MARK} CROWE LOGIC", style=f"bold {EMERALD_BRIGHT}"))
    with Live(console=console, refresh_per_second=120, transient=False) as live:
        for c in range(1, w + 1):
            t = Text()
            for idx, r in enumerate(padded):
                shown = r[:c]
                t.append(shown[:-1], style=f"bold {EMERALD}")
                t.append(shown[-1], style="bold bright_green")  # glowing edge
                if idx < len(padded) - 1:
                    t.append("\n")
            live.update(t)
            time.sleep(0.010)
        live.update(Text(_WORDMARK, style=f"bold {EMERALD}"))  # settle
    console.print(Text("  cultivation intelligence", style=DIM))
