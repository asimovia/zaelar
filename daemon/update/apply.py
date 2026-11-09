"""Download a verified release's asset for THIS platform, verify it again, and swap it in — or leave everything as it was.

THE ORDER IS THE SAFETY:
    1. download to the updater's own staging folder (never next to the installed program);
    2. size and sha256 against the SIGNED manifest — a mismatch deletes the download and ends in `failed`;
    3. when `cosign` is on PATH: the Sigstore bundle over `SHA256SUMS-<suffix>` against the release workflow's
       identity, and the asset's line in those sums — the same check `get.sh` makes (optional: the manifest
       signature already pins the bytes; this is a second, independent publisher check);
    4. `ready`. The swap happens later (`install()`), and re-hashes the staged file first: a file that changed while
       it waited is not the file that was verified.
    5. the swap itself, per OS, written so that a failure half-way puts the old program back.

THE SWAP, PER OS — and why each is the shape it is:

  macOS (`Zaelar.app`)  extract the zip with `ditto` beside the installed bundle, check the NEW bundle's code
      signature (`codesign --verify --deep --strict`) and — when the installed app carries a Developer ID team — that
      the new one is signed by the SAME team; then exchange the two directories in ONE atomic call
      (`renamex_np(RENAME_SWAP)`; two renames with rollback where it is unavailable). The running process keeps its
      already-mapped files; `launchctl kickstart -k gui/<uid>/com.zaelar.daemon` restarts it on the new bundle.
  Windows (`zaelar-daemon.exe`)  a running .exe cannot be overwritten but CAN be renamed, so: copy the new one in as
      `zaelar-daemon.new.exe`, rename the running one to `zaelar-daemon.old.exe`, rename the new one into place (if
      that fails, the old one is renamed back). Then a detached `cmd` waits two seconds and starts the program again
      while this process exits; the leftover `.old.exe` is deleted by the next check. Chosen over "swap on next start
      via the scheduled task" because the Startup-folder fallback of `install.ps1` has no launcher to run a swap, and
      a rename works the same under both.
  `.pyz` (any OS)  `os.replace` of the archive, atomic on every OS; restarted by launchd on macOS, by the same
      detached `cmd` on Windows, and by the person elsewhere (no service manager is assumed on Linux).

A daemon run from a SOURCE TREE has nothing to swap: it updates with git, and `installed_target()` is None.
"""
from __future__ import annotations

import ctypes
import hashlib
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from . import manifest, repo
from .state import STORE, Store

LABEL = "com.zaelar.daemon"
SIGNER_RE = r"^https://github.com/asimovia/zaelar/\.github/workflows/daemon-artifacts\.yml@refs/tags/"
OIDC_ISSUER = "https://token.actions.githubusercontent.com"
_CHUNK = 1024 * 1024


class VerificationError(Exception):
    """The downloaded bytes are not the ones the signed manifest names."""


@dataclass(frozen=True)
class Target:
    kind: str          # "macos-app" | "windows-exe" | "pyz"
    path: Path         # what gets replaced: the .app directory, the .exe, the .pyz
    platform: str      # the manifest's platform key


def platform_key() -> str | None:
    if sys.platform == "darwin":
        import platform as _platform   # noqa: PLC0415
        return "macos-x86_64" if _platform.machine() == "x86_64" else "macos"
    if sys.platform == "win32":
        return "windows"
    return None


def installed_target() -> Target | None:
    """What this process was started from, if it is an installed artifact the updater may replace."""
    from .. import paths   # noqa: PLC0415
    if paths._REPO_ROOT.is_file():                     # a zipapp: the archive itself
        return Target("pyz", paths._REPO_ROOT, "pyz")
    if not getattr(sys, "frozen", False):
        return None                                    # a source tree updates with git
    exe = Path(sys.executable).resolve()
    if sys.platform == "darwin":
        app = exe.parents[2] if len(exe.parents) > 2 else None
        if app is not None and app.suffix == ".app":
            return Target("macos-app", app, platform_key() or "macos")
        return None                                    # an old onefile build: re-run the installer instead
    if sys.platform == "win32":
        return Target("windows-exe", exe, "windows")
    return None


