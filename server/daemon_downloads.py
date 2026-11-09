"""Where a user gets the daemon's installer, and which one to put in front of him first (from
`server/daemon_api.py`, refactor2710-13 T-03). `daemon_api` imports them back."""
import os
import sys

from fastapi import Request

# Where a user gets the installer: the newest release's own files. The daemon is rebuilt and attached on every
# engine tag (`.github/workflows/daemon-artifacts.yml` runs on `v*`), so `releases/latest/download/<file>` is
# the newest build. It used to be pinned to a `daemon-v<version>` tag, and that pin went stale silently: the
# version number did not move while the daemon's code did, so the screen kept handing out a months-old build.
# The one-line command (the main path) resolves the newest release that carries the file and never 404s; these
# links are the fallback for somebody who would rather see the file first.
_RELEASE_BASE_DEFAULT = "https://github.com/asimovia/zaelar/releases/latest/download"

_ASSETS = {
    "macos": {"artifact": "zaelar-daemon-macos", "installer": "zaelar-daemon-install-macos.sh",
              "checksums": "SHA256SUMS-macos"},
    "windows": {"artifact": "zaelar-daemon-windows.exe", "installer": "zaelar-daemon-install-windows.ps1",
                "checksums": "SHA256SUMS-windows"},
}

# ⚠️ THE ONE-LINE COMMAND IS THE MAIN PATH, and it is not a convenience for people who like terminals. macOS
# quarantine and the Windows Mark of the Web are written by whatever SAVED the file — a browser stamps it,
# `curl` and `Invoke-WebRequest` do not. So a daemon that arrives this way is never held by Gatekeeper and
# never raises the SmartScreen panel, on unsigned artifacts, with no Apple or Microsoft account and nothing to
# renew. The download buttons stay as a fallback for somebody who would rather see the file, and they are the
# ones that cost a security dialog.
#
# ⚠️ AND THE ARCHITECTURE PROBLEM IS WHY A BUTTON CANNOT BE THE MAIN PATH. Apple Silicon and Intel need
# different binaries, a user-agent does not reliably say which, and picking wrong fails with "bad CPU type in
# executable". The script reads `uname -m` and is simply right.
_BOOTSTRAP_BASE_DEFAULT = "https://raw.githubusercontent.com/asimovia/zaelar/main/daemon/packaging"

_BOOTSTRAP = {
    "macos": {"script": "get.sh", "command": "curl -fsSL {base}/get.sh | bash"},
    "windows": {"script": "get.ps1", "command": "irm {base}/get.ps1 | iex"},
}


def _downloads(version: str) -> dict:
    base = (os.getenv("ZAELAR_DAEMON_DOWNLOAD_BASE") or "").strip().rstrip("/")
    tag = "latest"
    if not base:
        base = _RELEASE_BASE_DEFAULT
    boot = (os.getenv("ZAELAR_DAEMON_BOOTSTRAP_BASE") or _BOOTSTRAP_BASE_DEFAULT).rstrip("/")
    out: dict = {"tag": tag, "platforms": {}}
    if not base:
        return out
    for name, assets in _ASSETS.items():
        entry = {key: f"{base}/{filename}" for key, filename in assets.items()}
        entry["bootstrap"] = f"{boot}/{_BOOTSTRAP[name]['script']}"
        entry["command"] = _BOOTSTRAP[name]["command"].format(base=boot)
        out["platforms"][name] = entry
    return out


def _guess_platform(request: Request) -> str:
    """Which installer to put in front of this person first. The client's own user-agent, because the ENGINE's
    platform is the wrong answer on a cloud account (a Linux container) and on a self-hoster browsing from a
    second machine."""
    agent = (request.headers.get("user-agent") or "").lower()
    if "windows" in agent:
        return "windows"
    if "mac" in agent or "darwin" in agent:
        return "macos"
    if not agent:
        return "windows" if os.name == "nt" else ("macos" if sys.platform == "darwin" else "")
    return ""
