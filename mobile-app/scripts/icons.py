"""Draw the native app's icon set and launch mark — one source, every file Xcode needs.

    ../.venv/bin/python scripts/icons.py                    # the mark drawn by frontend/mobile/icons/generate.py
    ../.venv/bin/python scripts/icons.py --source brand.png # a designed icon (square, ≥1024 px) replaces the mark

Writes into ios/App/App/Assets.xcassets:
  · AppIcon.appiconset — the single 1024×1024 image Xcode 14+ derives every size from, opaque (the App Store refuses
    an icon with alpha), plus the iOS 18 dark and tinted appearances (the mark on a transparent background; with
    --source they reuse the source);
  · Splash.imageset — the mark alone on transparent, shown centred on the dark launch screen
    (Base.lproj/LaunchScreen.storyboard).
The PWA icons stay generate.py's job; this script only imports its `icon()` drawing so both share one geometry.
"""
import argparse
import importlib.util
import json
from pathlib import Path

from PIL import Image

APP = Path(__file__).resolve().parents[1]
ASSETS = APP / "ios/App/App/Assets.xcassets"
GENERATE = APP.parent / "frontend/mobile/icons/generate.py"
MARK = 0.185          # iris radius / icon size — the apple-touch-icon geometry (iOS applies its own mask)


def _generate():
    spec = importlib.util.spec_from_file_location("pwa_icons", GENERATE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _mark(size, background):
    gen = _generate()
    gen.BG = background
    return gen.icon(size, MARK, False)


def _write(folder, images, files):
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("*.png"):
        old.unlink()
    for name, img in files.items():
        img.save(folder / name)
    (folder / "Contents.json").write_text(json.dumps({"images": images, "info": {"author": "xcode", "version": 1}},
                                                     indent=2) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", help="a square PNG (≥1024 px) to use instead of the drawn mark")
    a = ap.parse_args()
    if a.source:
        src = Image.open(a.source).convert("RGBA").resize((1024, 1024), Image.LANCZOS)
        light = Image.alpha_composite(Image.new("RGBA", src.size, (0, 0, 0, 255)), src).convert("RGB")
        dark, tinted = src, src.convert("LA").convert("RGBA")
        splash = src.resize((360, 360), Image.LANCZOS)
    else:
        light = _mark(1024, (0, 0, 0, 255)).convert("RGB")
        dark = _mark(1024, (0, 0, 0, 0))
        tinted = dark.convert("LA").convert("RGBA")
        splash = _mark(360, (0, 0, 0, 0))
    universal = {"idiom": "universal", "platform": "ios", "size": "1024x1024"}
    _write(ASSETS / "AppIcon.appiconset", [
        {**universal, "filename": "AppIcon-1024.png"},
        {**universal, "filename": "AppIcon-1024-dark.png",
         "appearances": [{"appearance": "luminosity", "value": "dark"}]},
        {**universal, "filename": "AppIcon-1024-tinted.png",
         "appearances": [{"appearance": "luminosity", "value": "tinted"}]},
    ], {"AppIcon-1024.png": light, "AppIcon-1024-dark.png": dark, "AppIcon-1024-tinted.png": tinted})
    _write(ASSETS / "Splash.imageset", [
        {"idiom": "universal", "filename": "splash@3x.png", "scale": "3x"},
    ], {"splash@3x.png": splash})
    print("app icon and launch mark written")


if __name__ == "__main__":
    main()
