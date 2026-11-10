"""The Developer ID path is exercised WITHOUT Apple (V2-869 §5): `sign_and_notarize.sh --dry-run sign` walks a real
bundle and prints every command it would run, and that plan is pinned here.

  · the order: import (throwaway keychain, unlocked, partition list) → sign → verify → notarize → staple → assess
    → [package];
  · INSIDE-OUT: every Mach-O before the bundle that contains it, the framework before the app, the app last; text
    files and the `Resources/Python.framework` SYMLINK never signed; never `--deep` to sign;
  · hardened runtime + secure timestamp on every signature, and entitlements ONLY on the bundled Node (allow-jit —
    measured, see the script's header);
  · what is assessed is the PUBLISHED zip, extracted: codesign --strict, stapler validate, spctl;
  · the Installer identity is optional: without it no `.pkg` phase, with it a package that is notarized, stapled and
    assessed as an install;
  · a dry run prints no secret, and a real run without one dies naming it.

Disarms (seen red 2026-11-10): `deepest_first` replaced by a plain `sort` (spelling order) → the framework is sealed
before the helper app inside it and the inside-out test fails; `--entitlements` given to every file → the
entitlements test fails.
"""
from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[4]
SCRIPT = ENGINE / "daemon" / "packaging" / "macos" / "sign_and_notarize.sh"

pytestmark = pytest.mark.skipif(sys.platform != "darwin" or not shutil.which("plutil"),
                                reason="the signing script reads Info.plist with macOS plutil")

SECRETS = {"APPLE_DEVID_APP_P12": "QVBQUDEy", "APPLE_DEVID_APP_P12_PASSWORD": "app-pass-0451",
           "NOTARY_KEY_P8": "notary-key-0451", "NOTARY_KEY_ID": "KEYID0451", "NOTARY_ISSUER": "issuer-0451",
           "APPLE_TEAM_ID": "TEAM0451"}
INSTALLER = {"APPLE_DEVID_INSTALLER_P12": "SU5TVA==", "APPLE_DEVID_INSTALLER_P12_PASSWORD": "inst-pass-0451"}


def _macho(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy("/bin/echo", path)       # any real Mach-O; `file` must call it one
    path.chmod(0o755)


def _app(tmp: Path) -> Path:
    app = tmp / "Zaelar.app"
    c = app / "Contents"
    _macho(c / "MacOS" / "zaelar-daemon")
    _macho(c / "Frameworks" / "Python.framework" / "Versions" / "3.12" / "Python")
    # python.org builds carry a helper app INSIDE the framework: a bundle in a bundle, which must be sealed first.
    _macho(c / "Frameworks" / "Python.framework" / "Versions" / "3.12" / "Resources" / "Python.app" / "Contents"
           / "MacOS" / "Python")
    _macho(c / "Frameworks" / "lib-dynload" / "_ssl.so")
    _macho(c / "Frameworks" / "libssl.3.dylib")
    _macho(c / "Frameworks" / "playwright" / "driver" / "node")
    (c / "Frameworks" / "base_library.zip").write_bytes(b"PK\x05\x06" + b"\0" * 18)
    (c / "Resources").mkdir()
    (c / "Resources" / "Python.framework").symlink_to("../Frameworks/Python.framework")
    with open(c / "Info.plist", "wb") as fh:
        plistlib.dump({"CFBundleExecutable": "zaelar-daemon", "CFBundleIdentifier": "com.zaelar.daemon",
                       "CFBundleShortVersionString": "0.2.2"}, fh)
    return app


def _plan(tmp_path: Path, env_extra: dict) -> tuple[list[str], str]:
    app = _app(tmp_path)
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "TMPDIR": str(tmp_path), **env_extra}
    out = subprocess.run(["bash", str(SCRIPT), "--dry-run", "sign", str(app), str(tmp_path / "dist"), "macos"],
                         capture_output=True, text=True, timeout=60, env=env)
    assert out.returncode == 0, out.stderr
    return out.stdout.splitlines(), out.stdout


def _at(lines: list[str], pred, what: str) -> int:
    for i, line in enumerate(lines):
        if pred(line):
            return i
    raise AssertionError(f"the plan has no line that {what}")


def _signs(lines: list[str]) -> list[tuple[int, str, str]]:
    """(index, path, line) of every SIGNING codesign line (verification lines carry --verify)."""
    out = []
    for i, line in enumerate(lines):
        if line.startswith("+ codesign ") and "--verify" not in line:
            out.append((i, line.rsplit(" ", 1)[1], line))
    return out


def test_the_phases_run_in_order_import_sign_verify_notarize_staple_assess(tmp_path):
    lines, _ = _plan(tmp_path, {})
    phases = [l[3:] for l in lines if l.startswith("== ")]
    assert phases == ["import", "sign", "verify", "notarize notarize.zip", "staple", "assess"], phases
    imp = lines.index("== import")
    for needle in ("security create-keychain", "security unlock-keychain", "security import <APPLE_DEVID_APP_P12>",
                   "security set-key-partition-list -S apple-tool:,apple:,codesign:", "security list-keychains"):
        at = _at(lines, lambda l, n=needle: l.startswith("+ " + n), f"runs {needle}")
        assert imp < at < lines.index("== sign"), needle
    sub = _at(lines, lambda l: "notarytool submit" in l and "--wait" in l, "submits with --wait")
    staple = _at(lines, lambda l: l == f"+ xcrun stapler staple {tmp_path}/Zaelar.app", "staples the app")
    rezip = _at(lines, lambda l: l.startswith("+ ditto -c -k") and "--keepParent" in l and l.endswith("dist/Zaelar.zip"),
                "re-zips the stapled app")
    assert sub < staple < rezip


