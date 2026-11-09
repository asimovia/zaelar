"""The 🖥 screen is the daemon's settings (V2-575, operator 2026-11-09), RENDERED in ES and EN.

Five cards in a fixed order — status · folders · browser · pairing · tunnel — each painted from a fixture
`/api/daemon/status`; a status missing every new field still paints them all in their "not known" face with no
exception; the tunnel switch is drawn disabled with its consent text while the status says nothing about it (its live
face is `test_the_tunnel_switch_asks_first.py`); the install wizard ENDS on the settings view
instead of closing; and the 🖥 icon's colour follows the status, green for a cloud engine whose relay is connected.

Rendered in Chromium against the real DaemonSetup, TopBar-free icon state (`services/daemon.iconState`) applied to
the real `.daemonBtn` stylesheet rule, and the shipped bundles. Disarms (seen red 2026-11-09): the close-on-connect
effect restored → `test_the_wizard_ends_on_the_settings_view`; `relayConnected()` dropped from `iconState` → the icon
test; the `browser` guard in `browserLine` removed → the missing-fields test throws.
"""
from __future__ import annotations

import re

import pytest

from tests.browser.unit.daemon.harness import BUNDLES, mount_screen, open_page, read, recheck
from tests.waiting import until_sync

pytest.importorskip("playwright.sync_api")

_ABSENT = {"ok": True, "local": True, "installed": False, "reachable": False, "running": False, "state": "off",
           "capabilities": [], "roots": [], "candidates": [], "platform": "macos", "downloads": {"platforms": {}}}
_LOCAL = {**_ABSENT, "installed": True, "reachable": True, "running": True, "state": "ok", "version": "0.9.1",
          "expected_version": "0.9.1", "capabilities": ["files.list", "browser.auth"],
          "roots": ["/Users/x/Documents", "/Users/x/Pictures"],
          "candidates": [{"path": "/Users/x/Desktop", "label": "Desktop", "allowed": False}],
          "browser": {"state": "ready", "channel": "chrome"}, "unsupported_browsers": []}
_FRESH = {**_LOCAL, "state": "warn", "roots": [],
          "candidates": [{"path": "/Users/x/Desktop", "label": "Desktop", "allowed": False},
                         {"path": "/Users/x/Documents", "label": "Documents", "allowed": False}]}
_REMOTE = {"ok": True, "local": False, "installed": False, "reachable": False, "running": False, "state": "remote",
           "platform": "macos", "downloads": {"platforms": {"macos": {"command": "curl -fsSL x | sh"}}},
           "browser": {"state": "downloading", "channel": "chromium", "progress": 43, "size_mb": 120},
           "unsupported_browsers": ["Firefox", "Safari"],
           "relay": {"paired": True, "connected": True, "caps": ["browser"], "version": "0.9.2",
                     "platform": "macos", "since": "2026-11-09T10:15:00Z"}}
_ORDER = ["status", "folders", "browser", "pair", "tunnel"]


def _raw_keys(text: str) -> list[str]:
    return re.findall(r"\bdaemon\.[a-z_]+\.[a-z_.]+\b", text)


