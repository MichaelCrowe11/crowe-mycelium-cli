from __future__ import annotations

# Emerald "cultivation" drift — distinct from crowe-logic gold / deepparallel cyan.
PALETTE = ["green3", "bright_green", "spring_green2", "green4", "dark_sea_green"]
_SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
MARK = "⬢"


def crest_frame(tick: int, elapsed: int) -> str:
    """Rich-markup string for one animation frame of the thinking crest."""
    spin = _SPIN[tick % len(_SPIN)]
    color = PALETTE[tick % len(PALETTE)]
    return f"[{color}]{MARK}[/] [grey50]{spin} thinking · {elapsed}s[/]"
