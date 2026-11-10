"""A daemon release can be verified by somebody who does not trust us (V2-575 · P4, signing).

Before this, the one-line installer checked a binary against a checksum file from the same release: two files
agreeing, which catches a corrupt download and nothing else — whoever can replace one can replace the other.
Now each build job signs its `SHA256SUMS-<suffix>` with a Sigstore KEYLESS signature (the signer is the release
workflow's GitHub OIDC identity, logged in Rekor) and attests the provenance of the binaries the sums list, and
the installers verify the signature when `cosign` is on PATH.

What can silently break that, and what each test here pins:

  · the job loses `id-token: write` → signing fails, or someone "fixes" it by dropping the step;
  · the signature is taken BEFORE `release_names.py` rewrites the sums → a valid signature over a file that is
    never published, which fails on every user's machine (or, worse, a stale one that verifies something else);
  · the three places that name the bundle drift apart (the workflow writes one name, the installer fetches
    another) → every cosign user is refused, or the check is quietly skipped;
  · the installer treats a MISSING signature as "fine" → deleting one file defeats the whole mechanism;
  · the installer checks the signature after it has already run something.

The workflow itself can only be run on GitHub. What runs here is its STRUCTURE, the real `release_names.py`, and
the real `get.sh` against a fake network and a fake `cosign` — `get.ps1` is checked by text (no PowerShell on
the machines this suite runs on; the workflow parse-checks it on Windows).
"""
from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ENGINE = Path(__file__).resolve().parents[4]
WORKFLOW = ENGINE / ".github" / "workflows" / "daemon-artifacts.yml"
PACKAGING = ENGINE / "daemon" / "packaging"

SIGNER_RE = r"^https://github.com/asimovia/zaelar/\.github/workflows/daemon-artifacts\.yml@refs/tags/"
ISSUER = "https://token.actions.githubusercontent.com"


