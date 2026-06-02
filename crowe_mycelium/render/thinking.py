from __future__ import annotations

# Emerald "cultivation" drift — distinct from crowe-logic gold / deepparallel cyan.
PALETTE = ["green3", "bright_green", "spring_green2", "green4", "dark_sea_green"]
_SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
MARK = "⬢"

# Amplified mycelial-strand crest: a bright spore node travels along a strand of
# nodes, leaving an emerald glow trail — reads as a signal propagating through
# mycelium. Much more visible than a single spinner char.
_STRAND_LEN = 22


def _strand(tick: int) -> str:
    """A row of nodes with one bright travelling spore + a fading glow trail."""
    head = tick % _STRAND_LEN
    cells: list[str] = []
    for i in range(_STRAND_LEN):
        dist = (head - i) % _STRAND_LEN  # 0 at head, grows behind it
        if dist == 0:
            cells.append("[bold bright_green]◆[/]")
        elif dist == 1:
            cells.append("[spring_green2]◈[/]")
        elif dist == 2:
            cells.append("[green3]◇[/]")
        elif dist == 3:
            cells.append("[green4]◌[/]")
        else:
            cells.append("[grey30]·[/]")
    return "".join(cells)


def crest_frame(tick: int, elapsed: int) -> str:
    """Rich-markup string for one animation frame of the thinking crest."""
    spin = _SPIN[tick % len(_SPIN)]
    color = PALETTE[tick % len(PALETTE)]
    strand = _strand(tick)
    # PALETTE[color] on the lead hex keeps the cycling-color test contract.
    return (
        f"[{color}]{MARK}[/] {strand} "
        f"[grey50]{spin}[/] [bold {color}]thinking[/] [grey50]· {elapsed}s[/]"
    )
