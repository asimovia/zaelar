"""Where a user gets the daemon's installer, and which one to put in front of him first (from
`server/daemon_api.py`, refactor2710-13 T-03). `daemon_api` imports them back."""
import json
import os
import sys
import threading
import time
import urllib.request

from fastapi import Request

# Where a user gets the installer: the newest release's own files. The daemon is rebuilt and attached on every
# engine tag (`.github/workflows/daemon-artifacts.yml` runs on `v*`), so `releases/latest/download/<file>` is
# the newest build. It used to be pinned to a `daemon-v<version>` tag, and that pin went stale silently: the
# version number did not move while the daemon's code did, so the screen kept handing out a months-old build.
# The one-line command (the main path) resolves the newest release that carries the file and never 404s; these
# links are the fallback for somebody who would rather see the file first.
_RELEASE_BASE_DEFAULT = "https://github.com/asimovia/zaelar/releases/latest/download"

_ASSETS = {
    # macOS ships the `Zaelar.app` bundle, zipped (V2-869); Apple Silicon here, `Zaelar-macos-x86_64.zip` for Intel.
    "macos": {"artifact": "Zaelar-macos.zip", "installer": "zaelar-daemon-install-macos.sh",
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


# ── is the published release signed by the publisher's OS identity? ───────────────────────────────────────────
# The release's `update-manifest.json` says, per platform, whether its asset carries Developer ID + notarization
# (macOS) or Authenticode (Windows) — measured from the published bytes by `daemon/packaging/update_manifest.py`.
# The download screen reads it to drop the "your system will ask you to allow it" line when there is nothing to
# allow. It is read in the BACKGROUND and cached: the icon polls the status every few seconds, and a status that
# waited on GitHub would be a status that hangs offline. Unknown (`None`) until the first read lands, and after a
# failure — the screen then shows the unsigned wording, which is the safe one.
# Not verified with minisign here, on purpose: the flag only chooses a sentence. What the updater INSTALLS is
# checked against the signature and the digest, never against this flag.
_SIGNED_TTL_S = 6 * 3600
_SIGNED_RETRY_S = 15 * 60
_signed_cache: dict = dict(at=0.0, base="", signed={}, busy=False)   # a state record, not a table
_signed_lock = threading.Lock()
LIVE = True     # the suite turns it off (root conftest): a deterministic test never reads GitHub


def _read_signed(base: str) -> dict:
    from connectors import outcome as _outcome

    def fetch() -> dict:
        with urllib.request.urlopen(f"{base}/update-manifest.json", timeout=5) as r:     # noqa: S310 — https base
            return json.loads(r.read(256 * 1024).decode("utf-8"))

    raw = _outcome.call("daemon_release", "update_manifest", fetch, empty=lambda m: not m.get("platforms"))
    out: dict = {}
    for key, entry in (raw.get("platforms") or {}).items():
        if isinstance(entry, dict) and isinstance(entry.get("signed"), bool):
            out[key] = entry["signed"]
    # The `.pkg` exists only when the Installer identity did too: listed under `installers`, never assumed — its
    # name comes from the manifest, so a link never points at a file the release does not carry.
    for key, entry in (raw.get("installers") or {}).items():
        if isinstance(entry, dict) and isinstance(entry.get("asset"), str):
            out["package:" + key] = entry["asset"]
    return out


def _refresh_signed(base: str) -> None:
    try:
        signed, ok = _read_signed(base), True
    except Exception:       # noqa: BLE001 — offline, no release yet, an older manifest: all mean "not known"
        signed, ok = {}, False
    with _signed_lock:
        _signed_cache.update(signed=signed, base=base, busy=False,
                             at=time.time() - (0 if ok else _SIGNED_TTL_S - _SIGNED_RETRY_S))


def _release_signed(base: str) -> dict:
    """{platform: bool, "package:<platform>": asset} from the newest release's manifest, or {} while it is not
    known. Never blocks."""
    with _signed_lock:
        fresh = _signed_cache["base"] == base and time.time() - _signed_cache["at"] < _SIGNED_TTL_S
        if not fresh and LIVE and not _signed_cache["busy"] and base.startswith("https://"):
            _signed_cache["busy"] = True
            threading.Thread(target=_refresh_signed, args=(base,), name="daemon-release-signed", daemon=True).start()
        return dict(_signed_cache["signed"]) if _signed_cache["base"] == base else {}


def _downloads(version: str) -> dict:
    base = (os.getenv("ZAELAR_DAEMON_DOWNLOAD_BASE") or "").strip().rstrip("/")
    tag = "latest"
    if not base:
        base = _RELEASE_BASE_DEFAULT
    boot = (os.getenv("ZAELAR_DAEMON_BOOTSTRAP_BASE") or _BOOTSTRAP_BASE_DEFAULT).rstrip("/")
    out: dict = {"tag": tag, "platforms": {}}
    if not base:
        return out
    signed = _release_signed(base)
    for name, assets in _ASSETS.items():
        entry = {key: f"{base}/{filename}" for key, filename in assets.items()}
        entry["bootstrap"] = f"{boot}/{_BOOTSTRAP[name]['script']}"
        entry["command"] = _BOOTSTRAP[name]["command"].format(base=boot)
        # `true` / `false` from the published release, `null` while not known (the screen then says the unsigned
        # sentence). A signed Mac release also carries the notarized installer package a person double-clicks.
        entry["signed"] = signed.get(name)
        package = signed.get("package:" + name)
        if entry["signed"] and isinstance(package, str) and package.endswith(".pkg") and "/" not in package:
            entry["package"] = f"{base}/{package}"
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
