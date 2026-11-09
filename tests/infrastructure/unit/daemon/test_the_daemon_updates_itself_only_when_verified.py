"""The installed daemon updates itself — and ONLY with bytes the publisher signed for (V2-869 §4).

The one rule this file exists for: ANY VERIFICATION FAILURE LEAVES THE INSTALLED DAEMON UNTOUCHED. Every refusal
below asserts the installed program's bytes afterwards, not just the state the updater reports — an updater that
says "failed" after half-replacing the program is the failure this mechanism exists to prevent.

Pinned:
  · the pure-Python Ed25519 verifier against RFC 8032's vectors and against a real implementation;
  · the minisign format: a fixture signed IN THE TEST with a throwaway key (never the real one) verifies; a tampered
    file, an altered trusted comment, another key, the legacy algorithm — refused;
  · the committed `daemon/update/PUBLIC_KEY` is a PUBLIC key and nothing else;
  · the client: an unsigned manifest, a mis-signed one, one replayed from another release — refused before any asset
    is downloaded; a sha256 or size mismatch — refused, download deleted, install untouched; a staged file that
    changes between `ready` and the swap — refused, install untouched; the good path swaps and restarts;
  · the state machine idle → downloading → ready / failed, and its illegal transitions;
  · `/health.update = {current, available, state, error, last_check}`;
  · the swap's rollback when the second rename fails (the Windows dance), and the macOS bundle exchange;
  · the tray offers «Install» only for a verified, waiting update.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from daemon.update import apply, check, ed25519, manifest, minisign, state as update_state

ENGINE = Path(__file__).resolve().parents[4]

# ── a throwaway minisign signer, built in the test (cryptography is a TEST dependency; the daemon never needs it) ──


class Signer:
    def __init__(self, key_id: bytes = b"\x01\x02\x03\x04\x05\x06\x07\x08"):
        ed = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519")
        from cryptography.hazmat.primitives import serialization
        self._sk = ed.Ed25519PrivateKey.generate()
        self.key_id = key_id
        self.pk = self._sk.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)

    @property
    def public_text(self) -> str:
        return "untrusted comment: test key\n" + base64.b64encode(b"Ed" + self.key_id + self.pk).decode() + "\n"

    @property
    def public_key(self) -> minisign.PublicKey:
        return minisign.parse_public_key(self.public_text)

    def sign(self, data: bytes, comment: str = "timestamp:1", algorithm: bytes = b"ED") -> str:
        msg = hashlib.blake2b(data, digest_size=64).digest() if algorithm == b"ED" else data
        sig = self._sk.sign(msg)
        glob = self._sk.sign(sig + comment.encode())
        return ("untrusted comment: signature from a test key\n"
                + base64.b64encode(algorithm + self.key_id + sig).decode() + "\n"
                + f"trusted comment: {comment}\n" + base64.b64encode(glob).decode() + "\n")


# ── Ed25519 ───────────────────────────────────────────────────────────────────────────────────────────────────

RFC8032 = [   # (public key, message, signature) — RFC 8032 §7.1, TEST 1 and TEST 2
    ("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", "",
     "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe"
     "24655141438e7a100b"),
    ("3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", "72",
     "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302a"
     "eeb00d291612bb0c00"),
]


@pytest.mark.parametrize("pk,msg,sig", RFC8032)
def test_ed25519_verifies_the_rfc_vectors_and_nothing_else(pk, msg, sig):
    pk, msg, sig = bytes.fromhex(pk), bytes.fromhex(msg), bytes.fromhex(sig)
    assert ed25519.verify(pk, msg, sig)
    assert not ed25519.verify(pk, msg + b"x", sig)
    flipped = bytearray(sig)
    flipped[5] ^= 1
    assert not ed25519.verify(pk, msg, bytes(flipped))
    assert not ed25519.verify(pk[:31], msg, sig) and not ed25519.verify(pk, msg, sig[:63])


def test_ed25519_agrees_with_a_real_implementation():
    signer = Signer()
    for data in (b"", b"a", os.urandom(1000)):
        assert ed25519.verify(signer.pk, data, signer._sk.sign(data))
    # s >= L (a malleated signature) is refused, as RFC 8032 requires.
    sig = bytearray(signer._sk.sign(b"m"))
    s = int.from_bytes(sig[32:], "little") + ed25519._L
    sig[32:] = s.to_bytes(32, "little")
    assert not ed25519.verify(signer.pk, b"m", bytes(sig))


# ── minisign ──────────────────────────────────────────────────────────────────────────────────────────────────

def test_a_minisign_signature_made_with_a_throwaway_key_verifies_and_tampering_does_not():
    signer = Signer()
    data = b'{"product": "zaelar-daemon"}\n'
    sig = signer.sign(data, "build=7")
    assert minisign.verify(data, sig, [signer.public_key]) == "build=7"
    with pytest.raises(minisign.SignatureError, match="does not match"):
        minisign.verify(data + b" ", sig, [signer.public_key])
    lines = sig.splitlines()
    lines[2] = "trusted comment: build=8"
    with pytest.raises(minisign.SignatureError, match="altered"):
        minisign.verify(data, "\n".join(lines) + "\n", [signer.public_key])
    with pytest.raises(minisign.SignatureError, match="unknown key"):
        minisign.verify(data, sig, [Signer(b"\x09" * 8).public_key])
    with pytest.raises(minisign.SignatureError, match="prehashed"):
        minisign.verify(data, signer.sign(data, algorithm=b"Ed"), [signer.public_key])
    with pytest.raises(minisign.SignatureError):
        minisign.verify(data, "", [signer.public_key])


def test_a_real_minisign_signature_verifies(tmp_path):
    """When the reference tool is installed, its own output (throwaway key, no password) must verify here."""
    tool = shutil.which("minisign")
    if not tool:
        pytest.skip("minisign is not installed")
    pub, sec, data = tmp_path / "k.pub", tmp_path / "k.sec", tmp_path / "m.json"
    subprocess.run([tool, "-G", "-W", "-p", str(pub), "-s", str(sec)], check=True, capture_output=True)
    data.write_bytes(b'{"a": 1}\n')
    subprocess.run([tool, "-S", "-s", str(sec), "-m", str(data), "-t", "hello"], check=True, capture_output=True)
    key = minisign.parse_public_key(pub.read_text())
    assert minisign.verify(data.read_bytes(), (tmp_path / "m.json.minisig").read_text(), [key]) == "hello"


def test_the_committed_key_is_a_public_key_and_only_that():
    text = (ENGINE / "daemon" / "update" / "PUBLIC_KEY").read_text(encoding="utf-8")
    key = minisign.parse_public_key(text)
    assert len(key.key) == 32
    assert "PUBLIC key" in text and "secret" not in text.lower().replace("never", "")
    assert len([ln for ln in text.splitlines() if ln.strip()]) == 2, "a comment and ONE key line, nothing else"


# ── the client ────────────────────────────────────────────────────────────────────────────────────────────────

TAG = "v9.0.0"
NEW = b"the NEW daemon archive"
OLD = b"the installed daemon archive"


def _manifest(build: int = 999, data: bytes = NEW, tag: str = TAG, **extra) -> bytes:
    body = {"product": "zaelar-daemon", "version": "9.0.0", "build": build, "tag": tag,
            "published_at": "2026-11-09T00:00:00Z", "min_engine_build": 0, "next_key": None,
            "platforms": {"pyz": {"asset": "zaelar-daemon-macos.pyz", "sha256": hashlib.sha256(data).hexdigest(),
                                  "size": len(data)}}}
    body.update(extra)
    return (json.dumps(body, indent=1, sort_keys=True) + "\n").encode()


class Net:
    """A fake release server. Records every URL asked for, so a test can prove the asset was never fetched."""

    def __init__(self, manifest_bytes: bytes, signature: str | None, asset: bytes = NEW, tag: str = TAG):
        base = f"https://github.com/asimovia/zaelar/releases/download/{tag}"
        self.files = {f"{base}/update-manifest.json": manifest_bytes, f"{base}/zaelar-daemon-macos.pyz": asset}
        assets = [{"name": "update-manifest.json", "browser_download_url": f"{base}/update-manifest.json"}]
        if signature is not None:
            self.files[f"{base}/update-manifest.json.minisig"] = signature.encode()
            assets.append({"name": "update-manifest.json.minisig",
                           "browser_download_url": f"{base}/update-manifest.json.minisig"})
        releases = [{"tag_name": "v9.1.0-no-daemon", "assets": []}, {"tag_name": tag, "assets": assets}]
        self.files["https://api.github.com/repos/asimovia/zaelar/releases?per_page=100"] = json.dumps(releases).encode()
        self.asked: list[str] = []

    def fetch(self, url: str, **_kw) -> bytes:
        self.asked.append(url)
        if url not in self.files:
            raise OSError(f"404 {url}")
        return self.files[url]

    def fetch_file(self, url: str, dest: Path, limit: int) -> None:
        dest.write_bytes(self.fetch(url))

    def asked_for_asset(self) -> bool:
        return any(u.endswith(".pyz") for u in self.asked)


@pytest.fixture
def env(tmp_path, monkeypatch):
    """An installed `.pyz`, a fresh update state, the committed key replaced by a throwaway one."""
    signer = Signer()
    monkeypatch.delenv("ZAELAR_DAEMON_REPO", raising=False)
    monkeypatch.setattr(check, "public_keys", lambda learned=None: [signer.public_key] + (
        [minisign.parse_public_key(learned)] if learned else []))
    monkeypatch.setattr(check, "current", lambda: {"version": "0.2.2", "build": 100})
    installed = tmp_path / "bin" / "zaelar-daemon.pyz"
    installed.parent.mkdir()
    installed.write_bytes(OLD)
    store = update_state.Store(tmp_path / "update")
    target = apply.Target("pyz", installed, "pyz")
    restarts: list = []

    def run(net: Net) -> dict:
        return check.check_and_download(fetch=net.fetch, store=store, target=target, fetch_file=net.fetch_file,
                                        cosign=None)

    def install() -> dict:
        return apply.install(store=store, target=target, restart=lambda t: restarts.append(t) or "launchd")

    return {"signer": signer, "store": store, "installed": installed, "run": run, "install": install,
            "restarts": restarts}


def test_an_unsigned_manifest_is_refused_before_anything_is_downloaded(env):
    net = Net(_manifest(), signature=None)
    result = env["run"](net)
    assert result["state"] == "failed" and "not signed" in result["error"]
    assert not net.asked_for_asset(), "an unsigned manifest must never lead to a download"
    assert env["installed"].read_bytes() == OLD


def test_a_manifest_signed_by_another_key_or_tampered_is_refused(env):
    other = Signer(b"\x07" * 8)
    for net in (Net(_manifest(), other.sign(_manifest())),                           # another key
                Net(_manifest(build=1000), env["signer"].sign(_manifest(build=999)))):   # bytes changed after signing
        result = env["run"](net)
        assert result["state"] == "failed", result
        assert not net.asked_for_asset()
        assert env["installed"].read_bytes() == OLD


def test_a_signed_manifest_replayed_from_another_release_is_refused(env):
    data = _manifest(tag="v1.0.0")
    result = env["run"](Net(data, env["signer"].sign(data)))
    assert result["state"] == "failed" and "found on release" in result["error"]
    assert env["installed"].read_bytes() == OLD


def test_a_sha256_mismatch_leaves_the_install_untouched_and_keeps_nothing(env):
    data = _manifest()
    net = Net(data, env["signer"].sign(data), asset=b"x" * len(NEW))   # same size, other bytes
    result = env["run"](net)
    assert result["state"] == "failed" and "sha256 mismatch" in result["error"]
    assert env["installed"].read_bytes() == OLD
    assert not list(env["store"].staging().iterdir()), "the rejected download was kept"
    assert env["install"]()["error"], "nothing may be installed from a failed state"
    assert env["installed"].read_bytes() == OLD and not env["restarts"]


def test_a_size_mismatch_is_refused(env):
    data = _manifest()
    result = env["run"](Net(data, env["signer"].sign(data), asset=NEW + b"!"))
    assert result["state"] == "failed" and "size mismatch" in result["error"]
    assert env["installed"].read_bytes() == OLD


def test_a_verified_update_is_downloaded_then_swapped_then_restarted(env):
    data = _manifest()
    result = env["run"](Net(data, env["signer"].sign(data)))
    assert result["state"] == "ready", result
    assert result["available"]["build"] == 999
    assert env["installed"].read_bytes() == OLD, "ready is not installed: the swap is a separate step"
    out = env["install"]()
    assert out["state"] == "idle" and out["restart"] == "launchd", out
    assert env["installed"].read_bytes() == NEW
    assert env["restarts"] and env["store"].snapshot()["pending"] is None
    assert not list(env["store"].staging().iterdir())


def test_a_staged_update_that_changes_before_the_swap_is_refused(env):
    data = _manifest()
    assert env["run"](Net(data, env["signer"].sign(data)))["state"] == "ready"
    Path(env["store"].snapshot()["pending"]["path"]).write_bytes(b"swapped under us")
    out = env["install"]()
    assert out["state"] == "failed" and "changed after it was verified" in out["error"]
    assert env["installed"].read_bytes() == OLD and not env["restarts"]


def test_an_older_or_equal_release_is_up_to_date_and_never_downloaded(env):
    for build in (100, 50):
        data = _manifest(build=build)
        net = Net(data, env["signer"].sign(data))
        result = env["run"](net)
        assert result["state"] == "idle" and result["available"] is None
        assert not net.asked_for_asset()


def test_a_next_key_is_learned_only_from_a_verified_manifest(env):
    nxt = Signer(b"\x0a" * 8)
    data = _manifest(next_key=nxt.public_text.splitlines()[1])
    env["run"](Net(data, Signer(b"\x0b" * 8).sign(data)))            # NOT trusted: nothing learned
    assert env["store"].snapshot()["next_key"] is None
    env["run"](Net(data, env["signer"].sign(data)))                   # trusted: learned
    assert env["store"].snapshot()["next_key"] == nxt.public_text.splitlines()[1]
    rotated = _manifest(build=1001)
    assert env["run"](Net(rotated, nxt.sign(rotated)))["state"] == "ready", "the announced key now verifies"


# ── the state machine ─────────────────────────────────────────────────────────────────────────────────────────

def test_the_state_machine_only_reaches_ready_through_downloading(tmp_path):
    store = update_state.Store(tmp_path)
    assert store.snapshot()["state"] == "idle"
    with pytest.raises(update_state.IllegalTransition):
        store.transition("ready")
    store.transition("downloading")
    with pytest.raises(update_state.IllegalTransition):
        store.transition("idle")
    store.transition("failed", error="x")
    assert store.snapshot()["error"] == "x"
    store.transition("downloading")
    store.transition("ready", pending={"path": "p"})
    store.transition("idle")
    assert store.snapshot()["error"] == ""
    with pytest.raises(update_state.IllegalTransition):
        store.update(state="ready")
    # A download cannot survive a restart: whoever was writing it is gone.
    store.transition("downloading")
    fresh = update_state.Store(tmp_path)
    assert fresh.snapshot()["state"] == "failed" and "interrupted" in fresh.snapshot()["error"]
    assert set(update_state.STATES) == {"idle", "downloading", "ready", "failed"}


# ── the swap ──────────────────────────────────────────────────────────────────────────────────────────────────

def test_the_windows_rename_dance_puts_the_old_program_back_when_it_fails(tmp_path, monkeypatch):
    exe = tmp_path / "zaelar-daemon.exe"
    exe.write_bytes(OLD)
    new = tmp_path / "staged.exe"
    new.write_bytes(NEW)
    real = os.rename
    calls = []

    def flaky(a, b):
        calls.append((Path(a).name, Path(b).name))
        if len(calls) == 2:
            raise OSError("the new file could not be moved into place")
        return real(a, b)

    monkeypatch.setattr(apply.os, "rename", flaky)
    with pytest.raises(OSError):
        apply.swap_file(new, exe)
    assert exe.read_bytes() == OLD, "the running program must be back under its name"
    monkeypatch.setattr(apply.os, "rename", real)
    apply.swap_file(new, exe)
    assert exe.read_bytes() == NEW and (tmp_path / "zaelar-daemon.old.exe").read_bytes() == OLD


@pytest.mark.skipif(sys.platform != "darwin", reason="the .app exchange uses macOS renamex_np and ditto")
def test_the_macos_bundle_is_exchanged_atomically_or_not_at_all(tmp_path):
    def app(root: Path, marker: bytes) -> Path:
        exe = root / "Zaelar.app" / "Contents" / "MacOS" / "zaelar-daemon"
        exe.parent.mkdir(parents=True)
        exe.write_bytes(marker)
        return root / "Zaelar.app"

    installed = app(tmp_path / "prefix", OLD)
    src = app(tmp_path / "src", NEW)
    zipped = tmp_path / "Zaelar.zip"
    subprocess.run(["ditto", "-c", "-k", "--keepParent", str(src), str(zipped)], check=True)
    exe = installed / "Contents" / "MacOS" / "zaelar-daemon"

    def refuse(new_app, old_app):
        raise apply.VerificationError("bad code signature")

    with pytest.raises(apply.VerificationError):
        apply.swap_macos_app(zipped, installed, verify=refuse)
    assert exe.read_bytes() == OLD and not (installed.parent / ".Zaelar.app.update").exists()
    apply.swap_macos_app(zipped, installed, verify=lambda new_app, old_app: None)
    assert exe.read_bytes() == NEW and not (installed.parent / ".Zaelar.app.update").exists()


def test_a_source_tree_is_never_a_target():
    assert apply.installed_target() is None, "running from a checkout: update with git, never swap the repo"


# ── what is shown ─────────────────────────────────────────────────────────────────────────────────────────────

def test_health_carries_the_update_section(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from daemon import config
    from daemon.http import routes
    config.reset_cache()
    monkeypatch.setattr(update_state, "STORE", update_state.Store(tmp_path / "upd"))
    try:
        body = routes.health(None, {})
    finally:
        config.reset_cache()
    upd = body["update"]
    assert set(upd) == {"current", "available", "state", "error", "last_check"}
    assert upd["state"] == "idle" and upd["available"] is None and upd["error"] == ""
    assert set(upd["current"]) == {"version", "build"}
    assert upd["current"]["build"] == int((ENGINE / "update" / "BUILD").read_text().strip()), \
        "a source tree reports the engine's own build number"


def test_the_tray_offers_install_only_for_a_verified_waiting_update():
    from daemon.tray import model
    base = {"ok": True, "version": "0.2.2", "configured": True, "browser": {"state": "ready"}}
    ids = lambda h: [i.id for i in model.view(h, {"enabled": True}).items]   # noqa: E731
    assert "updates" in ids(base)
    ready = dict(base, update={"state": "ready", "available": {"version": "0.3.0", "build": 130}})
    item = next(i for i in model.view(ready, {"enabled": True}).items if i.id == "update_install")
    assert "0.3.0" in item.label and "130" in item.label
    failed = dict(base, update={"state": "failed", "available": None, "error": "not signed"})
    assert "update_install" not in ids(failed) and "updates" in ids(failed)
    # Newer release known, but its download did not verify: AVAILABLE is not INSTALLABLE.
    rejected = dict(base, update={"state": "failed", "available": {"version": "0.3.0", "build": 130},
                                  "error": "sha256 mismatch"})
    assert "update_install" not in ids(rejected) and "updates" in ids(rejected)