def busy() -> bool:
    """A sign-in window is open: an automatic restart now would close it under the person."""
    try:
        from ..browser.window import WINDOWS   # noqa: PLC0415
        return bool(WINDOWS.current_task())
    except Exception:   # noqa: BLE001
        return False


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(_CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def stream_to_file(url: str, dest: Path, limit: int, timeout: float = 600.0) -> None:
    """Download `url` to `dest`, refusing more than `limit` bytes. The default file transport; tests inject theirs."""
    import urllib.request   # noqa: PLC0415
    if not url.startswith("https://"):
        raise ValueError(f"refusing a non-https URL: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "zaelar-daemon-update"})
    written = 0
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest, "wb") as out:   # noqa: S310
        for block in iter(lambda: resp.read(_CHUNK), b""):
            written += len(block)
            if written > limit:
                raise VerificationError("the download is larger than the manifest says")
            out.write(block)


def asset_url(tag: str, asset: str) -> str:
    return f"https://github.com/{repo()}/releases/download/{tag}/{asset}"


def _cosign_check(tag: str, platform: str, asset: str, sha: str, fetch, workdir: Path, cosign: str) -> None:
    """The Sigstore check `get.sh` makes, when cosign is installed. A missing bundle is a refusal, like there."""
    suffix = manifest.PLATFORMS[platform][1]
    sums_name = f"SHA256SUMS-{suffix}"
    sums = workdir / "SHA256SUMS"
    bundle = workdir / "SHA256SUMS.sigstore.json"
    sums.write_bytes(fetch(asset_url(tag, sums_name)))
    try:
        bundle.write_bytes(fetch(asset_url(tag, sums_name + ".sigstore.json")))
    except Exception as e:   # noqa: BLE001
        raise VerificationError(f"{tag} publishes no Sigstore bundle for {sums_name}") from e
    signer = (os.getenv("ZAELAR_DAEMON_SIGNER_RE") or "").strip() or SIGNER_RE
    proc = subprocess.run([cosign, "verify-blob", "--bundle", str(bundle), "--certificate-identity-regexp", signer,
                           "--certificate-oidc-issuer", OIDC_ISSUER, str(sums)],
                          capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise VerificationError(f"the Sigstore signature on {sums_name} does not verify")
    listed = {ln.split()[-1]: ln.split()[0] for ln in sums.read_text(encoding="utf-8").splitlines() if ln.strip()}
    if listed.get(asset) != sha:
        raise VerificationError(f"{asset} is not listed with this sha256 in the signed {sums_name}")


def discard_pending(store: Store = STORE) -> None:
    pending = store.snapshot().get("pending") or {}
    path = pending.get("path")
    if path:
        try:
            Path(path).unlink()
        except Exception:   # noqa: BLE001
            pass


def download(parsed: manifest.Manifest, fetch=None, store: Store = STORE, target: Target | None = None,
             fetch_file=stream_to_file, cosign: str | None = "auto") -> dict:
    """idle/failed/ready → downloading → ready (verified) | failed (nothing kept). Returns `{state, error}`."""
    target = target or installed_target()
    if target is None:
        return {"state": store.snapshot()["state"], "error": "",
                "note": "running from source: update it with git"}
    entry = parsed.platforms.get(target.platform)
    if entry is None:
        snap = store.transition("failed", error=f"{parsed.tag} publishes no update for {target.platform}")
        return {"state": snap["state"], "error": snap["error"]}
    if store.snapshot()["state"] == "downloading":
        return {"state": "downloading", "error": ""}   # one download at a time
    discard_pending(store)
    store.transition("downloading", pending=None)
    staging = store.staging()
    dest = staging / f"{parsed.build}-{entry.asset}"
    try:
        fetch_file(asset_url(parsed.tag, entry.asset), dest, entry.size)
        size = dest.stat().st_size
        if size != entry.size:
            raise VerificationError(f"size mismatch: the manifest says {entry.size} bytes, {size} arrived")
        actual = sha256_file(dest)
        if actual != entry.sha256:
            raise VerificationError("sha256 mismatch: the file that arrived is not the file that was signed for")
        cosign_bin = shutil.which("cosign") if cosign == "auto" else cosign
        if cosign_bin:
            if fetch is None:
                from .check import http_get as fetch   # noqa: PLC0415
            _cosign_check(parsed.tag, target.platform, entry.asset, actual, fetch, staging, cosign_bin)
    except Exception as e:   # noqa: BLE001 — every failure: delete what arrived, record why, touch nothing installed
        try:
            dest.unlink()
        except Exception:   # noqa: BLE001
            pass
        reason = str(e) if isinstance(e, VerificationError) else f"download failed ({type(e).__name__})"
        snap = store.transition("failed", error=reason, pending=None)
        return {"state": snap["state"], "error": snap["error"]}
    snap = store.transition("ready", pending={
        "path": str(dest), "sha256": entry.sha256, "size": entry.size, "platform": target.platform,
        "version": parsed.version, "build": parsed.build, "tag": parsed.tag})
    return {"state": snap["state"], "error": ""}


# ── the swap ─────────────────────────────────────────────────────────────────────────────────────────────────

_RENAME_SWAP = 0x00000002


def _atomic_exchange(a: Path, b: Path) -> bool:
    """Exchange two paths in one call (macOS `renamex_np`). False when the call is not available here."""
    if sys.platform != "darwin":
        return False
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        fn = libc.renamex_np
    except (OSError, AttributeError):
        return False
    fn.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
    if fn(os.fsencode(a), os.fsencode(b), _RENAME_SWAP) != 0:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err))
    return True


