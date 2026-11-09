"""Draw the tray icons committed under `daemon/tray/icons/` (run once when the glyphs change; needs Pillow).

The PNGs are committed rather than drawn at run time so the macOS build does not need Pillow at all: the menu bar
loads a file. Three states, told apart by SHAPE because a macOS template image has no colour of its own:
    connected  a ring with a full dot      waiting  a ring with a half dot      error  a ring with a cross

    python daemon/packaging/tray_icons.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "tray" / "icons"
COLOURS = {"connected": (46, 160, 67, 255), "waiting": (219, 154, 4, 255), "error": (207, 34, 46, 255)}


def _glyph(draw: ImageDraw.ImageDraw, size: int, state: str, ink) -> None:
    pad, ring = size * 0.12, max(2, round(size * 0.09))
    draw.ellipse([pad, pad, size - pad, size - pad], outline=ink, width=ring)
    c, r = size / 2, size * 0.17
    if state == "connected":
        draw.ellipse([c - r, c - r, c + r, c + r], fill=ink)
    elif state == "waiting":
        draw.pieslice([c - r, c - r, c + r, c + r], 90, 270, fill=ink)
        draw.arc([c - r, c - r, c + r, c + r], 270, 90, fill=ink, width=max(1, ring // 2))
    else:
        w = max(2, ring)
        draw.line([c - r, c - r, c + r, c + r], fill=ink, width=w)
        draw.line([c - r, c + r, c + r, c - r], fill=ink, width=w)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for state, colour in COLOURS.items():
        template = Image.new("RGBA", (36, 36), (0, 0, 0, 0))
        _glyph(ImageDraw.Draw(template), 36, state, (0, 0, 0, 255))
        template.save(OUT / f"{state}-template.png", optimize=True)
        coloured = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(coloured)
        d.ellipse([1, 1, 63, 63], fill=colour)
        _glyph(d, 64, state, (255, 255, 255, 255))
        coloured.save(OUT / f"{state}.png", optimize=True)
    print(f"icons → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
