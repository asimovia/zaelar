"""Write `update-manifest.json` for a release — the file the installed daemon's updater trusts (V2-869 §4).

    python daemon/packaging/update_manifest.py <dir with every build job's renamed files> --tag v3.140

Runs in the workflow's `manifest` job, AFTER every build job has renamed its files (`release_names.py`) and signed
its sums (cosign): it reads the files under their PUBLISHED names, hashes them, and REFUSES when:

  · a build name survived (`Zaelar.zip`, `zaelar-daemon.exe`, `SHA256SUMS`) — the rename did not run, and a manifest
    naming those files would point the updater at assets the release does not contain;
  · an asset's digest disagrees with the `SHA256SUMS-<suffix>` its job published — two records of one file that
    disagree mean one of them is about other bytes, and the manifest must never be the one that is wrong.

A platform whose build did not produce its asset is left OUT of the manifest (and said so) rather than failing the
release: an Intel build that failed must not stop Apple Silicon users from updating.

The `build` is the engine's `update/BUILD` at this commit (V2-553), so the number in the manifest, the number the
packaged daemon reports in `/health.update.current` and the number the engine shows are one number.

Signing is the workflow's NEXT step (`minisign -S`, with a key that never touches this repository). Without the key
the manifest is still published, unsigned — and every client refuses it. That is correct: an update nobody signed
is not an update.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import struct
import sys
import zipfile
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ENGINE))

from daemon.update import MIN_ENGINE_BUILD  # noqa: E402 — the shared shape, stdlib only
from daemon.update import manifest as shape  # noqa: E402

_BUILD_NAMES = ("Zaelar.zip", "zaelar-daemon", "zaelar-daemon.exe", "zaelar-daemon.pyz", "SHA256SUMS")


class ManifestRefused(SystemExit):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _version() -> str:
    for line in (ENGINE / "daemon" / "__init__.py").read_text(encoding="utf-8").splitlines():
        if line.startswith("VERSION"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise ManifestRefused("daemon/__init__.py has no VERSION line")


def _engine_build() -> int:
    try:
        return int((ENGINE / "update" / "BUILD").read_text(encoding="utf-8").strip())
    except (OSError, ValueError) as e:
        raise ManifestRefused("update/BUILD is missing or not a number") from e


def _sums(directory: Path, suffix: str) -> dict[str, str]:
    path = directory / f"SHA256SUMS-{suffix}"
    if not path.is_file():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) == 2:
            out[parts[1]] = parts[0]
    return out


def _unreadable(path: Path, e: Exception) -> bool:
    """Said in the job's log, then `False`: an asset whose signature could not be READ is published as unsigned —
    the screen then keeps the warning, which is the safe side — and the log says why."""
    print(f"  {path.name}: signature not readable ({type(e).__name__}: {e}) — marked unsigned", file=sys.stderr)
    return False


def _stapled_app(path: Path) -> bool:
    """A notarized, STAPLED Zaelar.app carries its ticket at `Zaelar.app/Contents/CodeResources` — a file an ad hoc
    build never has (its seal is `_CodeSignature/CodeResources`). Read from the zip that is published, so the flag is
    about these bytes, not about which workflow step was believed to run."""
    try:
        with zipfile.ZipFile(path) as zf:
            return any(n.endswith("Zaelar.app/Contents/CodeResources") for n in zf.namelist())
    except (OSError, zipfile.BadZipFile) as e:
        return _unreadable(path, e)


def _authenticode(path: Path) -> bool:
    """A PE carries an Authenticode signature when its certificate-table directory entry (data directory 4) is not
    empty. Pure header arithmetic — the manifest job runs on Linux, where no Windows tool is."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(4096)
    except OSError as e:
        return _unreadable(path, e)
    try:
        if head[:2] != b"MZ":
            return False
        pe = struct.unpack_from("<I", head, 0x3C)[0]
        if head[pe:pe + 4] != b"PE\0\0":
            return False
        optional = pe + 24
        magic = struct.unpack_from("<H", head, optional)[0]
        directories = optional + (96 if magic == 0x10B else 112)      # PE32 / PE32+
        size = struct.unpack_from("<I", head, directories + 4 * 8 + 4)[0]
    except struct.error as e:
        return _unreadable(path, e)
    return size > 0


