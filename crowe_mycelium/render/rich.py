from __future__ import annotations

import threading
import time
from typing import Iterator

from rich.live import Live
from rich.markdown import Markdown
from rich.text import Text

from crowe_mycelium.branding import console
from crowe_mycelium.render.base import Renderer
from crowe_mycelium.render.thinking import crest_frame


class RichRenderer(Renderer):
    """Terminal output: an emerald thinking crest while the backend works (so a
    cold/slow backend is never a silent wait), then markdown-rendered answer."""

    def render_stream(self, chunks: Iterator[str]) -> str:
        box: dict = {"parts": [], "started": False, "done": False}

        def pull():
            try:
                for c in chunks:
                    box["parts"].append(c)
                    box["started"] = True
            except BaseException as e:  # surfaced after the live region closes
                box["err"] = e
            finally:
                box["done"] = True

        th = threading.Thread(target=pull, daemon=True)
        t0 = time.time()
        th.start()
        # Hold the crest for at least MIN_CREST_S on an interactive terminal, so
        # a fast warm response still plays the animation instead of flashing
        # past. No floor when piped (tests / non-TTY) so output stays instant.
        min_crest = 0.7 if console.is_terminal else 0.0
        with Live(console=console, refresh_per_second=30, transient=True) as live:
            tick = 0
            while not box["done"] or box["parts"]:
                elapsed = time.time() - t0
                if box["started"] and elapsed >= min_crest:
                    # First token arrived (crest has had its moment): grow live.
                    live.update(Markdown("".join(box["parts"])))
                else:
                    # Still waiting, or holding the crest floor: emerald crest.
                    live.update(Text.from_markup(crest_frame(tick, int(elapsed))))
                tick += 1
                if box["done"] and box["parts"] and elapsed >= min_crest:
                    break
                time.sleep(0.05)
        th.join()

        if "err" in box:
            raise box["err"]
        text = "".join(box["parts"])
        if text:
            console.print(Markdown(text))
        return text

    def notice(self, msg: str) -> None:
        console.print(f"[grey50]{msg}[/]")

    def error(self, msg: str) -> None:
        console.print(f"[bold red]error[/] {msg}")
