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
        with Live(console=console, refresh_per_second=12, transient=True) as live:
            tick = 0
            while not box["done"] or box["parts"]:
                if box["started"]:
                    # First token arrived: show the answer growing live.
                    live.update(Markdown("".join(box["parts"])))
                else:
                    # Still waiting on the backend: emerald thinking crest.
                    live.update(Text.from_markup(crest_frame(tick, int(time.time() - t0))))
                tick += 1
                if box["done"] and box["parts"]:
                    break
                time.sleep(0.08)
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