@pytest.mark.parametrize("lang", ["es", "en"])
def test_every_card_paints_from_a_full_local_status(server, lang):
    from playwright.sync_api import sync_playwright
    b = BUNDLES[lang]
    with sync_playwright() as pw:
        pg = open_page(pw, server, {"status": _LOCAL}, lang=lang)
        mount_screen(pg)
        pg.wait_for_selector(".dsx-ovl.on [data-card='tunnel']", timeout=5000)
        r = read(pg)
        assert r["cards"] == _ORDER, r["cards"]
        assert r["title"] == b["daemon.settings.title"]
        assert r["lead"] == b["daemon.status.what"]
        assert (r["installed"], r["running"], r["version"]) == (b["daemon.status.yes"], b["daemon.status.yes"], "0.9.1")
        assert r["link"] == b["daemon.link.local"]
        assert r["folders"] == ["/Users/x/Documents", "/Users/x/Pictures"]
        assert r["defaultTag"] == b["daemon.folders.default"], "the first granted folder is marked as the default"
        assert r["slow"] == b["daemon.folders.slow"]
        assert r["browser"] == b["daemon.browser.ready_chrome"] and r["onlyChrome"] is None
        assert r["cap"] == b["daemon.cap.browser_on"]
        assert r["windowOpen"] == {"disabled": True, "tip": b["daemon.browser.window_tip"]}
        assert r["pairLinked"] == b["daemon.pair.loopback"], "over loopback the card says it is already linked"
        assert r["pairCode"] is None and not r["getCard"], "no code and no download for a local engine"
        assert r["tunnel"] == b["daemon.tunnel.consent"] and r["soon"] is None
        assert r["switchDisabled"] is True and r["switchChecked"] is False, "no egress field: the switch is not live"
        assert r["tunnelState"] == b["daemon.tunnel.unknown"]
        assert not _raw_keys(r["text"]), f"raw i18n keys on screen: {_raw_keys(r['text'])}"
        assert not pg._errors, pg._errors
        pg._browser.close()


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_cloud_engine_with_a_connected_relay_paints_the_remote_cards(server, lang):
    from playwright.sync_api import sync_playwright
    b = BUNDLES[lang]
    with sync_playwright() as pw:
        pg = open_page(pw, server, {"status": _REMOTE}, lang=lang)
        mount_screen(pg)
        pg.wait_for_selector(".dsx-ovl.on [data-card='tunnel']", timeout=5000)
        r = read(pg)
        assert r["cards"] == _ORDER, "linked: the download block is gone, the five cards remain"
        assert (r["installed"], r["running"], r["version"]) == (b["daemon.status.yes"], b["daemon.status.yes"], "0.9.2")
        prefix = b["daemon.link.relay_since"].split("{since}")[0]
        assert r["link"].startswith(prefix) and len(r["link"]) > len(prefix) + 4, r["link"]
        assert r["foldersNote"] == b["daemon.folders.remote"], "paths never arrive on a cloud engine — said so"
        assert r["browser"] == b["daemon.browser.downloading_pct_mb"].replace("{pct}", "43").replace("{mb}", "120")
        assert r["onlyChrome"] == b["daemon.browser.only_chrome_found"].replace("{names}", "Firefox, Safari")
        assert r["bar"] and r["track"] and abs(r["bar"] / r["track"] - 0.43) < 0.03, (r["bar"], r["track"])
        assert r["pairCard"] and r["pairLinked"] is None and pg.query_selector(".dsx-pair-get")
        assert not _raw_keys(r["text"]), _raw_keys(r["text"])
        assert not pg._errors, pg._errors
        pg._browser.close()


@pytest.mark.parametrize("status", [
    {"ok": True, "state": "ok", "reachable": True},                          # a daemon that says nothing new
    {"ok": True, "state": "remote", "local": False},                         # a cloud engine with no relay
    {"ok": True, "state": "ok", "reachable": True, "browser": "weird", "relay": 7, "unsupported_browsers": "x",
     "roots": None, "candidates": None},                                      # fields of the wrong type
], ids=["local-bare", "remote-no-relay", "wrong-types"])
def test_missing_fields_paint_unknown_and_never_throw(server, status):
    from playwright.sync_api import sync_playwright
    b = BUNDLES["es"]
    with sync_playwright() as pw:
        pg = open_page(pw, server, {"status": status})
        mount_screen(pg)
        pg.wait_for_selector(".dsx-ovl.on [data-card='tunnel']", timeout=5000)
        r = read(pg)
        assert r["browser"] == b["daemon.browser.unknown"], r["browser"]
        assert r["version"] == b["daemon.status.unknown"]
        if status["state"] == "remote":
            assert not r["pairCard"], "no relay on this engine → no pairing card"
            assert r["getCard"] and r["limit"] == b["daemon.remote.limit"], "the cloud limit is still said"
            assert r["link"] == b["daemon.link.unknown"]
        else:
            assert r["cards"] == _ORDER and r["link"] == b["daemon.link.local"]
        assert r["switchDisabled"] is True
        assert not _raw_keys(r["text"]), _raw_keys(r["text"])
        assert not pg._errors, pg._errors
        pg._browser.close()


