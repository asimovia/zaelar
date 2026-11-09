"""The update manifest: ONE signed JSON file per release that tells an installed daemon what is newest and what its
bytes hash to. Written by `daemon/packaging/update_manifest.py` in CI, read by `check.py` on the user's machine —
both import THIS module, so the asset names, the platform keys and the shape cannot drift between writer and reader.

    {
      "product": "zaelar-daemon",
      "version": "0.2.2",              the daemon's own contract version (`daemon.VERSION`)
      "build": 123,                    the engine's `update/BUILD` at the tag — the number a person compares
      "tag": "v3.140",                 the release that publishes it (checked against where it was found)
      "published_at": "2026-11-09T…Z",
      "min_engine_build": 0,           the oldest engine build this daemon works with (0 = any)
      "platforms": {
        "macos":        {"asset": "Zaelar-macos.zip",          "sha256": "…", "size": 123},
        "macos-x86_64": {"asset": "Zaelar-macos-x86_64.zip",   "sha256": "…", "size": 123},
        "windows":      {"asset": "zaelar-daemon-windows.exe", "sha256": "…", "size": 123},
        "pyz":          {"asset": "zaelar-daemon-macos.pyz",   "sha256": "…", "size": 123}
      },
      "installers": {"macos": {"asset": "Zaelar-macos.pkg", …}}   only when the notarized .pkg was built
      "next_key": null                 a minisign public key the NEXT releases may be signed with (rotation)
    }

THE SIGNATURE IS THE ONLY THING THAT MAKES ANY OF THIS TRUE. The manifest travels beside the binaries it describes,
so whoever can replace one can replace the other; `update-manifest.json.minisig`, made with a key that is NOT in
the release and verified against the public key committed in this repository (`daemon/update/PUBLIC_KEY`), is what
turns "a file that says so" into "the publisher says so". An unsigned manifest is refused by the client, always.

`next_key` is how the key rotates without a flag day: a manifest signed by a key the client already trusts may
announce the next one, and the client remembers it (`state.json`). A key is only ever LEARNED from a manifest that
verified — never from the network on its own.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

PRODUCT = "zaelar-daemon"
MANIFEST_NAME = "update-manifest.json"
SIGNATURE_NAME = MANIFEST_NAME + ".minisig"

# Platform key → (the asset the updater installs, the build job suffix whose `SHA256SUMS-<suffix>` lists it).
# The `.pyz` is the same program on every OS; it is taken from the Apple Silicon job, which also publishes the
# installer scripts, so exactly one copy is named.
PLATFORMS: dict[str, tuple[str, str]] = {
    "macos": ("Zaelar-macos.zip", "macos"),
    "macos-x86_64": ("Zaelar-macos-x86_64.zip", "macos-x86_64"),
    "windows": ("zaelar-daemon-windows.exe", "windows"),
    "pyz": ("zaelar-daemon-macos.pyz", "macos"),
}

# The notarized installer packages, when the release has them (only with the Apple identity). Listed so that the
# one-line installer can check a `.pkg` against the SIGNED manifest too; the updater itself installs the zip.
INSTALLERS: dict[str, tuple[str, str]] = {
    "macos": ("Zaelar-macos.pkg", "macos"),
    "macos-x86_64": ("Zaelar-macos-x86_64.pkg", "macos-x86_64"),
}

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ASSET = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_VERSION = re.compile(r"^\d+(\.\d+){0,3}$")


class ManifestError(ValueError):
    """The manifest is not the shape this client understands — refused, the same as a bad signature."""


@dataclass(frozen=True)
class Asset:
    asset: str
    sha256: str
    size: int


@dataclass(frozen=True)
class Manifest:
    version: str
    build: int
    tag: str
    published_at: str
    min_engine_build: int
    platforms: dict
    next_key: str | None

    def summary(self) -> dict:
        return {"version": self.version, "build": self.build, "tag": self.tag, "published_at": self.published_at}


def version_tuple(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(p) for p in str(version).split("."))
    except ValueError:
        return (0,)


def is_newer(candidate: Manifest, current_version: str, current_build: int) -> bool:
    """`build` decides — it moves on every release and is what a person compares. The daemon's own `version` only
    breaks a tie, for a build that does not know its build number (0: run from an unstamped tree)."""
    if current_build and candidate.build:
        return candidate.build > current_build
    return version_tuple(candidate.version) > version_tuple(current_version)


def parse(data: bytes) -> Manifest:
    """Parse and validate. Anything unexpected is a `ManifestError`: a client that guesses at a malformed manifest
    is a client that can be steered by one."""
    try:
        raw = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ManifestError("the manifest is not JSON") from e
    if not isinstance(raw, dict) or raw.get("product") != PRODUCT:
        raise ManifestError("the manifest is not a zaelar-daemon manifest")
    version = raw.get("version")
    if not isinstance(version, str) or not _VERSION.match(version):
        raise ManifestError("the manifest has no valid version")
    build = raw.get("build")
    if not isinstance(build, int) or isinstance(build, bool) or build < 0:
        raise ManifestError("the manifest has no valid build number")
    tag = raw.get("tag")
    if not isinstance(tag, str) or not tag or len(tag) > 128:
        raise ManifestError("the manifest names no release tag")
    min_engine = raw.get("min_engine_build", 0)
    if not isinstance(min_engine, int) or isinstance(min_engine, bool) or min_engine < 0:
        raise ManifestError("min_engine_build is not a number")
    platforms_raw = raw.get("platforms")
    if not isinstance(platforms_raw, dict) or not platforms_raw:
        raise ManifestError("the manifest lists no platforms")
    platforms: dict[str, Asset] = {}
    for key, entry in platforms_raw.items():
        if key not in PLATFORMS or not isinstance(entry, dict):
            continue   # a platform this client does not know is not an error; it is just not ours
        asset, sha, size = entry.get("asset"), entry.get("sha256"), entry.get("size")
        if not isinstance(asset, str) or not _ASSET.match(asset):
            raise ManifestError(f"platform {key}: invalid asset name")
        if not isinstance(sha, str) or not _SHA256.match(sha):
            raise ManifestError(f"platform {key}: invalid sha256")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            raise ManifestError(f"platform {key}: invalid size")
        platforms[key] = Asset(asset, sha, size)
    next_key = raw.get("next_key")
    if next_key is not None and not isinstance(next_key, str):
        raise ManifestError("next_key must be a public key string or null")
    return Manifest(version, build, tag, str(raw.get("published_at") or ""), min_engine, platforms, next_key)
