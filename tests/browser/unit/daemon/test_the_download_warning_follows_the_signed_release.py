"""The 🖥 screen's «download the file yourself» fold says what the PUBLISHED release will do (V2-869 §5), RENDERED
in ES and EN against the real DaemonSetup and the shipped bundles.

  · `signed: true` for the platform shown → the signed sentence for THAT platform (no "macOS will ask you to allow
    it"), and a release that also lists its notarized `.pkg` links the package instead of the zipped app;
  · `signed: false` or unknown (`null`, an older engine that sends no field) → the unsigned sentence, unchanged —
    preparing somebody for a dialog that does not come costs nothing, promising none and showing one costs trust;
  · switching to Windows follows THAT platform's flag, not the Mac's.

Disarm (seen red 2026-11-10): the `signed === true` test in DaemonSetup.js replaced by `true` → the unsigned face
shows the signed sentence and `test_an_unsigned_or_unknown_release_keeps_the_warning` fails.
"""
from __future__ import annotations

import pytest

from tests.browser.unit.daemon.harness import BUNDLES, mount_screen, open_page, show

pytest.importorskip("playwright.sync_api")

_BASE = "https://example.invalid/releases/latest/download"


def _remote(macos: dict, windows: dict | None = None) -> dict:
    platforms = {"macos": {"command": "curl -fsSL x/get.sh | bash", "artifact": f"{_BASE}/Zaelar-macos.zip",
                           "installer": f"{_BASE}/zaelar-daemon-install-macos.sh",
                           "checksums": f"{_BASE}/SHA256SUMS-macos", **macos}}
    if windows is not None:
        platforms["windows"] = {"command": "irm x/get.ps1 | iex", "artifact": f"{_BASE}/zaelar-daemon-windows.exe",
                                "installer": f"{_BASE}/zaelar-daemon-install-windows.ps1",
                                "checksums": f"{_BASE}/SHA256SUMS-windows", **windows}
    return {"ok": True, "local": False, "installed": False, "reachable": False, "running": False, "state": "remote",
            "platform": "macos", "downloads": {"tag": "latest", "platforms": platforms}}


_FOLD = """() => {
  const p = document.querySelector('.dsx-ovl [data-signed]');
  const a = p && p.nextElementSibling.querySelector('a');
  return p ? {signed: p.dataset.signed, text: p.textContent.trim(), href: a.getAttribute('href'),
              label: a.textContent.trim()} : null;
}"""


def _fold(pg) -> dict:
    show(pg, "install")   # the download block lives in the install tab (six tabs since V2-869)
    pg.wait_for_selector(".dsx-ovl.on [data-signed]", state="attached", timeout=5000)
    return pg.evaluate(_FOLD)


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_signed_release_drops_the_allow_it_line(server, lang):
    from playwright.sync_api import sync_playwright
    b = BUNDLES[lang]
    with sync_playwright() as pw:
        pg = open_page(pw, server, {"status": _remote({"signed": True, "package": f"{_BASE}/Zaelar-macos.pkg"})},
                       lang=lang)
        mount_screen(pg)
        f = _fold(pg)
        assert f["signed"] == "yes"
        assert f["text"] == b["daemon.manual.body.signed.macos"]
        assert f["text"] != b["daemon.manual.body"]
        assert ("Privacy & Security" not in f["text"]) and ("Privacidad y seguridad" not in f["text"])
        assert f["href"].endswith("/Zaelar-macos.pkg") and f["label"] == b["daemon.manual.package"]
        assert not pg._errors, pg._errors
        pg._browser.close()


@pytest.mark.parametrize("lang", ["es", "en"])
@pytest.mark.parametrize("flag", [{"signed": False}, {"signed": None}, {}], ids=["false", "null", "absent"])
def test_an_unsigned_or_unknown_release_keeps_the_warning(server, lang, flag):
    from playwright.sync_api import sync_playwright
    b = BUNDLES[lang]
    with sync_playwright() as pw:
        pg = open_page(pw, server, {"status": _remote(flag)}, lang=lang)
        mount_screen(pg)
        f = _fold(pg)
        assert f["signed"] == "no"
        assert f["text"] == b["daemon.manual.body"]
        assert f["href"].endswith("/Zaelar-macos.zip") and f["label"] == b["daemon.manual.artifact"]
        assert not pg._errors, pg._errors
        pg._browser.close()


def test_the_sentence_follows_the_platform_shown(server):
    """A signed Mac build and an unsigned Windows one: the Windows tab keeps the Windows warning."""
    from playwright.sync_api import sync_playwright
    b = BUNDLES["en"]
    with sync_playwright() as pw:
        pg = open_page(pw, server, {"status": _remote({"signed": True}, {"signed": False})}, lang="en")
        mount_screen(pg)
        assert _fold(pg)["text"] == b["daemon.manual.body.signed.macos"]
        assert _fold(pg)["href"].endswith("/Zaelar-macos.zip"), "signed but no .pkg listed: the zip"
        show(pg, "install"); pg.click(".dsx-ovl.on .dsx-dl-btn:has-text('Windows')")
        assert _fold(pg)["text"] == b["daemon.manual.body"]
        pg._browser.close()
    with sync_playwright() as pw:
        pg = open_page(pw, server, {"status": _remote({"signed": False}, {"signed": True})}, lang="en")
        mount_screen(pg)
        show(pg, "install"); pg.click(".dsx-ovl.on .dsx-dl-btn:has-text('Windows')")
        assert _fold(pg)["text"] == b["daemon.manual.body.signed.windows"]
        assert not pg._errors, pg._errors
        pg._browser.close()