def _signed(key: str, path: Path, directory: Path) -> bool | None:
    """Whether the publisher's OPERATING-SYSTEM identity is on this platform's asset (V2-869 §5): Developer ID +
    notarization on a Mac build, Authenticode on Windows; `None` for the portable `.pyz`, which has no such signature
    (and so no field). The engine's download screen reads it to drop the "your system will ask you to allow it"
    line; the updater trusts the minisign signature and the digest, never this flag."""
    if path.suffix == ".zip":
        package = shape.INSTALLERS.get(key, ("",))[0]
        return _stapled_app(path) or bool(package and (directory / package).is_file())
    if path.suffix == ".exe":
        return _authenticode(path)
    return None


def build_manifest(directory: Path, tag: str, published_at: str | None = None, next_key: str | None = None,
                   build: int | None = None, version: str | None = None) -> dict:
    stale = [n for n in _BUILD_NAMES if (directory / n).exists()]
    if stale:
        raise ManifestRefused(f"build names survived the rename: {', '.join(stale)} — run release_names.py first")
    platforms: dict[str, dict] = {}
    for key, (asset, suffix) in shape.PLATFORMS.items():
        path = directory / asset
        if not path.is_file():
            print(f"  {key}: {asset} not built — left out of the manifest", file=sys.stderr)
            continue
        digest = _sha256(path)
        listed = _sums(directory, suffix).get(asset)
        if listed is None:
            raise ManifestRefused(f"{asset} is not listed in SHA256SUMS-{suffix}")
        if listed != digest:
            raise ManifestRefused(f"{asset}: SHA256SUMS-{suffix} says {listed}, the file hashes to {digest}")
        platforms[key] = {"asset": asset, "sha256": digest, "size": path.stat().st_size}
        signed = _signed(key, path, directory)
        if signed is not None:
            platforms[key]["signed"] = signed
    if not platforms:
        raise ManifestRefused("no platform asset found — nothing to describe")
    installers: dict[str, dict] = {}
    for key, (asset, suffix) in shape.INSTALLERS.items():
        path = directory / asset
        if path.is_file():
            digest = _sha256(path)
            if _sums(directory, suffix).get(asset) != digest:
                raise ManifestRefused(f"{asset} does not match SHA256SUMS-{suffix}")
            installers[key] = {"asset": asset, "sha256": digest, "size": path.stat().st_size}
    out = {
        "product": shape.PRODUCT,
        "version": version or _version(),
        "build": _engine_build() if build is None else build,
        "tag": tag,
        "published_at": published_at or _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "min_engine_build": MIN_ENGINE_BUILD,
        "platforms": platforms,
        "next_key": next_key,
    }
    if installers:
        out["installers"] = installers
    return out


def write(directory: Path, tag: str, **kw) -> Path:
    data = build_manifest(directory, tag, **kw)
    # Round-trip through the CLIENT's parser: a manifest the updater would refuse is a release bug, caught here.
    text = json.dumps(data, indent=1, sort_keys=True) + "\n"
    shape.parse(text.encode("utf-8"))
    target = directory / shape.MANIFEST_NAME
    target.write_text(text, encoding="utf-8", newline="\n")
    for stale_sig in (directory / shape.SIGNATURE_NAME,):
        if stale_sig.exists():
            stale_sig.unlink()   # a signature is about the bytes it was made over; these are new bytes
    return target


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Write the daemon's update-manifest.json.")
    parser.add_argument("directory", type=Path)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--next-key", default=None, help="a minisign public key for the NEXT releases (rotation)")
    args = parser.parse_args(argv[1:])
    target = write(args.directory, args.tag.strip(), next_key=args.next_key or None)
    data = json.loads(target.read_text(encoding="utf-8"))
    print(f"{target.name}: {data['product']} {data['version']} build {data['build']} tag {data['tag']}")
    for key, entry in data["platforms"].items():
        mark = "" if "signed" not in entry else ("  signed" if entry["signed"] else "  unsigned")
        print(f"  {key:13} {entry['asset']}  {entry['size']:,} bytes  {entry['sha256'][:16]}…{mark}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