def test_the_wizard_ends_on_the_settings_view_and_does_not_close(server):
    """Install → folders: opened while nothing answers it is the connect step; when the daemon answers it becomes the
    settings screen, folders card right after the status, and stays OPEN — it is a settings screen now."""
    from playwright.sync_api import sync_playwright
    b = BUNDLES["es"]
    api = {"status": _ABSENT}
    with sync_playwright() as pw:
        pg = open_page(pw, server, api)
        mount_screen(pg)
        pg.wait_for_selector(".dsx-ovl.on .dsx-lead", timeout=5000)
        r = read(pg)
        assert r["lead"] == b["daemon.local.lead"] and r["title"] == b["daemon.title"], r
        api["status"] = _FRESH
        recheck(pg)
        pg.wait_for_selector(".dsx-ovl [data-card='folders']", timeout=5000)
        api["status"] = {**_FRESH, "roots": ["/Users/x/Documents"], "state": "ok"}
        recheck(pg)
        until_sync(lambda: read(pg)["folders"] == ["/Users/x/Documents"], "the granted folder to appear", timeout_s=5)
        r = read(pg)
        assert r["open"], "the screen closed itself on connect — it is a settings screen and must stay"
        assert r["cards"][:2] == ["status", "folders"] and r["title"] == b["daemon.settings.title"]
        pg.click(".dsx-head .dsx-icon")
        assert not read(pg)["open"], "the ✕ closes it"
        assert not pg._errors, pg._errors
        pg._browser.close()


def test_with_no_folder_the_documents_folder_is_the_suggested_default(server):
    from playwright.sync_api import sync_playwright
    b = BUNDLES["es"]
    with sync_playwright() as pw:
        pg = open_page(pw, server, {"status": _FRESH})
        mount_screen(pg)
        pg.wait_for_selector(".dsx-ovl.on .dsx-chip", timeout=5000)
        r = read(pg)
        assert r["folders"] == [] and r["suggested"] and "Documents" in r["suggested"], r["suggested"]
        assert b["daemon.folders.default"] in r["suggested"]
        assert not pg._errors, pg._errors
        pg._browser.close()


_ICON = """async () => {
  const d = window.__daemon; await d.check();
  // A NEW element per state, classed before it is attached: `.ic` transitions its colour, and re-classing one element
  // would read the colour mid-transition.
  const old = document.getElementById('probe'); if (old) old.remove();
  const el = document.createElement('button'); el.id = 'probe'; el.textContent = '■';
  el.className = 'ic daemonBtn st-' + d.iconState(); document.body.append(el);
  const css = (v) => { const p = document.createElement('i'); p.style.color = `var(${v})`; document.body.append(p);
                       const c = getComputedStyle(p).color; p.remove(); return c; };
  return {state: d.iconState(), color: getComputedStyle(el).color,
          ok: css('--hb-ok'), warn: css('--hb-warn'), grey: css('--hb-muted-2')};
}"""


def test_the_icon_colour_follows_the_status(server):
    """Grey with nothing there, amber with no folder, green when it answers — and green on a cloud engine only once
    the relay is connected: `relay.connected || local connected`."""
    from playwright.sync_api import sync_playwright
    api = {"status": _ABSENT}
    seen = {}
    with sync_playwright() as pw:
        pg = open_page(pw, server, api)
        for name, st in [("absent", _ABSENT), ("fresh", _FRESH), ("local", _LOCAL),
                         ("remote-unlinked", {**_REMOTE, "relay": {"paired": False, "connected": False}}),
                         ("remote-no-relay", {k: v for k, v in _REMOTE.items() if k != "relay"}),
                         ("remote-linked", _REMOTE)]:
            api["status"] = st
            seen[name] = pg.evaluate(_ICON)
        assert not pg._errors, pg._errors
        pg._browser.close()
    grey, warn, ok = seen["absent"]["grey"], seen["absent"]["warn"], seen["absent"]["ok"]
    assert len({grey, warn, ok}) == 3, "the three colours are distinct"
    expect = {"absent": grey, "fresh": warn, "local": ok, "remote-unlinked": grey, "remote-no-relay": grey,
              "remote-linked": ok}
    got = {k: v["color"] for k, v in seen.items()}
    assert got == expect, {k: (seen[k]["state"], got[k], expect[k]) for k in expect if got[k] != expect[k]}
