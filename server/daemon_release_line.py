"""Which release the 🖥 screen links the daemon's files from — the daemon's OWN release line first (V2-869 §5).

The SAME rule as `daemon/update/release_line.py`, copied on purpose: the engine never imports `daemon/` (it is not in
the cloud image, and an import would crash-loop the Machine at boot — `test_the_boot_knows_about_the_daemon.py`), and
the daemon never imports the engine (it is packaged alone). The two copies are held equal by node 7.129, which runs
every case against both and fails when their code differs. The rule:

  1. among the `daemon-vX.Y.Z` releases that carry the file, the newest by VERSION; drafts, prereleases and tags that
     are not exactly `daemon-vX.Y.Z` are not candidates;
  2. only when no daemon release carries it, the newest release of any kind that does, newest-first.

The daemon tags come from `git/matching-refs/tags/daemon-v`, so no daemon release sinks below the listing's first page.
"""
from __future__ import annotations

import json
import re
from typing import Callable

DAEMON_TAG = re.compile(r"^daemon-v(\d+)\.(\d+)\.(\d+)$")
_MAX_TAGS_TRIED = 5     # newest first; a daemon release without this file is rare, five in a row is a broken line


def version(tag: str) -> tuple[int, int, int] | None:
    m = DAEMON_TAG.match(tag or "")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def asset_url(release: dict, asset: str) -> str | None:
    for a in release.get("assets") or []:
        if isinstance(a, dict) and a.get("name") == asset:
            url = a.get("browser_download_url")
            return url if isinstance(url, str) and url.startswith("https://") else None
    return None


def _published(release) -> bool:
    return isinstance(release, dict) and not release.get("draft") and not release.get("prerelease")


def choose(releases: list, asset: str) -> dict | None:
    """The release `asset` is taken from, out of a releases listing in the API's newest-first order."""
    carrying = [r for r in releases if _published(r) and asset_url(r, asset)] if isinstance(releases, list) else []
    daemon = [r for r in carrying if version(str(r.get("tag_name") or ""))]
    if daemon:
        return max(daemon, key=lambda r: version(str(r.get("tag_name"))))
    return carrying[0] if carrying else None


def daemon_tags(refs: list) -> list[str]:
    """`daemon-vX.Y.Z` tags from a `git/matching-refs` answer, newest version first."""
    tags = [str(r.get("ref") or "").removeprefix("refs/tags/") for r in refs if isinstance(r, dict)] \
        if isinstance(refs, list) else []
    return sorted((t for t in tags if version(t)), key=version, reverse=True)


def resolve(fetch: Callable[[str], bytes], repo: str, asset: str) -> dict | None:
    """The release to take `asset` from, asking GitHub. `fetch(url) -> bytes` raises on a failed request."""
    api = f"https://api.github.com/repos/{repo}"
    try:
        tags = daemon_tags(json.loads(fetch(f"{api}/git/matching-refs/tags/daemon-v").decode("utf-8")))
    except Exception:   # noqa: BLE001 — no tag listing (rate limit, fork without tags): the listing below decides
        tags = []
    for tag in tags[:_MAX_TAGS_TRIED]:
        try:
            release = json.loads(fetch(f"{api}/releases/tags/{tag}").decode("utf-8"))
        except Exception:   # noqa: BLE001 — a tag without a published release (yet): the next one
            continue
        if _published(release) and asset_url(release, asset):
            return release
    return choose(json.loads(fetch(f"{api}/releases?per_page=100").decode("utf-8")), asset)
