"""The keys `Zaelar.app`'s `Info.plist` must carry, and the one function that writes them (used by `build.py`).

    CFBundleIdentifier   com.zaelar.daemon — the identity macOS files its permission grants under; the
                         LaunchAgent label is the same string
    LSUIElement          true — no Dock icon and no app menu: the daemon lives in the menu bar
    NS…UsageDescription  the sentence macOS shows in ITS OWN prompt the first time the daemon reads a protected folder
                         (Documents, Desktop, Downloads). Without them the prompt carries no reason at all. English
                         here; translations belong to the bundle's localized `InfoPlist.strings`, a later step.

PyInstaller's command line cannot set arbitrary plist keys, so the build patches the generated file after the fact,
before anything signs the bundle.
"""
from __future__ import annotations

import plistlib
from pathlib import Path

BUNDLE_ID = "com.zaelar.daemon"
NAME = "Zaelar"

USAGE = {
    "NSDocumentsFolderUsageDescription":
        "Zaelar reads the documents in the folders you allow, to find or read them when you ask.",
    "NSDesktopFolderUsageDescription":
        "Zaelar only looks at your Desktop if you allow it, to find what you ask for.",
    "NSDownloadsFolderUsageDescription":
        "Zaelar reads your Downloads only if you allow it, to open or find what you downloaded.",
}


def keys(version: str) -> dict:
    return {
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleName": NAME,
        "CFBundleDisplayName": NAME,
        "CFBundleShortVersionString": version,
        "CFBundleVersion": version,
        "LSUIElement": True,
        "NSHighResolutionCapable": True,
        **USAGE,
    }


def apply(plist_path: Path, version: str) -> dict:
    """Merge the keys into an existing `Info.plist` (keeping what PyInstaller wrote, e.g. `CFBundleExecutable`)."""
    with open(plist_path, "rb") as fh:
        data = plistlib.load(fh)
    data.update(keys(version))
    with open(plist_path, "wb") as fh:
        plistlib.dump(data, fh)
    return data