def _release_names():
    spec = importlib.util.spec_from_file_location("daemon_release_names_signing", PACKAGING / "release_names.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _build_steps() -> list[dict]:
    return _workflow()["jobs"]["build"]["steps"]


def _index(steps: list[dict], predicate, what: str) -> int:
    for i, step in enumerate(steps):
        if predicate(step):
            return i
    raise AssertionError(f"the build job has no step that {what}")


def _runs(fragment: str):
    return lambda step: fragment in str(step.get("run", ""))


def _uses(prefix: str):
    return lambda step: str(step.get("uses", "")).startswith(prefix)


# ── the workflow ─────────────────────────────────────────────────────────────────────────────────────────────
def test_the_build_job_may_sign_and_attest_and_nothing_more():
    """`id-token: write` is what lets the job become a signing identity; `attestations: write` stores the
    provenance. The build never writes to the repository — that stays with the release job — so `contents` is
    read-only here: a job that can mint a signing certificate should not also be able to rewrite a release."""
    jobs = _workflow()["jobs"]
    assert jobs["build"].get("permissions") == {
        "contents": "read", "id-token": "write", "attestations": "write"}
    assert jobs["release"].get("permissions") == {"contents": "write"}


def test_the_checksums_are_signed_after_the_rename_and_checked_before_upload():
    """⚠️ THE ORDER IS THE GUARD. `release_names.py` rewrites the sums for the published names; a signature
    taken before it is valid over bytes that are never published. And the job verifies its own bundle before
    uploading, so a signature that would fail on a user's machine fails here first. The guards-hold check of
    the real binary stays ahead of all of it: nothing that does not run gets signed."""
    steps = _build_steps()
    guards = _index(steps, lambda s: "guards hold" in str(s.get("name", "")), "checks the binary's guards")
    rename = _index(steps, _runs("release_names.py"), "runs release_names.py")
    install = _index(steps, _uses("sigstore/cosign-installer@"), "installs cosign")
    sign = _index(steps, _runs("cosign sign-blob"), "signs with cosign")
    verify = _index(steps, _runs("cosign verify-blob"), "verifies the signature")
    upload = _index(steps, _uses("actions/upload-artifact@"), "uploads the build")
    assert guards < rename < sign < verify < upload, "signing must sit between the rename and the upload"
    assert install < sign


def test_the_signature_is_keyless_over_the_published_sums_name():
    """Keyless = no `--key`, so there is no secret to leak or rotate; `--yes` because a CI job cannot answer
    the consent prompt. The input and output names are the ones `release_names.py` declares — the same two
    names both installers download — so the signature is always over what the release publishes."""
    names = _release_names()
    sums = "dist/daemon/" + names.SUMS_TEMPLATE.format(suffix="${{ matrix.suffix }}")
    bundle = "dist/daemon/" + names.SIGNATURE_TEMPLATE.format(suffix="${{ matrix.suffix }}")
    steps = _build_steps()
    sign = " ".join(str(steps[_index(steps, _runs("cosign sign-blob"), "signs")]["run"]).split())
    assert "--yes" in sign
    assert "--key" not in sign, "the release is signed keyless — a key would be a secret to leak"
    assert f'--bundle "{bundle}"' in sign
    assert sign.rstrip().endswith(f'"{sums}"'), "the signed blob is not the published sums file"
    verify = " ".join(str(steps[_index(steps, _runs("cosign verify-blob"), "verifies")]["run"]).split())
    assert f'--bundle "{bundle}"' in verify and f"--certificate-oidc-issuer {ISSUER}" in verify
    assert "github.workflow_ref" in verify, "the self-check must pin THIS workflow's identity, not any"


def test_the_signing_tools_are_pinned_to_exact_versions():
    """A floating `@v4` or an unpinned cosign means the tool that mints the release signature can change
    between two runs of the same commit."""
    steps = _build_steps()
    installer = steps[_index(steps, _uses("sigstore/cosign-installer@"), "installs cosign")]
    assert re.fullmatch(r"sigstore/cosign-installer@v\d+\.\d+\.\d+", installer["uses"])
    assert re.fullmatch(r"v\d+\.\d+\.\d+", str(installer.get("with", {}).get("cosign-release", "")))
    attest = steps[_index(steps, _uses("actions/attest-build-provenance@"), "attests provenance")]
    assert re.fullmatch(r"actions/attest-build-provenance@v\d+\.\d+\.\d+", attest["uses"])


def test_provenance_is_attested_for_exactly_what_the_sums_list():
    """The attestation's subjects come from the sums file itself, so the provenance and the checksums can never
    be about different files — the binary and the portable archive, under their published names."""
    names = _release_names()
    steps = _build_steps()
    rename = _index(steps, _runs("release_names.py"), "renames")
    at = _index(steps, _uses("actions/attest-build-provenance@"), "attests provenance")
    upload = _index(steps, _uses("actions/upload-artifact@"), "uploads")
    assert rename < at < upload
    assert steps[at]["with"] == {
        "subject-checksums": "dist/daemon/" + names.SUMS_TEMPLATE.format(suffix="${{ matrix.suffix }}")}


def test_a_build_that_is_not_a_daemon_tag_still_publishes_nothing():
    """Signing must not turn a dispatch, a branch run or an ENGINE tag into a daemon release: only the release job,
    gated on the daemon's own `daemon-v` tags, attaches files, and the build job uploads build artifacts only
    (V2-869 §5: an engine release carrying daemon builds was picked over a newer, signed daemon release)."""
    jobs = _workflow()["jobs"]
    assert jobs["release"]["if"] == "startsWith(github.ref, 'refs/tags/daemon-v')"
    assert not any("action-gh-release" in str(s.get("uses", "")) for s in jobs["build"]["steps"])


# ── release_names.py ─────────────────────────────────────────────────────────────────────────────────────────
def test_no_signature_survives_a_rename(tmp_path):
    """A signature from an earlier build name or an earlier run, left beside freshly rewritten sums, would be
    published as if it vouched for them. The rename deletes every one, of every shape, so the only signature in
    the release is the one the next step makes over what the rename wrote."""
    names = _release_names()
    (tmp_path / "zaelar-daemon").write_bytes(b"binary")
    (tmp_path / "zaelar-daemon.pyz").write_bytes(b"archive")
    (tmp_path / "SHA256SUMS").write_text("0" * 64 + "  zaelar-daemon\n", encoding="utf-8")
    stale = ["SHA256SUMS.sig", "SHA256SUMS.pem", "SHA256SUMS-macos.sigstore.json",
             "SHA256SUMS-old.sigstore", "SHA256SUMS-macos.bundle"]
    for name in stale:
        (tmp_path / name).write_text("stale", encoding="utf-8")
    names.rename_for("macos", tmp_path)
    left = sorted(p.name for p in tmp_path.iterdir())
    assert not [n for n in left if n in stale], f"a stale signature survived: {left}"
    sums = tmp_path / names.SUMS_TEMPLATE.format(suffix="macos")
    listed = {line.split()[1] for line in sums.read_text(encoding="utf-8").splitlines()}
    assert listed == {"zaelar-daemon-macos", "zaelar-daemon-macos.pyz"}
    assert names.SIGNATURE_TEMPLATE == names.SUMS_TEMPLATE + ".sigstore.json"


def test_the_sums_a_windows_build_writes_check_on_any_machine(tmp_path, monkeypatch):
    """On Windows, text mode turns every `\\n` into CRLF unless told otherwise, and a sums file whose names end
    in `\\r` fails `shasum -c` / `sha256sum -c` everywhere else — the signature would vouch for a file nobody
    can use to check the binary. Windows' translation is simulated here, since this suite runs elsewhere."""
    names = _release_names()
    original = Path.write_text

    def windows_write_text(self, data, encoding=None, errors=None, newline=None):
        translated = data.replace("\n", "\r\n") if newline is None else data
        return original(self, translated, encoding=encoding, errors=errors, newline="")

    monkeypatch.setattr(Path, "write_text", windows_write_text)
    (tmp_path / "zaelar-daemon.exe").write_bytes(b"binary")
    (tmp_path / "zaelar-daemon.pyz").write_bytes(b"archive")
    (tmp_path / "manifest.json").write_bytes(b"{}")
    names.rename_for("windows", tmp_path)
    for written in (names.SUMS_TEMPLATE.format(suffix="windows"), "manifest-windows.json"):
        assert b"\r" not in (tmp_path / written).read_bytes(), f"{written} was written with CRLF"


# ── the installers ───────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("script,start,end,default", [
    ("get.sh", 'VERIFY_OUT="$(cosign verify-blob', "2>&1)", 'SIGNER_RE="${ZAELAR_DAEMON_SIGNER_RE:-' + SIGNER_RE + '}"'),
    ("get.ps1", "& cosign verify-blob", "2>&1", "else { '" + SIGNER_RE + "' }"),
])
def test_the_installer_verifies_against_the_release_workflows_identity(script, start, end, default):
    """The identity is the WHOLE check: a bundle from any GitHub workflow anywhere verifies against a loose
    regexp. Anchored to this repository, this workflow file, and a tag ref — a branch build is not a release.
    Read from the INVOCATION itself, not the file: the by-hand hint line names the same flags, and a test that
    found them there would stay green with the real check gone."""
    text = (PACKAGING / script).read_text(encoding="utf-8")
    assert default in text, f"{script} does not default to the release workflow's identity"
    assert ISSUER in text
    at = text.index(start)
    call = text[at:text.index(end, at)]
    var = "$SIGNER_RE" if script == "get.sh" else "$SignerRe"
    issuer = "$OIDC_ISSUER" if script == "get.sh" else "$OidcIssuer"
    for flag in ("--bundle", f"--certificate-identity-regexp {var}", f"--certificate-oidc-issuer {issuer}"):
        assert flag in call.replace('"', ""), f"{script}'s cosign call lacks {flag}"


