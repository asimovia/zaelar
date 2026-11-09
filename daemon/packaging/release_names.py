"""Give a build's files the names the RELEASE publishes them under (V2-575 · P4).

WHY THIS IS A SCRIPT AND NOT THREE LINES OF SHELL. Three build jobs — Apple Silicon, Intel, Windows — upload
into one flattened release, and every one of them produces `zaelar-daemon`, `zaelar-daemon.pyz`,
`manifest.json` and `SHA256SUMS` under those exact names. Whoever uploaded last used to win. So each job
renames its own output with its architecture's suffix before uploading, and that rename has to happen
identically on bash and on PowerShell, which is exactly the kind of thing that drifts between two copies.

⚠️ AND THE RENAME IS NOT JUST A RENAME. `build.py` writes `SHA256SUMS` listing the files by their BUILD names,
so renaming the files alone leaves a checksum file that names things the release does not contain — published,
correct-looking, and useless for the one job it has. Measured 2026-09-15: the first release shipped exactly
that, and the one-line installer refused to install because it could not find its own artifact in the sums.
The digests are recomputed here from the files as they will actually be published.

    python daemon/packaging/release_names.py macos
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

DIST = Path(__file__).resolve().parent.parent.parent / "dist" / "daemon"

# Build name → the template its published name follows. `.exe` keeps its extension because Windows needs it to
# run the file at all, so the suffix goes before it rather than after.
_RENAMES = (
    ("zaelar-daemon", "zaelar-daemon-{suffix}"),
    ("zaelar-daemon.exe", "zaelar-daemon-{suffix}.exe"),
    ("zaelar-daemon.pyz", "zaelar-daemon-{suffix}.pyz"),
    ("manifest.json", "manifest-{suffix}.json"),
)

# The checksum file the release publishes, and the Sigstore bundle the workflow signs it into. Named here, once,
# because three places must agree on them: the workflow signs `SUMS_TEMPLATE`, writes `SIGNATURE_TEMPLATE`, and
# both installers download the pair under these names (node 7.99 joins all three).
SUMS_TEMPLATE = "SHA256SUMS-{suffix}"
SIGNATURE_TEMPLATE = SUMS_TEMPLATE + ".sigstore.json"

# Every shape a signature over a sums file has had or could have: a bundle, or a detached `.sig` + `.pem` pair.
_SIGNATURE_SUFFIXES = (".sigstore.json", ".sigstore", ".bundle", ".sig", ".pem")


def _stale_signatures(dist: Path) -> list[Path]:
    return [f for f in dist.glob("SHA256SUMS*") if f.name.endswith(_SIGNATURE_SUFFIXES)]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rename_for(suffix: str, dist: Path | None = None) -> list[Path]:
    """Rename everything in `dist` for `suffix`, then rewrite the checksums and the manifest to match.

    Returns the artifacts (binary and archive) under their published names."""
    dist = dist or DIST
    # ⚠️ A SIGNATURE IS ABOUT THE BYTES IT WAS MADE OVER. The sums are rewritten below, so any signature already in
    # `dist` — from an earlier build, an earlier name, a re-run — now vouches for a file that no longer exists,
    # and published beside the new sums it would read as "signed" while verifying nothing (or failing on every
    # user's machine). Signing is the workflow's NEXT step, over what this function writes; nothing older survives.
    for stale in _stale_signatures(dist):
        stale.unlink()
    # Windows names its binary `zaelar-daemon.exe`; a suffix that already carries `.exe` would double it.
    published: list[Path] = []
    for build_name, template in _RENAMES:
        source = dist / build_name
        if not source.exists():
            continue
        target = dist / template.format(suffix=suffix)
        source.replace(target)
        if not target.name.startswith("manifest"):
            published.append(target)

    # The checksums are RECOMPUTED, not rewritten by text substitution: a sums file whose names were patched
    # but whose digests came from somewhere else would be the same lie in a more convincing format.
    sums = dist / SUMS_TEMPLATE.format(suffix=suffix)
    # ⚠️ `newline="\n"`, because this runs on Windows too, where text mode writes CRLF: every name in the sums then
    # ends in `\r`, and `shasum -c` / `sha256sum -c` on any other machine report the files as missing — a
    # third party could not check a Windows build at all (measured on the published SHA256SUMS-windows).
    sums.write_text("".join(f"{_sha256(a)}  {a.name}\n" for a in sorted(published)), encoding="utf-8",
                    newline="\n")
    old_sums = dist / "SHA256SUMS"
    if old_sums.exists():
        old_sums.unlink()

    manifest_path = dist / f"manifest-{suffix}.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["platform_suffix"] = suffix
            manifest["artifacts"] = [
                {"name": a.name, "bytes": a.stat().st_size, "sha256": _sha256(a)} for a in sorted(published)
            ]
            manifest_path.write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8", newline="\n")
        except Exception:       # noqa: BLE001 — the manifest is informational; the sums are the control
            pass
    return published


def main(argv: list[str]) -> int:
    if len(argv) != 2 or not argv[1].strip():
        print("usage: release_names.py <suffix>", file=sys.stderr)
        return 2
    published = rename_for(argv[1].strip())
    if not published:
        print(f"nothing to rename in {DIST}", file=sys.stderr)
        return 1
    for artifact in published:
        print(f"  {artifact.name}  {artifact.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