def _team_id(app: Path) -> str:
    proc = subprocess.run(["codesign", "-dv", "--verbose=2", str(app)], capture_output=True, text=True, timeout=60)
    m = re.search(r"^TeamIdentifier=(\S+)$", proc.stderr, re.M)
    team = m.group(1) if m else ""
    return "" if team == "not" else team   # "TeamIdentifier=not set" on an ad hoc signature


def verify_bundle(new_app: Path, old_app: Path) -> None:
    """The new bundle's own signature must verify; a Developer-ID-signed install only accepts the SAME team."""
    proc = subprocess.run(["codesign", "--verify", "--deep", "--strict", str(new_app)],
                          capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise VerificationError("the new Zaelar.app's code signature does not verify")
    old_team = _team_id(old_app) if old_app.exists() else ""
    if old_team and _team_id(new_app) != old_team:
        raise VerificationError("the new Zaelar.app is not signed by the same developer as the installed one")


def _extract_zip(zip_path: Path, into: Path) -> None:
    subprocess.run(["ditto", "-x", "-k", str(zip_path), str(into)], check=True, capture_output=True, timeout=600)


def swap_macos_app(zip_path: Path, app: Path, extract=_extract_zip, verify=verify_bundle) -> None:
    stage = app.parent / ".Zaelar.app.update"
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True)
    try:
        extract(zip_path, stage)
        new_app = stage / "Zaelar.app"
        if not (new_app / "Contents" / "MacOS" / "zaelar-daemon").is_file():
            raise VerificationError("the update does not contain Zaelar.app")
        verify(new_app, app)
        if not _atomic_exchange(new_app, app):
            previous = stage / "previous.app"
            os.rename(app, previous)
            try:
                os.rename(new_app, app)
            except Exception:
                os.rename(previous, app)
                raise
    finally:
        shutil.rmtree(stage, ignore_errors=True)   # after the exchange it holds the OLD bundle


