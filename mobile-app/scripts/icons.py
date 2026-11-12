"""Draw the native app's icon set and launch mark — one source, every file Xcode needs.

    ../.venv/bin/python scripts/icons.py                    # the mark drawn by frontend/mobile/icons/generate.py
    ../.venv/bin/python scripts/icons.py --source brand.png # a designed icon (square, ≥1024 px) replaces the mark

Writes into ios/App/App/Assets.xcassets:
  · AppIcon.appiconset — the single 1024×1024 image Xcode 14+ derives every size from, opaque (the App Store refuses
    an icon with alpha), plus the iOS 18 dark and tinted appearances (the mark on a transparent background; with
    --source they reuse the source);
  · Splash.imageset — the mark alone on transparent, shown centred on the dark launch screen
    (Base.lproj/LaunchScreen.storyboard).
With --android it writes the Android set instead (android/app/src/main/res), from the same source:
  · mipmap-*/ic_launcher_foreground.png — the adaptive icon's layer (108 dp, the mark inside the 66 dp safe circle) on
    the black background of values/ic_launcher_background.xml, plus ic_launcher_monochrome.png (Android 13 themed
    icons: the mark's silhouette, the launcher tints it);
  · mipmap-*/ic_launcher.png and ic_launcher_round.png — the legacy square and round icons (before Android 8);
  · drawable-*/splash_mark.png — the mark the Android 12+ splash shows centred on the dark background (240 dp, the
    mark inside its 160 dp circle);
  · build/store/play-icon-512.png — the 512×512 listing icon Play asks for (opaque; Play applies its own mask).
The PWA icons stay generate.py's job; this script only imports its `icon()` drawing so both share one geometry.
"""
import argparse
import importlib.util
import json
from pathlib import Path

from PIL import Image

APP = Path(__file__).resolve().parents[1]
ASSETS = APP / "ios/App/App/Assets.xcassets"
RES = APP / "android/app/src/main/res"
DENSITIES = {"mdpi": 1, "hdpi": 1.5, "xhdpi": 2, "xxhdpi": 3, "xxxhdpi": 4}
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


def _on(size, mark, fraction, background=(0, 0, 0, 0), circle=False):
    """`mark` (transparent, square, the drawing filling it) centred at `fraction` of a `size` canvas."""
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    if circle:
        from PIL import ImageDraw
        ImageDraw.Draw(canvas).ellipse((0, 0, size - 1, size - 1), fill=background)
    else:
        canvas.paste(background, (0, 0, size, size))
    m = mark.resize((round(size * fraction),) * 2, Image.LANCZOS)
    off = (size - m.size[0]) // 2
    canvas.alpha_composite(m, (off, off))
    return canvas


def android(mark):
    """The Android set from `mark`: the drawing alone, cropped to its bounds, on transparent."""
    black = (0, 0, 0, 255)
    silhouette = Image.new("RGBA", mark.size, (255, 255, 255, 0))
    silhouette.putalpha(mark.getchannel("A"))
    for name, k in DENSITIES.items():
        mip = RES / f"mipmap-{name}"
        mip.mkdir(parents=True, exist_ok=True)
        fg = round(108 * k)
        _on(fg, mark, 0.56).save(mip / "ic_launcher_foreground.png")
        _on(fg, silhouette, 0.56).save(mip / "ic_launcher_monochrome.png")
        legacy = round(48 * k)
        _on(legacy, mark, 0.62, black).save(mip / "ic_launcher.png")
        _on(legacy, mark, 0.58, black, circle=True).save(mip / "ic_launcher_round.png")
        drw = RES / f"drawable-{name}"
        drw.mkdir(parents=True, exist_ok=True)
        _on(round(240 * k), mark, 0.6).save(drw / "splash_mark.png")
    store = APP / "build/store"
    store.mkdir(parents=True, exist_ok=True)
    _on(512, mark, 0.61, black).convert("RGB").save(store / "play-icon-512.png")
    print("android icons, splash mark and Play icon written")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", help="a square PNG (≥1024 px) to use instead of the drawn mark")
    ap.add_argument("--android", action="store_true", help="write the Android set instead of the iOS one")
    a = ap.parse_args()
    if a.android:
        src = Image.open(a.source).convert("RGBA") if a.source else _mark(1024, (0, 0, 0, 0))
        l, t, r, b = src.getchannel("A").getbbox()
        side, cx, cy = max(r - l, b - t), (l + r) / 2, (t + b) / 2   # a square around the drawing: never stretch it
        return android(src.crop((round(cx - side / 2), round(cy - side / 2), round(cx + side / 2), round(cy + side / 2))))
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