def test_every_binary_is_signed_inside_out_and_the_app_last(tmp_path):
    lines, _ = _plan(tmp_path, {})
    signed = _signs(lines)
    paths = [p for _, p, _ in signed]
    app = str(tmp_path / "Zaelar.app")
    assert paths[-1] == app, "the app is sealed last"
    fw = f"{app}/Contents/Frameworks/Python.framework"
    helper = f"{fw}/Versions/3.12/Resources/Python.app"
    assert paths.index(f"{helper}/Contents/MacOS/Python") < paths.index(helper) < paths.index(fw) < paths.index(app)
    assert paths.index(f"{fw}/Versions/3.12/Python") < paths.index(fw)
    bundles = [p for p in paths if p.endswith((".app", ".framework"))]
    for path in paths:
        for bundle in bundles:
            if path.startswith(bundle + "/"):
                assert paths.index(path) < paths.index(bundle), f"{path} signed after {bundle}, which contains it"
    expected = {f"{app}/Contents/MacOS/zaelar-daemon", f"{fw}/Versions/3.12/Python",
                f"{helper}/Contents/MacOS/Python", helper,
                f"{app}/Contents/Frameworks/lib-dynload/_ssl.so", f"{app}/Contents/Frameworks/libssl.3.dylib",
                f"{app}/Contents/Frameworks/playwright/driver/node", fw, app}
    assert set(paths) == expected and len(paths) == len(expected), "each once; no text file, no symlinked framework"
    for _, _, line in signed:
        assert "--options runtime" in line and "--timestamp" in line and "--force" in line
        assert "--deep" not in line, "never --deep to SIGN"


def test_only_the_bundled_node_gets_entitlements(tmp_path):
    lines, _ = _plan(tmp_path, {})
    with_ent = [p for _, p, line in _signs(lines) if "--entitlements" in line]
    assert [Path(p).name for p in with_ent] == ["node"]
    line = next(line for _, p, line in _signs(lines) if p.endswith("/node"))
    assert line.split("--entitlements ")[1].split(" ")[0].endswith("macos/entitlements-node.plist")
    ent = plistlib.loads((SCRIPT.parent / "entitlements-node.plist").read_bytes())
    assert ent == {"com.apple.security.cs.allow-jit": True}, "measured: allow-jit alone runs the bundled Node"


def test_what_is_assessed_is_the_published_zip_extracted(tmp_path):
    lines, _ = _plan(tmp_path, {})
    rezip = _at(lines, lambda l: l.startswith("+ ditto -c -k") and l.endswith("dist/Zaelar.zip"), "re-zips")
    unzip = _at(lines, lambda l: l.startswith("+ ditto -x -k") and "dist/Zaelar.zip" in l, "extracts the zip")
    got = [l for l in lines[unzip:] if "/received/Zaelar.app" in l]
    assert [l.split(" ")[1] + " " + l.split(" ")[2] for l in got] == \
        ["codesign --verify", "xcrun stapler", "spctl --assess"], got
    assert "--deep --strict" in got[0] and "validate" in got[1] and "--type execute" in got[2]
    assert rezip < unzip


def test_without_the_installer_identity_there_is_no_package(tmp_path):
    lines, text = _plan(tmp_path, {})
    assert "== package" not in lines and "no Installer identity" in text
    assert not [l for l in lines if l.startswith("+ ") and (".pkg" in l or "productbuild" in l or "INSTALLER" in l)]


def test_with_the_installer_identity_the_package_is_signed_notarized_stapled_and_assessed(tmp_path):
    lines, _ = _plan(tmp_path, {**SECRETS, **INSTALLER})
    phases = [l[3:] for l in lines if l.startswith("== ")]
    assert phases[-4:] == ["package", "notarize Zaelar.pkg", "staple package", "assess package"], phases
    assert _at(lines, lambda l: l.startswith("+ security import <APPLE_DEVID_INSTALLER_P12>"), "imports it") \
        < lines.index("== sign")
    pkg = lines.index("== package")
    for needle in ("+ productbuild ", "+ pkgutil --check-signature", "+ xcrun notarytool submit",
                   "+ xcrun stapler staple", "+ xcrun stapler validate", "+ spctl --assess --type install"):
        assert _at(lines[pkg:], lambda l, n=needle: l.startswith(n) and "Zaelar.pkg" in l, f"runs {needle}") >= 0


def test_a_dry_run_prints_no_secret(tmp_path):
    _, text = _plan(tmp_path, {**SECRETS, **INSTALLER})
    for name, value in {**SECRETS, **INSTALLER}.items():
        if name != "APPLE_TEAM_ID":
            assert value not in text, f"{name}'s value is in the plan"


def test_a_real_run_without_a_secret_dies_naming_it(tmp_path):
    app = _app(tmp_path)
    env = {"PATH": "/usr/bin:/bin", "TMPDIR": str(tmp_path), **{k: v for k, v in SECRETS.items() if k != "NOTARY_ISSUER"}}
    out = subprocess.run(["bash", str(SCRIPT), "sign", str(app), str(tmp_path / "dist"), "macos"],
                         capture_output=True, text=True, timeout=60, env=env)
    assert out.returncode != 0 and "NOTARY_ISSUER is not set" in out.stderr
    assert not os.path.exists(tmp_path / "dist" / "Zaelar.zip")
