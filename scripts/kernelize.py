#!/usr/bin/env python3
"""Convert a jupytext-style .py to a Kaggle-ready .ipynb.

jupytext alone produces a notebook without a ``kernelspec`` metadata block.
Papermill (Kaggle's executor) refuses such notebooks with
``ValueError: No kernel name found in notebook and no override provided``.

This script wraps jupytext + injects the python3 kernelspec that Kaggle's
Papermill needs. Use it as the canonical "py → Kaggle .ipynb" converter
in the ship_phase2.sh pipeline.

Usage:
    python scripts/kernelize.py SCRIPT.py NOTEBOOK.ipynb
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


_KERNELSPEC = {
    "display_name": "Python 3",
    "language": "python",
    "name": "python3",
}
_LANGUAGE_INFO = {
    "name": "python",
    "version": "3.12",
    "mimetype": "text/x-python",
    "file_extension": ".py",
    "codemirror_mode": {"name": "ipython", "version": 3},
    "pygments_lexer": "ipython3",
}


def kernelize(src: Path, dst: Path) -> None:
    # Use jupytext for the cell-split, then patch metadata for Papermill.
    subprocess.run(
        [sys.executable, "-m", "jupytext", "--to", "ipynb", str(src), "-o", str(dst)],
        check=True,
    )
    nb = json.loads(dst.read_text())
    nb.setdefault("metadata", {})
    nb["metadata"]["kernelspec"] = _KERNELSPEC
    nb["metadata"]["language_info"] = _LANGUAGE_INFO
    dst.write_text(json.dumps(nb, indent=1) + "\n")


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    if not src.exists():
        print(f"ERROR: source not found: {src}", file=sys.stderr)
        return 1
    dst.parent.mkdir(parents=True, exist_ok=True)
    kernelize(src, dst)
    print(f"wrote {dst} ({dst.stat().st_size:,} bytes, with kernelspec)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