@pytest.mark.parametrize("script,fetched", [
    ("get.sh", '"$BASE/$SUMS.sigstore.json"'),
    ("get.ps1", '"$Base/SHA256SUMS-windows.sigstore.json"'),
])
def test_the_installer_fetches_the_bundle_the_workflow_writes(script, fetched):
    """The third side of the join: `release_names.py` names the bundle, the workflow writes it, the installer
    downloads it. A drift is not loud — it refuses every user who has cosign installed."""
    names = _release_names()
    assert names.SIGNATURE_TEMPLATE.format(suffix="x").endswith(".sigstore.json")
    assert fetched in (PACKAGING / script).read_text(encoding="utf-8")


@pytest.mark.parametrize("script,check,hasher,run", [
    ("get.sh", "cosign verify-blob", "shasum -a 256", 'bash "$WORK/install.sh"'),
    ("get.ps1", "& cosign verify-blob", "Get-FileHash", "& $installer"),
])
def test_the_signature_is_checked_before_the_hash_and_before_anything_runs(script, check, hasher, run):
    """The hash is only as good as the sums it is compared with, so the sums' signature comes first; and both
    come before the installer is executed."""
    text = (PACKAGING / script).read_text(encoding="utf-8")
    assert text.index(check) < text.index(hasher) < text.index(run)