def swap_file(new: Path, installed: Path) -> None:
    """Windows .exe and .pyz: copy beside, rename the running file aside, rename the new one in (rollback on error)."""
    staged = installed.with_name(installed.stem + ".new" + installed.suffix)
    shutil.copyfile(new, staged)
    if installed.suffix == ".pyz":
        os.chmod(staged, 0o755)
        os.replace(staged, installed)   # atomic on every OS; a running zipapp keeps its open handle
        return
    old = installed.with_name(installed.stem + ".old" + installed.suffix)
    if old.exists():
        try:
            old.unlink()
        except OSError:
            old = installed.with_name(f"{installed.stem}.old-{int(time.time())}{installed.suffix}")
    os.rename(installed, old)
    try:
        os.rename(staged, installed)
    except Exception:
        os.rename(old, installed)
        raise


def relaunch(target: Target) -> str:
    """Start the new program. `launchd` | `self` (this process must exit) | `manual` (the person restarts it)."""
    if sys.platform == "darwin":
        domain = f"gui/{os.getuid()}/{LABEL}"
        if subprocess.run(["launchctl", "print", domain], capture_output=True, timeout=30).returncode == 0:
            # `-k` kills THIS process and starts the job again — on the new bundle.
            subprocess.Popen(["launchctl", "kickstart", "-k", domain], start_new_session=True)   # noqa: S603
            return "launchd"
        return "manual"
    if sys.platform == "win32":
        program = target.path
        if target.kind == "pyz":
            launcher = target.path.with_name("zaelar-daemon.cmd")
            program = launcher if launcher.exists() else target.path
        flags = 0x00000008 | 0x00000200   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(["cmd.exe", "/d", "/c", f'ping -n 3 127.0.0.1 >nul & start "" "{program}"'],   # noqa: S603
                         creationflags=flags, close_fds=True)
        threading.Timer(1.0, os._exit, (0,)).start()
        return "self"
    return "manual"


def install(store: Store = STORE, target: Target | None = None, restart=relaunch, swap_app=swap_macos_app) -> dict:
    """ready → swapped → idle; or → failed with the install untouched. Returns `{state, error, restart}`."""
    target = target or installed_target()
    snap = store.snapshot()
    pending = snap.get("pending") or {}
    if snap["state"] != "ready" or not pending:
        return {"state": snap["state"], "error": "no verified update is waiting", "restart": ""}
    if target is None:
        return {"state": snap["state"], "error": "running from source: update it with git", "restart": ""}
    staged = Path(pending.get("path") or "")
    try:
        if pending.get("platform") != target.platform:
            raise VerificationError("the waiting update is for another platform")
        if not staged.is_file() or sha256_file(staged) != pending.get("sha256"):
            raise VerificationError("the waiting update changed after it was verified")
        if target.kind == "macos-app":
            swap_app(staged, target.path)
        else:
            swap_file(staged, target.path)
    except Exception as e:   # noqa: BLE001 — the swap functions restore the old program before raising
        reason = str(e) if isinstance(e, VerificationError) else f"could not install the update ({type(e).__name__})"
        discard_pending(store)
        snap = store.transition("failed", error=reason, pending=None)
        return {"state": snap["state"], "error": snap["error"], "restart": ""}
    discard_pending(store)
    line = f"installed {pending.get('version')} (build {pending.get('build')})"
    store.transition("idle", pending=None, available=None, last_result=line)
    how = restart(target)
    return {"state": "idle", "error": "", "restart": how, "installed": line}


def cleanup() -> None:
    """Remove what a previous swap left behind (Windows `.old.exe`, an interrupted macOS staging folder)."""
    target = installed_target()
    if target is None:
        return
    if target.kind == "windows-exe":
        for leftover in target.path.parent.glob(target.path.stem + ".old*" + target.path.suffix):
            try:
                leftover.unlink()
            except OSError:
                pass
    elif target.kind == "macos-app":
        shutil.rmtree(target.path.parent / ".Zaelar.app.update", ignore_errors=True)
