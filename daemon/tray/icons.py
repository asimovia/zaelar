"""The icon files, one per state, shipped as data next to this module (`icons/`).

  `<state>-template.png`  macOS: black glyph on transparent, 36×36 (the @2x of an 18 pt menu-bar icon). Marked as a
                          TEMPLATE, so macOS tints it for a light or dark menu bar — which is why the states differ by
                          SHAPE (full dot · half dot · cross), not by colour.
  `<state>.png`           Windows / Linux: the same glyph, white on a coloured disc, 64×64.
"""
from __future__ import annotations

import sys
from pathlib import Path


def folder() -> Path:
    """`daemon/tray/icons/`, or the copy PyInstaller unpacked next to the frozen program."""
    here = Path(__file__).resolve().parent / "icons"
    if here.is_dir():
        return here
    base = Path(getattr(sys, "_MEIPASS", "") or ".")
    return base / "daemon" / "tray" / "icons"


def path(state: str, template: bool) -> str:
    name = f"{state}-template.png" if template else f"{state}.png"
    return str(folder() / name)
