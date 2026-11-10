"""A daemon file is taken from the daemon's OWN release line, an engine release only as a fallback (V2-869 §5, node 7.129).

An engine release (`v3.147`) that also carried daemon builds was cut after `daemon-v0.3.0`, and "the first listed release
that carries the file" installed the engine's unsigned build under the engine's number. The order, pinned here for
every reader — `daemon/update/release_line.py` (the updater), its copy `server/daemon_release_line.py` (the 🖥 screen;
the engine may not import `daemon/`), both run on every case and held byte-equal in their code, and `get.sh` (run for
real against a fake GitHub):

  1. among `daemon-vX.Y.Z` releases carrying the file, the highest VERSION (0.10.0 > 0.9.0, whatever the listing
     order); drafts, prereleases and tags that are not exactly `daemon-vX.Y.Z` are not candidates;
  2. only when none carries it, the newest release of any kind that does, in the API's newest-first order;
  3. the daemon tags come from `git/matching-refs` (every tag), so a daemon release past the first page of the
     releases listing is still found;
  4. the installer says which release it picked and why.

Disarm (seen red 2026-11-10): `choose` returning `carrying[0]` first (the old "newest with the file") → the engine
release wins and the order tests fail; `get.sh` scanning only the listing → its daemon-line test fails.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from daemon.update import release_line as daemon_copy
from server import daemon_release_line as server_copy

ENGINE = Path(__file__).resolve().parents[4]
GET_SH = ENGINE / "daemon" / "packaging" / "get.sh"
REPO = "asimovia/zaelar"
API = f"https://api.github.com/repos/{REPO}"
ASSETS = ("Zaelar-macos.zip", "Zaelar-macos-x86_64.zip", "zaelar-daemon-windows.exe", "update-manifest.json")


def _rel(tag: str, assets=ASSETS, **extra) -> dict:
    base = f"https://github.com/{REPO}/releases/download/{tag}"
    return {"tag_name": tag, "draft": False, "prerelease": False,
            "assets": [{"name": a, "browser_download_url": f"{base}/{a}"} for a in assets], **extra}


both = pytest.mark.parametrize("release_line", [daemon_copy, server_copy], ids=["daemon", "server"])


def test_the_two_python_copies_are_the_same_code():
    def code(mod):
        text = Path(mod.__file__).read_text(encoding="utf-8")
        return text[text.index("from __future__"):]
    assert code(daemon_copy) == code(server_copy), "daemon/update/release_line.py and server/daemon_release_line.py drifted"


def _tag(r):
    return r["tag_name"] if r else None


# ── the rule over a listing ──────────────────────────────────────────────────────────────────────────────────

@both
def test_a_daemon_release_wins_over_a_newer_engine_release(release_line):
    listing = [_rel("v3.147"), _rel("daemon-v0.3.0"), _rel("v3.146")]
    assert _tag(release_line.choose(listing, "Zaelar-macos.zip")) == "daemon-v0.3.0"


@both
def test_the_newest_daemon_release_is_chosen_by_version_not_by_listing_order(release_line):
    listing = [_rel("daemon-v0.9.0"), _rel("daemon-v0.10.0"), _rel("daemon-v0.3.0")]
    assert _tag(release_line.choose(listing, "Zaelar-macos.zip")) == "daemon-v0.10.0"


@both
def test_an_engine_release_is_used_only_when_no_daemon_release_carries_the_file(release_line):
    listing = [_rel("v3.147"), _rel("daemon-v0.3.0", assets=("Zaelar-macos.zip",)), _rel("v3.146")]
    assert _tag(release_line.choose(listing, "zaelar-daemon-windows.exe")) == "v3.147"
    assert release_line.choose([_rel("v3.147", assets=())], "Zaelar-macos.zip") is None


@pytest.mark.parametrize("odd", [_rel("daemon-v0.4.0", prerelease=True), _rel("daemon-v0.4.0", draft=True),
                                 _rel("daemon-v0.4.0-rc1"), _rel("daemon-v0.4")],
                         ids=["prerelease", "draft", "rc-suffix", "two-part"])
@both
def test_a_release_outside_the_line_is_not_a_daemon_candidate(odd, release_line):
    assert _tag(release_line.choose([odd, _rel("daemon-v0.3.0")], "Zaelar-macos.zip")) == "daemon-v0.3.0"


# ── asking GitHub: the tags first, then the listing ──────────────────────────────────────────────────────────

class Fake:
    def __init__(self, files: dict):
        self.files, self.asked = {k: json.dumps(v).encode() for k, v in files.items()}, []

    def __call__(self, url: str, **_kw) -> bytes:
        self.asked.append(url)
        if url not in self.files:
            raise OSError(f"404 {url}")
        return self.files[url]


def _refs(*tags):
    return [{"ref": f"refs/tags/{t}"} for t in tags]


@both
def test_resolve_reads_every_daemon_tag_and_skips_one_without_the_file(release_line):
    fake = Fake({f"{API}/git/matching-refs/tags/daemon-v": _refs("daemon-v0.2.0", "daemon-v0.10.0", "daemon-v0.3.0"),
                 f"{API}/releases/tags/daemon-v0.10.0": _rel("daemon-v0.10.0", assets=("zaelar-daemon-windows.exe",)),
                 f"{API}/releases/tags/daemon-v0.3.0": _rel("daemon-v0.3.0"),
                 f"{API}/releases?per_page=100": [_rel("v3.147")]})
    assert _tag(release_line.resolve(fake, REPO, "Zaelar-macos.zip")) == "daemon-v0.3.0"
    assert f"{API}/releases?per_page=100" not in fake.asked, "a daemon release was found: the listing is not read"
    assert fake.asked.index(f"{API}/releases/tags/daemon-v0.10.0") < fake.asked.index(f"{API}/releases/tags/daemon-v0.3.0")


@both
def test_resolve_falls_back_to_the_listing_when_the_tags_cannot_be_read(release_line):
    fake = Fake({f"{API}/releases?per_page=100": [_rel("v3.147"), _rel("daemon-v0.3.0")]})
    assert _tag(release_line.resolve(fake, REPO, "Zaelar-macos.zip")) == "daemon-v0.3.0"


def test_the_updater_takes_its_manifest_from_the_daemon_line():
    from daemon.update import check
    listing = [_rel("v3.147"), _rel("daemon-v0.3.0")]
    found = check.find_release(listing)
    assert found and found[0] == "daemon-v0.3.0" and found[1].endswith("/daemon-v0.3.0/update-manifest.json")


def test_the_download_screen_links_the_resolved_daemon_release(monkeypatch):
    from server import daemon_downloads as dd
    monkeypatch.setattr(dd, "_resolve_release",
                        lambda: ("daemon-v0.3.0", f"https://github.com/{REPO}/releases/download/daemon-v0.3.0"))
    monkeypatch.setattr(dd, "_read_signed", lambda base: {"macos": True} if base.endswith("/daemon-v0.3.0") else {})
    dd._refresh_signed(dd._RELEASE_BASE_DEFAULT)
    out = dd._downloads("0.3.0")
    assert out["tag"] == "daemon-v0.3.0"
    assert out["platforms"]["macos"]["artifact"] == f"https://github.com/{REPO}/releases/download/daemon-v0.3.0/Zaelar-macos.zip"
    assert out["platforms"]["macos"]["signed"] is True


# ── get.sh, run for real against a fake GitHub ───────────────────────────────────────────────────────────────

_FAKE_CURL = r'''#!/bin/bash
# A fake `curl`: serves $FAKE_GH/<url with / and : and ? replaced by _>, fails (like -f) for anything else.
out=""; url=""
while (( $# )); do case "$1" in -o) out="$2"; shift 2 ;; http*) url="$1"; shift ;; *) shift ;; esac; done
echo "$url" >> "$FAKE_GH/asked"
f="$FAKE_GH/$(printf '%s' "$url" | tr '/:?=' '____')"
[[ -f "$f" ]] || exit 22
if [[ -n "$out" ]]; then cp "$f" "$out"; else cat "$f"; fi
'''


def _get_sh(tmp_path: Path, files: dict) -> tuple[str, list[str]]:
    gh = tmp_path / "gh"
    gh.mkdir()
    for url, body in files.items():
        (gh / url.translate(str.maketrans("/:?=", "____"))).write_text(json.dumps(body))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "curl").write_text(_FAKE_CURL)
    (bin_dir / "curl").chmod(0o755)
    env = {"PATH": f"{bin_dir}:/usr/bin:/bin:/usr/sbin:/sbin", "FAKE_GH": str(gh), "HOME": str(tmp_path)}
    out = subprocess.run(["bash", str(GET_SH)], env=env, capture_output=True, text=True, timeout=60)
    asked = (gh / "asked").read_text().split() if (gh / "asked").exists() else []
    # It stops at the first file it cannot download (the sums): everything before is the choice of release.
    return out.stdout + out.stderr, asked


darwin_only = pytest.mark.skipif(sys.platform != "darwin", reason="get.sh refuses anything but macOS")


@darwin_only
def test_get_sh_installs_from_the_daemon_line_over_a_newer_engine_release(tmp_path):
    text, asked = _get_sh(tmp_path, {
        f"{API}/git/matching-refs/tags/daemon-v": _refs("daemon-v0.2.0", "daemon-v0.3.0"),
        f"{API}/releases/tags/daemon-v0.3.0": _rel("daemon-v0.3.0"),
        f"{API}/releases?per_page=100": [_rel("v3.147"), _rel("daemon-v0.3.0")]})
    assert "Zaelar Local Daemon · daemon-v0.3.0" in text, text
    assert "release: daemon-v0.3.0 (the daemon's release line)" in text, text
    assert any("/releases/download/daemon-v0.3.0/SHA256SUMS-" in u for u in asked), asked


@darwin_only
def test_get_sh_orders_daemon_tags_by_version(tmp_path):
    text, _ = _get_sh(tmp_path, {
        f"{API}/git/matching-refs/tags/daemon-v": _refs("daemon-v0.9.0", "daemon-v0.10.0"),
        f"{API}/releases/tags/daemon-v0.9.0": _rel("daemon-v0.9.0"),
        f"{API}/releases/tags/daemon-v0.10.0": _rel("daemon-v0.10.0")})
    assert "Zaelar Local Daemon · daemon-v0.10.0" in text, text


@darwin_only
def test_get_sh_skips_a_prerelease_and_falls_back_to_an_engine_release_saying_so(tmp_path):
    text, _ = _get_sh(tmp_path, {
        f"{API}/git/matching-refs/tags/daemon-v": _refs("daemon-v0.4.0"),
        f"{API}/releases/tags/daemon-v0.4.0": _rel("daemon-v0.4.0", prerelease=True),
        f"{API}/releases?per_page=100": [_rel("v3.147")]})
    assert "Zaelar Local Daemon · v3.147" in text, text
    assert "no daemon-v* release carries" in text, text


def test_get_ps1_follows_the_same_order():
    """No PowerShell here to run it (the Windows CI job parse-checks it): the order is pinned on its text."""
    ps1 = (ENGINE / "daemon" / "packaging" / "get.ps1").read_text(encoding="utf-8-sig")
    tags_at = ps1.index("/git/matching-refs/tags/daemon-v")
    listing_at = ps1.index("/releases?per_page=100")
    assert tags_at < listing_at, "the daemon tags are asked before the releases listing"
    assert "[version]" in ps1 and "-Descending" in ps1, "daemon tags sorted by version, newest first"
    assert "-not $rel.prerelease" in ps1
    assert 'Say "release: $Tag ($Picked)"' in ps1
