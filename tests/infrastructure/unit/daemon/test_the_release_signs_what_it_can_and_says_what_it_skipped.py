"""The release pipeline signs the update manifest and the installers the moment the identities exist — and until
then stays green and SAYS what it skipped (V2-869 §4-5).

Pinned:
  · the update manifest's shape, written over the PUBLISHED names (after `release_names.py`), refusing a build name
    that survived the rename and any digest that disagrees with the job's signed sums — and round-tripping through
    the client's own parser;
  · the workflow: a `manifest` job after every build, minisign conditional on MINISIGN_SECRET_KEY with a notice when
    absent, verified with the CLIENT's code and the COMMITTED key; identity signing conditional on its secrets,
    after the smoke tests and before the sums; the "unsigned: identity secrets absent" notice; and the workflow
    references ONLY the secret names agreed with the operator;
  · the installers: every shell script parses; `get.sh` verifies the signed manifest with minisign when installed
    (refusing a bad one, skipping a missing one and saying so) and prefers a notarized `.pkg` the signed sums list;
    `install.sh` hands a `.pkg` to Gatekeeper before using it.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from daemon.update import manifest as shape

ENGINE = Path(__file__).resolve().parents[4]
WORKFLOW = ENGINE / ".github" / "workflows" / "daemon-artifacts.yml"
PACKAGING = ENGINE / "daemon" / "packaging"

APPLE_SECRETS = {"APPLE_DEVID_APP_P12", "APPLE_DEVID_APP_P12_PASSWORD", "APPLE_DEVID_INSTALLER_P12",
                 "APPLE_DEVID_INSTALLER_P12_PASSWORD", "NOTARY_KEY_P8", "NOTARY_KEY_ID", "NOTARY_ISSUER",
                 "APPLE_TEAM_ID"}
WINDOWS_SECRETS = {"AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "ARTIFACT_SIGNING_ENDPOINT",
                   "ARTIFACT_SIGNING_ACCOUNT", "ARTIFACT_SIGNING_PROFILE"}
MINISIGN_SECRETS = {"MINISIGN_SECRET_KEY", "MINISIGN_PASSWORD"}


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, PACKAGING / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


# ── the manifest writer ───────────────────────────────────────────────────────────────────────────────────────

def _built(dist: Path) -> None:
    """What the three build jobs leave under their BUILD names, before `release_names.py`."""
    dist.mkdir(parents=True)
    (dist / "Zaelar.zip").write_bytes(b"mac app")
    (dist / "zaelar-daemon.pyz").write_bytes(b"portable")
    (dist / "manifest.json").write_text("{}", encoding="utf-8")
    (dist / "SHA256SUMS").write_text("stale  Zaelar.zip\n", encoding="utf-8")


def test_the_manifest_is_written_over_the_published_names_and_parses(tmp_path):
    names = _load("rn_upd", "release_names.py")
    writer = _load("um_upd", "update_manifest.py")
    mac, win = tmp_path / "mac", tmp_path / "win"
    _built(mac)
    names.rename_for("macos", mac)
    win.mkdir()
    (win / "zaelar-daemon.exe").write_bytes(b"windows exe")
    names.rename_for("windows", win)
    release = tmp_path / "release"          # the manifest job's flattened download
    release.mkdir()
    for d in (mac, win):
        for f in d.iterdir():
            shutil.copy(f, release / f.name)

    target = writer.write(release, "v3.140")
    data = json.loads(target.read_text(encoding="utf-8"))
    assert set(data) == {"product", "version", "build", "tag", "published_at", "min_engine_build", "platforms",
                         "next_key"}
    assert data["tag"] == "v3.140" and data["next_key"] is None
    assert data["build"] == int((ENGINE / "update" / "BUILD").read_text().strip()), "aligned with update/BUILD"
    assert set(data["platforms"]) == {"macos", "windows", "pyz"}, "the Intel build did not run: left out, not fatal"
    for key, entry in data["platforms"].items():
        blob = (release / entry["asset"]).read_bytes()
        assert entry == {"asset": shape.PLATFORMS[key][0], "sha256": hashlib.sha256(blob).hexdigest(),
                         "size": len(blob)}
    parsed = shape.parse(target.read_bytes())
    assert parsed.platforms["windows"].asset == "zaelar-daemon-windows.exe"


def test_the_manifest_refuses_files_that_were_not_renamed(tmp_path):
    """Written BEFORE the rename it would point every daemon at assets the release does not contain."""
    writer = _load("um_upd2", "update_manifest.py")
    _built(tmp_path / "d")
    with pytest.raises(SystemExit, match="survived the rename"):
        writer.write(tmp_path / "d", "v1")


def test_the_manifest_refuses_a_digest_the_signed_sums_disagree_with(tmp_path):
    names = _load("rn_upd3", "release_names.py")
    writer = _load("um_upd3", "update_manifest.py")
    _built(tmp_path / "d")
    names.rename_for("macos", tmp_path / "d")
    (tmp_path / "d" / "Zaelar-macos.zip").write_bytes(b"replaced after the sums were signed")
    with pytest.raises(SystemExit, match="SHA256SUMS-macos says"):
        writer.write(tmp_path / "d", "v1")


def test_a_notarized_pkg_is_renamed_summed_and_listed(tmp_path):
    names = _load("rn_upd4", "release_names.py")
    writer = _load("um_upd4", "update_manifest.py")
    _built(tmp_path / "d")
    (tmp_path / "d" / "Zaelar.pkg").write_bytes(b"notarized pkg")
    names.rename_for("macos", tmp_path / "d")
    assert "Zaelar-macos.pkg" in (tmp_path / "d" / "SHA256SUMS-macos").read_text()
    data = json.loads(writer.write(tmp_path / "d", "v1").read_text())
    assert data["installers"]["macos"]["asset"] == "Zaelar-macos.pkg"


# ── the workflow ──────────────────────────────────────────────────────────────────────────────────────────────

def test_the_workflow_references_only_the_agreed_secret_names():
    used = set(re.findall(r"secrets\.([A-Z0-9_]+)", WORKFLOW.read_text(encoding="utf-8")))
    assert used == APPLE_SECRETS | WINDOWS_SECRETS | MINISIGN_SECRETS, used ^ (APPLE_SECRETS | WINDOWS_SECRETS
                                                                               | MINISIGN_SECRETS)


def _steps(job: str) -> list[dict]:
    return _workflow()["jobs"][job]["steps"]


def _index(steps, pred, what):
    for i, s in enumerate(steps):
        if pred(s):
            return i
    raise AssertionError(f"no step that {what}")


def test_identity_signing_is_conditional_after_the_smoke_test_and_before_the_sums():
    steps = _steps("build")
    ident = _index(steps, lambda s: s.get("id") == "identity", "decides which identities exist")
    probe = steps[ident]
    assert set(probe["env"]) == APPLE_SECRETS | WINDOWS_SECRETS
    assert "unsigned: identity secrets absent" in probe["run"]
    assert "::notice" in probe["run"]
    smoke = max(_index(steps, lambda s: str(s.get("name", "")).startswith("The binary actually runs") and
                       os_ in str(s.get("name")), "smoke-tests") for os_ in ("macOS", "Windows"))
    mac = _index(steps, lambda s: "sign_and_notarize.sh sign" in str(s.get("run", "")), "signs with Developer ID")
    win = _index(steps, lambda s: str(s.get("uses", "")).startswith("azure/artifact-signing-action@"),
                 "signs with Authenticode")
    rename = _index(steps, lambda s: "release_names.py" in str(s.get("run", "")), "renames")
    cosign = _index(steps, lambda s: "cosign sign-blob" in str(s.get("run", "")), "cosigns")
    assert smoke < ident < mac < rename < cosign and ident < win < rename
    assert steps[mac]["if"] == "runner.os == 'macOS' && steps.identity.outputs.apple == 'true'"
    assert steps[win]["if"] == "runner.os == 'Windows' && steps.identity.outputs.windows == 'true'"
    assert set(steps[mac]["env"]) == APPLE_SECRETS
    assert re.fullmatch(r"azure/artifact-signing-action@[0-9a-f]{40}", steps[win]["uses"]), "pinned by commit"
    with_ = steps[win]["with"]
    assert {re.search(r"secrets\.(\w+)", str(v)).group(1) for v in with_.values() if "secrets." in str(v)} \
        == WINDOWS_SECRETS
    shape_check = _index(steps, lambda s: "sign_and_notarize.sh check" in str(s.get("run", "")),
                         "checks the package shape on every build")
    assert "if" not in steps[shape_check] or steps[shape_check]["if"] == "runner.os == 'macOS'"


def test_the_manifest_job_signs_when_it_can_and_verifies_like_a_client():
    jobs = _workflow()["jobs"]
    job = jobs["manifest"]
    assert job["needs"] == "build" and job["permissions"] == {"contents": "read"}
    assert set(jobs["release"]["needs"]) == {"build", "manifest"}
    steps = job["steps"]
    write = _index(steps, lambda s: "update_manifest.py" in str(s.get("run", "")), "writes the manifest")
    sign = _index(steps, lambda s: s.get("id") == "minisign", "signs it")
    verify = _index(steps, lambda s: "check.verify" in str(s.get("run", "")), "verifies it")
    assert write < sign < verify
    assert set(steps[sign]["env"]) == MINISIGN_SECRETS
    assert "minisign -S" in steps[sign]["run"] and "::notice" in steps[sign]["run"]
    assert "REFUSE" in steps[sign]["run"], "the notice says what an unsigned manifest means"
    assert steps[verify]["if"] == "steps.minisign.outputs.signed == 'true'"
    assert "public_keys()" in steps[verify]["run"], "verified against the COMMITTED key, not the secret's own"


# ── the installers ────────────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("script", ["get.sh", "macos/install.sh", "macos/uninstall.sh", "macos/sign_and_notarize.sh",
                                    "macos/pkg/postinstall"])
def test_the_shell_scripts_parse(script):
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("needs bash")
    out = subprocess.run([bash, "-n", str(PACKAGING / script)], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr


def test_the_powershell_installer_checks_the_manifest_before_installing():
    """No PowerShell here; the Windows job parse-checks it. What can be read: the order and the refusals."""
    text = (PACKAGING / "get.ps1").read_text(encoding="utf-8")
    assert text.index("& minisign -V") < text.index("& $installer")
    assert "does not verify against the published key. Nothing was installed." in text
    assert "/update/PUBLIC_KEY" in text, "the key comes from the script's own origin, never the release"


def _fake(bin_dir: Path, name: str, body: str) -> None:
    p = bin_dir / name
    p.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    p.chmod(0o755)


def _get_sh(tmp_path: Path, minisign_exit: int | None, manifest: bool = True, signature: bool = True,
            pkg: bool = False, list_bytes: bool = True):
    bash, shasum = shutil.which("bash"), shutil.which("shasum")
    if not bash or not shasum:
        pytest.skip("needs bash and shasum")
    fx = tmp_path / "fx"
    fx.mkdir()
    zip_, pkg_ = b"the app, zipped", b"the notarized pkg"
    (fx / "Zaelar-macos.zip").write_bytes(zip_)
    sums = f"{hashlib.sha256(zip_).hexdigest()}  Zaelar-macos.zip\n"
    if pkg:
        (fx / "Zaelar-macos.pkg").write_bytes(pkg_)
        sums += f"{hashlib.sha256(pkg_).hexdigest()}  Zaelar-macos.pkg\n"
    (fx / "SHA256SUMS-macos").write_text(sums, encoding="utf-8")
    listed = hashlib.sha256(pkg_ if pkg else zip_).hexdigest() if list_bytes else "0" * 64
    if manifest:
        (fx / "update-manifest.json").write_text(json.dumps({"sha256": listed}), encoding="utf-8")
    if signature:
        (fx / "update-manifest.json.minisig").write_text("sig", encoding="utf-8")
    (fx / "PUBLIC_KEY").write_text("pub", encoding="utf-8")
    marker = tmp_path / "installed"
    (fx / "install.sh").write_text(f'echo "$1" > "{marker}"\n', encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake(bin_dir, "curl", 'out=""; url=""\n'
                           'while [ $# -gt 0 ]; do case "$1" in -o) out="$2"; shift 2;; -*) shift;; *) url="$1"; shift;; esac; done\n'
                           'src="$FX/${url##*/}"\n[ -f "$src" ] || exit 22\n'
                           'if [ -n "$out" ]; then cp "$src" "$out"; else cat "$src"; fi\n')
    _fake(bin_dir, "uname", 'case "$1" in -s) echo Darwin;; -m) echo arm64;; *) echo Darwin;; esac\n')
    if minisign_exit is not None:
        _fake(bin_dir, "minisign", f'printf "%s\\n" "$@" > "$MS_ARGS"\nexit {minisign_exit}\n')
    env = {"PATH": f"{bin_dir}:{os.path.dirname(shasum)}:/usr/bin:/bin", "HOME": str(tmp_path),
           "TMPDIR": str(tmp_path), "FX": str(fx), "MS_ARGS": str(tmp_path / "ms-args"),
           "ZAELAR_DAEMON_TAG": "v9.9.9"}
    out = subprocess.run([bash, str(PACKAGING / "get.sh")], capture_output=True, text=True, timeout=30, env=env)
    return out, marker, tmp_path / "ms-args"


def test_get_sh_refuses_a_manifest_that_does_not_verify(tmp_path):
    out, marker, _ = _get_sh(tmp_path, minisign_exit=1)
    assert out.returncode != 0 and not marker.exists()
    assert "does not verify" in out.stderr


def test_get_sh_refuses_a_signed_manifest_that_does_not_list_the_bytes(tmp_path):
    out, marker, _ = _get_sh(tmp_path, minisign_exit=0, list_bytes=False)
    assert out.returncode != 0 and not marker.exists()
    assert "does not list the file" in out.stderr


def test_get_sh_verifies_a_good_manifest_with_the_key_from_its_own_origin(tmp_path):
    out, marker, args = _get_sh(tmp_path, minisign_exit=0)
    assert out.returncode == 0, out.stderr
    assert marker.exists() and "update manifest ok" in out.stdout
    called = args.read_text().splitlines()
    assert called[0] == "-V" and "-p" in called and "-m" in called


@pytest.mark.parametrize("manifest,signature,said", [(False, False, "publishes none"),
                                                     (True, False, "publishes it unsigned")])
def test_get_sh_says_what_it_skipped_on_an_older_release(tmp_path, manifest, signature, said):
    out, marker, _ = _get_sh(tmp_path, minisign_exit=0, manifest=manifest, signature=signature)
    assert out.returncode == 0, out.stderr
    assert marker.exists() and said in out.stdout


def test_get_sh_prefers_the_notarized_pkg_the_signed_sums_list(tmp_path):
    out, marker, _ = _get_sh(tmp_path, minisign_exit=None, pkg=True)
    assert out.returncode == 0, out.stderr
    assert marker.read_text().strip().endswith("Zaelar-macos.pkg")
    (tmp_path / "zip").mkdir()
    out2, marker2, _ = _get_sh(tmp_path / "zip", minisign_exit=None)
    assert out2.returncode == 0, out2.stderr
    assert marker2.read_text().strip().endswith("Zaelar-macos.zip"), "no pkg listed: the zip, exactly as before"


def test_install_sh_asks_gatekeeper_about_a_pkg_before_using_it():
    text = (PACKAGING / "macos" / "install.sh").read_text(encoding="utf-8")
    at = text.index('if [[ "$SOURCE" == *.pkg ]]; then')
    block = text[at:text.index("\nfi\n", at)]
    assert block.index("pkgutil --check-signature") < block.index("spctl --assess --type install") \
        < block.index("pkgutil --expand-full")
    assert "Nothing was installed" in block


@pytest.mark.skipif(sys.platform != "darwin" or not shutil.which("pkgbuild"), reason="needs macOS pkgbuild")
def test_the_installer_package_is_a_current_user_install(tmp_path):
    """`check` mode builds the package UNSIGNED and checks the shape every published one must have."""
    exe = tmp_path / "Zaelar.app" / "Contents" / "MacOS" / "zaelar-daemon"
    exe.parent.mkdir(parents=True)
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    import plistlib
    with open(tmp_path / "Zaelar.app" / "Contents" / "Info.plist", "wb") as fh:
        plistlib.dump({"CFBundleExecutable": "zaelar-daemon", "CFBundleIdentifier": "com.zaelar.daemon",
                       "CFBundleShortVersionString": "0.2.2", "CFBundleVersion": "0.2.2"}, fh)
    out = subprocess.run(["bash", str(PACKAGING / "macos" / "sign_and_notarize.sh"), "check",
                          str(tmp_path / "Zaelar.app"), str(tmp_path / "out"), "macos"],
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert "current-user install" in out.stdout
