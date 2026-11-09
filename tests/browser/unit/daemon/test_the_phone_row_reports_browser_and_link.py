"""The phone's ☰ row for the daemon (V2-575) stays READ ONLY and adds two lines: the browser and the link, RENDERED.

The same words as the desktop settings screen (`daemon.browserLine` / `daemon.linkLine`), so the two surfaces cannot
word one state two ways; a status without those fields reads "not known", never an exception or a raw key.

Mounted at 375x812 with touch from the real MenuSheet and the shipped Spanish bundle. Disarm (seen red 2026-11-09):
the two lines removed from `MenuSheet.js` → the first test.
"""
from __future__ import annotations

import pytest

from tests.browser.unit.daemon.harness import BUNDLES, open_page

pytest.importorskip("playwright.sync_api")

_MOUNT = """async () => {
  const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = '/frontend/mobile/app/styles.css';
  document.head.append(l);
  const { MenuSheet } = await import('/frontend/mobile/app/shell/MenuSheet.js?v=2');
  document.body.append(MenuSheet());
  window.__store.setMobileMenuOpen(true);
  await window.__daemon.check();
}"""

_READ = """() => {
  const row = document.querySelector('.zm-menu .zm-row-static');
  const q = (s) => { const e = row && row.querySelector(s); return e ? e.innerText.trim() : null; };
  return {tappable: row ? (row.tagName === 'BUTTON' || !!row.onclick) : null, browser: q('.zm-daemon-browser'),
          link: q('.zm-daemon-link'), text: row ? row.innerText : ''};
}"""


def _row(server, status):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        pg = open_page(pw, server, {"status": status}, width=375, height=812, touch=True)
        pg.evaluate(_MOUNT)
        pg.wait_for_selector(".zm-menu .zm-daemon-link", timeout=5000)
        r = pg.evaluate(_READ)
        errors = list(pg._errors)
        pg._browser.close()
    return r, errors


def test_the_row_says_the_browser_and_the_relay_in_one_line_each(server):
    b = BUNDLES["es"]
    r, errors = _row(server, {
        "ok": True, "local": False, "state": "remote",
        "browser": {"state": "ready", "channel": "chrome"},
        "relay": {"paired": True, "connected": True, "since": "2026-11-09T10:15:00Z"}})
    assert r["tappable"] is False, "the phone row reports; it is not a control"
    assert r["browser"] == b["daemon.mobile.browser_line"].replace("{state}", b["daemon.browser.ready_chrome"])
    head = b["daemon.mobile.link_line"].replace("{state}", b["daemon.link.relay_since"].split("{since}")[0])
    assert r["link"].startswith(head) and len(r["link"]) > len(head) + 4, r["link"]
    assert "daemon." not in r["text"], r["text"]
    assert not errors, errors


def test_a_status_without_those_fields_reads_not_known(server):
    b = BUNDLES["es"]
    r, errors = _row(server, {"ok": True, "local": False, "state": "remote"})
    assert r["browser"] == b["daemon.mobile.browser_line"].replace("{state}", b["daemon.browser.unknown"])
    assert r["link"] == b["daemon.mobile.link_line"].replace("{state}", b["daemon.link.unknown"])
    assert not errors, errors
