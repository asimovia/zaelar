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
import sys
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
        print(f"  {key:13} {entry['asset']}  {entry['size']:,} bytes  {entry['sha256'][:16]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