# ── get.sh, for real, against a fake network ─────────────────────────────────────────────────────────────────
def _fake_bin(tmp_path: Path, cosign_exit: int | None) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    def tool(name: str, body: str) -> None:
        path = bin_dir / name
        path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
        path.chmod(0o755)

    # The network: every URL is answered from the fixture folder by its last path segment; a missing one is
    # a 404, which `curl -f` reports as exit 22.
    tool("curl", 'out=""; url=""\n'
                 'while [ $# -gt 0 ]; do case "$1" in -o) out="$2"; shift 2;; -*) shift;; *) url="$1"; shift;; esac; done\n'
                 'src="$FIXTURES/${url##*/}"\n[ -f "$src" ] || exit 22\n'
                 'if [ -n "$out" ]; then cp "$src" "$out"; else cat "$src"; fi\n')
    tool("uname", 'case "$1" in -s) echo Darwin;; -m) echo arm64;; *) echo Darwin;; esac\n')
    if cosign_exit is not None:
        tool("cosign", f'printf "%s\\n" "$@" > "$COSIGN_ARGS"\nexit {cosign_exit}\n')
    return bin_dir


def _run_get_sh(tmp_path: Path, cosign_exit: int | None, with_bundle: bool = True):
    bash = shutil.which("bash")
    shasum = shutil.which("shasum")
    if not bash or not shasum:
        pytest.skip("needs bash and shasum")
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    binary = b"the daemon app, zipped"
    (fixtures / "Zaelar-macos.zip").write_bytes(binary)
    import hashlib
    (fixtures / "SHA256SUMS-macos").write_text(
        f"{hashlib.sha256(binary).hexdigest()}  Zaelar-macos.zip\n", encoding="utf-8")
    if with_bundle:
        (fixtures / "SHA256SUMS-macos.sigstore.json").write_text("{}", encoding="utf-8")
    marker = tmp_path / "installed"
    (fixtures / "install.sh").write_text(f'echo "$1" > "{marker}"\n', encoding="utf-8")
    bin_dir = _fake_bin(tmp_path, cosign_exit)
    env = {
        "PATH": f"{bin_dir}:{os.path.dirname(shasum)}:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "TMPDIR": str(tmp_path),
        "FIXTURES": str(fixtures),
        "COSIGN_ARGS": str(tmp_path / "cosign-args"),
        "ZAELAR_DAEMON_TAG": "v9.9.9",
    }
    out = subprocess.run([bash, str(PACKAGING / "get.sh")], capture_output=True, text=True, timeout=30, env=env)
    return out, marker, tmp_path / "cosign-args"


def test_a_bad_signature_stops_the_install(tmp_path):
    out, marker, args = _run_get_sh(tmp_path, cosign_exit=1)
    assert out.returncode != 0
    assert not marker.exists(), "the installer ran although the signature did not verify"
    assert "does not verify" in out.stderr


def test_a_missing_signature_is_a_refusal_not_a_skip(tmp_path):
    """Whoever can replace the binary and the sums can delete the bundle; if that made the check skip, the
    signature would protect against nobody."""
    out, marker, args = _run_get_sh(tmp_path, cosign_exit=0, with_bundle=False)
    assert out.returncode != 0
    assert not marker.exists()
    assert "no signature" in out.stderr


def test_a_good_signature_installs_and_was_checked_against_the_pinned_identity(tmp_path):
    out, marker, args = _run_get_sh(tmp_path, cosign_exit=0)
    assert out.returncode == 0, out.stderr
    assert marker.exists()
    called = args.read_text(encoding="utf-8").splitlines()
    assert called[0] == "verify-blob"
    assert called[called.index("--certificate-identity-regexp") + 1] == SIGNER_RE
    assert called[called.index("--certificate-oidc-issuer") + 1] == ISSUER
    assert "signature ok" in out.stdout


def test_without_cosign_it_installs_on_the_hash_and_says_how_to_verify(tmp_path):
    """No cosign is the common case; refusing would turn a security feature into "the installer is broken".
    It installs on the hash check and says, in ONE line, what was skipped and the command to do it by hand."""
    out, marker, args = _run_get_sh(tmp_path, cosign_exit=None)
    assert out.returncode == 0, out.stderr
    assert marker.exists()
    lines = [line for line in out.stdout.splitlines() if "signature not checked" in line]
    assert len(lines) == 1
    assert "cosign verify-blob --bundle SHA256SUMS-macos.sigstore.json" in lines[0]
    assert SIGNER_RE in lines[0] and ISSUER in lines[0]
