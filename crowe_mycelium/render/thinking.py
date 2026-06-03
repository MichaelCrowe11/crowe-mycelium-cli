from __future__ import annotations

# Emerald "cultivation" drift — distinct from crowe-logic gold / deepparallel cyan.
PALETTE = ["green3", "bright_green", "spring_green2", "green4", "dark_sea_green"]
_SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
MARK = "⬢"

# Amplified multi-line mycelial FIELD: several bright spores propagate across a
# field of strands at different phases, each leaving an emerald glow trail —
# reads as a living mycelium network colonizing while the model thinks.
_FIELD_W = 30
_FIELD_ROWS = 3


def _glyph(dist: int) -> str:
    """A field cell styled by its distance behind the nearest travelling spore."""
    if dist == 0:
        return "[bold bright_green]◆[/]"
    if dist == 1:
        return "[spring_green2]◈[/]"
    if dist == 2:
        return "[green3]◇[/]"
    if dist == 3:
        return "[green4]◌[/]"
    if dist == 4:
        return "[dark_sea_green]·[/]"
    return "[grey30]·[/]"


def _field_row(tick: int, row: int) -> str:
    """One strand with two spores travelling at offset phases."""
    h1 = (tick + row * 9) % _FIELD_W
    h2 = (tick + row * 9 + _FIELD_W // 2) % _FIELD_W
    cells = []
    for i in range(_FIELD_W):
        d = min((h1 - i) % _FIELD_W, (h2 - i) % _FIELD_W)
        cells.append(_glyph(d))
    return "".join(cells)


def crest_frame(tick: int, elapsed: int, label: str = "thinking") -> str:
    """Rich-markup string (multi-line) for one frame of the thinking crest.

    `label` is the verb on the middle strand ("thinking" by default,
    "deliberating · sample 2/3" for deep mode)."""
    color = PALETTE[tick % len(PALETTE)]
    spin = _SPIN[tick % len(_SPIN)]
    top = "   " + _field_row(tick, 0)
    # Middle strand carries the hex mark + the cycling-color label
    # (keeps the PALETTE[0]/"thinking"/elapsed test contract by default).
    mid = (
        f"[{color}]{MARK}[/]  {_field_row(tick, 1)}  "
        f"[grey50]{spin}[/] [bold {color}]{label}[/] [grey50]· {elapsed}s[/]"
    )
    bot = "   " + _field_row(tick, 2)
    return f"{top}\n{mid}\n{bot}"
