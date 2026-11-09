"""Build the artifacts a person installs.

TWO FORMS, because "easy to install" means different things to two different people:

  THE ZIPAPP (`zaelar-daemon.pyz`) is the whole daemon in one file, built by the standard library, with no build
  dependency at all. It needs a Python 3.11+ on the machine — which a developer has and a stranger may not —
  and it is what makes the daemon reproducible: anybody can build the exact artifact we ship, from source, with
  one command and nothing installed.

  THE STANDALONE BUILD bundles the interpreter, so it runs on a machine with no Python at all. That is the one an
  ordinary user gets, and the reason it needs PyInstaller — a BUILD dependency, listed in `requirements-build.txt`.
  It also bundles what `daemon/requirements.txt` lists for the desktop resident: Playwright and its Node driver (so
  the installed daemon can always open a browser window), and the tray's GUI library for that OS. Its shape
  depends on the OS:

    macOS    `Zaelar.app`, ONEDIR, zipped as `Zaelar.zip`. Not onefile: a onefile program unpacks itself into a
             temporary folder on every start, which the hardened runtime and notarization handle badly, and an app
             BUNDLE is what carries an `Info.plist` — the bundle id, `LSUIElement` (menu bar, no Dock icon) and the
             sentences macOS shows when the daemon first reads Documents, Desktop or Downloads
             (`macos/info_plist.py`). The `.app` itself is built OUTSIDE `dist/daemon/` (in `dist/app/`): a release
             attaches every file in that folder, and a bundle is thousands of files.
    Windows  `zaelar-daemon.exe`, ONEFILE, a console program (so `zaelar-daemon status` prints in a terminal); the
             tray hides the console when nobody started it from one.
    Linux    `zaelar-daemon`, ONEFILE, headless.

  The zipapp stays dependency-free and therefore WITHOUT the browser: run with a bare Python it serves files and
  `/health` says `browser.state = "unsupported"`. That is its documented limit, not a bug.

WHY BOTH AND NOT JUST THE SECOND. A build that only works when a third-party tool is installed and working is a
build that stops existing the first time that tool breaks on a new Python. The zipapp is always available, so
there is always a way to ship, and CI can prove the package still assembles even on a runner where PyInstaller
would not.

WHAT THIS DELIBERATELY DOES NOT DO: download anything, sign anything with an identity, or publish anything. The
macOS bundle is sealed AD HOC so it is internally consistent; Developer ID signing, notarization and the `.pkg`
(`macos/sign_and_notarize.sh`), Authenticode, the Sigstore signature over the sums and the signed update manifest
(`update_manifest.py`) are steps of the release WORKFLOW, which holds the identities — never side effects of a build.

    python daemon/packaging/build.py              everything it can build here
    python daemon/packaging/build.py --zipapp     just the portable one
    python daemon/packaging/build.py --standalone just this OS's bundled build (`--onefile` is the old name)
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import platform
import shutil
import subprocess
import sys
import tempfile
import zipapp
from pathlib import Path

PACKAGING = Path(__file__).resolve().parent
DAEMON = PACKAGING.parent
ENGINE = DAEMON.parent
DIST = ENGINE / "dist" / "daemon"
# Where the macOS bundle is assembled: next to DIST, never inside it (see the module docstring).
APP_DIST = ENGINE / "dist" / "app"
APP_NAME = "Zaelar.app"
APP_ZIP = "Zaelar.zip"

# The entry point a zipapp needs at ITS top level. The daemon's own `__main__.py` is one level down, inside the
# package, so the archive gets a two-line shim rather than a copy of anything.
_ZIPAPP_MAIN = '''"""Entry point for the zipapp build. See daemon/packaging/build.py."""
import sys

from daemon.cli import main

raise SystemExit(main(sys.argv))
'''

# Everything under `daemon/` that is not the daemon at run time. Excluded from both artifacts: the build tooling
# has no business inside the thing it builds, and `__pycache__` from the developer's machine is bytes shipped to
# a stranger for no reason.
_EXCLUDE = {"packaging", "__pycache__", ".pytest_cache"}


def _version() -> str:
    """Read the version WITHOUT importing the package, so a build never depends on the daemon importing cleanly
    in whatever environment the build runs in."""
    for line in (DAEMON / "__init__.py").read_text(encoding="utf-8").splitlines():
        if line.startswith("VERSION"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("daemon/__init__.py has no VERSION line")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _stage(into: Path) -> Path:
    """A clean copy of the package, with the build tooling and every cache left behind."""
    package = into / "daemon"
    shutil.copytree(
        DAEMON, package,
        ignore=lambda _dir, names: [n for n in names if n in _EXCLUDE or n.endswith((".pyc", ".pyo"))],
    )
    # The engine's build number (`update/BUILD`, V2-553), stamped INTO the package: an installed daemon has no
    # engine tree beside it, and this integer is what the update manifest and the engine's icon compare.
    engine_build = ENGINE / "update" / "BUILD"
    if engine_build.is_file():
        (package / "update" / "BUILD").write_text(engine_build.read_text(encoding="utf-8").strip() + "\n",
                                                  encoding="utf-8")
    return package


def build_zipapp() -> Path:
    DIST.mkdir(parents=True, exist_ok=True)
    target = DIST / "zaelar-daemon.pyz"
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp)
        _stage(source)
        (source / "__main__.py").write_text(_ZIPAPP_MAIN, encoding="utf-8")
        # `compressed` because the archive travels; the interpreter shebang makes it directly executable on
        # POSIX and is simply ignored on Windows, where it is run as `py zaelar-daemon.pyz`.
        zipapp.create_archive(source, target=target, interpreter="/usr/bin/env python3", compressed=True)
    target.chmod(0o755)
    return target


def _have_pyinstaller() -> bool:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller is not installed: skipping the standalone build.\n"
              "  pip install -r daemon/requirements.txt -r daemon/packaging/requirements-build.txt",
              file=sys.stderr)
        return False
    return True


def _collect_args() -> list[str]:
    """What PyInstaller must carry beyond what its import analysis finds on its own.

    `daemon`: every submodule (several are imported lazily — the tray, the browser — and a build subtly missing one
    fails at run time, on somebody else's computer) and its data (the tray icons). `playwright`: its submodules and
    its `driver/` folder — the Node program and the JavaScript package — which no import statement reveals. When
    Playwright is not installed the build says so and goes on: the result serves files and reports
    `browser.state = "unsupported"`, which is an honest program, just not the desktop one."""
    args = ["--collect-submodules", "daemon", "--collect-data", "daemon"]
    if importlib.util.find_spec("playwright") is not None:
        args += ["--collect-submodules", "playwright", "--collect-data", "playwright"]
    else:
        print("Playwright is not installed: this build cannot open browser windows.", file=sys.stderr)
    return args


def _pyinstaller(source: Path, extra: list[str], distpath: Path) -> None:
    entry = source / "zaelar-daemon-entry.py"
    entry.write_text(_ZIPAPP_MAIN, encoding="utf-8")
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm",
         "--name", "zaelar-daemon",
         "--distpath", str(distpath), "--workpath", str(source / "build"), "--specpath", str(source),
         *_collect_args(), *extra,
         "--paths", str(source),
         str(entry)],
        check=True, cwd=source,
    )


def build_onefile() -> Path | None:
    """The single-file build (Windows, Linux). Returns None — loudly, not silently — when PyInstaller is not here."""
    if not _have_pyinstaller():
        return None
    DIST.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp)
        _stage(source)
        _pyinstaller(source, ["--onefile", "--console"], DIST)
    built = DIST / ("zaelar-daemon.exe" if sys.platform == "win32" else "zaelar-daemon")
    if not built.exists():
        raise SystemExit(f"PyInstaller reported success but {built} is not there")
    return built


def _load_info_plist():
    spec = importlib.util.spec_from_file_location("daemon_info_plist", PACKAGING / "macos" / "info_plist.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_app() -> Path | None:
    """macOS: `dist/app/Zaelar.app` (onedir, windowed, `Info.plist` patched) and `dist/daemon/Zaelar.zip` of it."""
    if not _have_pyinstaller():
        return None
    info_plist = _load_info_plist()
    APP_DIST.mkdir(parents=True, exist_ok=True)
    DIST.mkdir(parents=True, exist_ok=True)
    app = APP_DIST / APP_NAME
    if app.exists():
        shutil.rmtree(app)
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp)
        _stage(source)
        out = source / "out"
        _pyinstaller(source, ["--onedir", "--windowed", "--osx-bundle-identifier", info_plist.BUNDLE_ID], out)
        built = out / "zaelar-daemon.app"
        if not built.is_dir():
            raise SystemExit(f"PyInstaller reported success but {built} is not there")
        shutil.move(str(built), str(app))
    info_plist.apply(app / "Contents" / "Info.plist", _version())
    # PyInstaller signed the bundle AD HOC before the plist was patched, and the plist is part of what a bundle
    # signature seals — so the seal is re-made over the final bytes, still ad hoc. (An identity signature is a later
    # release step with the publisher's certificate; this one only keeps an unsigned build internally consistent.)
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app)], check=True)
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)
    target = DIST / APP_ZIP
    if target.exists():
        target.unlink()
    # `ditto` and not `zipfile`: a PyInstaller bundle is full of symlinks and extended attributes, and `ditto` is
    # the tool macOS (and Apple's notarization service) expects an app archive to have been made with.
    subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(app), str(target)], check=True)
    return target


def build_standalone() -> Path | None:
    return build_app() if sys.platform == "darwin" else build_onefile()


def write_manifest(artifacts: list[Path]) -> Path:
    """What was built, from what, and what it hashes to.

    The checksums are the whole point: this is how an installer, or a person, can tell the file they have is the
    file that was built. It is NOT a signature — a hash beside the download only proves the two agree, and
    whoever can replace one can replace the other. Signing is a release step, done by somebody who has the
    identity to sign with; see the ops playbook."""
    manifest = {
        "product": "zaelar-daemon",
        "version": _version(),
        "built_on": f"{platform.system().lower()}-{platform.machine().lower()}",
        "python": platform.python_version(),
        "artifacts": [
            {"name": a.name, "bytes": a.stat().st_size, "sha256": _sha256(a)} for a in artifacts
        ],
    }
    target = DIST / "manifest.json"
    target.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (DIST / "SHA256SUMS").write_text(
        "".join(f"{_sha256(a)}  {a.name}\n" for a in artifacts), encoding="utf-8")
    return target


def main(argv: list[str]) -> int:
    # ⚠️ WINDOWS CONSOLES ARE NOT UTF-8, and this cost a whole build. A Windows runner's stdout defaults to
    # cp1252, so the "→" in the success line below raised UnicodeEncodeError — AFTER every artifact had been
    # written. The build worked; the script died formatting its own report, and CI called it a failed build.
    # Measured on windows-latest, 2026-09-14. Reconfiguring covers every future print rather than this one
    # character, and `errors="replace"` means a console that still cannot render something prints a box
    # instead of throwing away the build.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:       # noqa: BLE001 — a stream that cannot be reconfigured is not a reason not to build
            pass
    parser = argparse.ArgumentParser(description="Build the zaelar-daemon artifacts.")
    parser.add_argument("--zipapp", action="store_true", help="only the portable, dependency-free build")
    parser.add_argument("--standalone", "--onefile", dest="standalone", action="store_true",
                        help="only this OS's bundled-interpreter build (Zaelar.app on macOS, onefile elsewhere)")
    args = parser.parse_args(argv[1:])
    both = not (args.zipapp or args.standalone)

    artifacts: list[Path] = []
    if both or args.zipapp:
        artifacts.append(build_zipapp())
    if both or args.standalone:
        one = build_standalone()
        if one:
            artifacts.append(one)
        elif args.standalone:
            return 1

    if not artifacts:
        return 1
    manifest = write_manifest(artifacts)
    print(f"\nzaelar-daemon {_version()} → {DIST}")
    for artifact in artifacts:
        print(f"  {artifact.name}  {artifact.stat().st_size:,} bytes")
    print(f"  {manifest.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
