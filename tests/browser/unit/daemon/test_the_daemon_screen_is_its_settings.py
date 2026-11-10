"""The 🖥 screen is the daemon's settings (V2-575, operator 2026-11-09), six TABS (V2-869), RENDERED in ES and EN.

Status · Install · Folders · Browser · Link · Tunnel in the subheader, Status open by default, and only the open tab's
card in the DOM; each painted from a fixture `/api/daemon/status`; a status missing every new field still paints them
in their "not known" face with no exception; a cloud engine with no paired daemon gets ONE "not linked" line and the way
forward instead of four "not known" rows; the tunnel switch is drawn disabled while the status says nothing about it
(its live face is `test_the_tunnel_switch_asks_first.py`); the install wizard ENDS on the Folders tab instead of
closing; and the 🖥 icon's colour follows the status, green for a cloud engine whose relay is connected.

Rendered in Chromium against the real DaemonSetup, TopBar-free icon state (`services/daemon.iconState`) applied to
the real `.daemonBtn` stylesheet rule, and the shipped bundles. Disarms (seen red 2026-11-09): the close-on-connect
effect restored → `test_the_wizard_ends_on_the_folders_tab`; `relayConnected()` dropped from `iconState` → the icon
test; the `browser` guard in `browserLine` removed → the missing-fields test throws.
"""
from __future__ import annotations

import re

import pytest

from tests.browser.unit.daemon.harness import BUNDLES, mount_screen, open_page, read, recheck, show
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
_TABS = ["status", "install", "folders", "browser", "link", "tunnel"]
_CARD = {"status": "status", "install": "install", "folders": "folders", "browser": "browser", "link": "pair",
         "tunnel": "tunnel"}


def _raw_keys(text: str) -> list[str]:
    return re.findall(r"\bdaemon\.[a-z_]+\.[a-z_.]+\b", text)


def _visit(pg) -> dict:
    """Every tab in turn: what each one paints, and that it is the only card in the DOM."""
    seen = {}
    for tab in _TABS:
        show(pg, tab)
        r = read(pg)
        assert r["cards"] == [_CARD[tab]] or (tab == "link" and r["cards"] == []), (tab, r["cards"])
        assert not _raw_keys(r["text"]), (tab, _raw_keys(r["text"]))
        seen[tab] = r
    return seen


@pytest.mark.parametrize("lang", ["es", "en"])
def test_six_tabs_each_paint_from_a_full_local_status(server, lang):
    from playwright.sync_api import sync_playwright
    b = BUNDLES[lang]
    with sync_playwright() as pw:
        pg = open_page(pw, server, {"status": _LOCAL}, lang=lang)
        mount_screen(pg)
        pg.wait_for_selector(".dsx-ovl.on [data-card='status'] .dsx-dot", timeout=5000)
        r = read(pg)
        assert r["tabs"] == [b["daemon.tab." + t] for t in _TABS], r["tabs"]
        assert r["tab"] == "status" and r["cards"] == ["status"], "Status is the default tab"
        assert r["title"] == b["daemon.settings.title"]
        v = _visit(pg)
        st = v["status"]
        assert st["lead"] == b["daemon.status.what"] and len(st["lead"].split()) <= 15
        assert (st["installed"], st["running"], st["version"]) == (b["daemon.status.yes"], b["daemon.status.yes"], "0.9.1")
        assert st["link"] == b["daemon.link.local"] and st["unlinked"] is None
        assert v["install"]["installedLine"] == b["daemon.install.done"].replace("{v}", "0.9.1")
        assert not v["install"]["getCard"], "no download for a local engine"
        f = v["folders"]
        assert f["folders"] == ["/Users/x/Documents", "/Users/x/Pictures"]
        assert f["defaultTag"] == b["daemon.folders.default"], "the first granted folder is marked as the default"
        assert f["foldersBody"] == b["daemon.folders.body"]
        br = v["browser"]
        assert br["browser"] == b["daemon.browser.ready_chrome"] and br["onlyChrome"] is None
        assert br["cap"] == b["daemon.cap.browser_on"]
        assert br["windowOpen"] == {"disabled": True, "tip": b["daemon.browser.window_tip"]}
        assert v["link"]["pairLinked"] == b["daemon.pair.loopback"], "a local engine says linking is for the cloud"
        assert v["link"]["pairCode"] is None
        tu = v["tunnel"]
        assert tu["tunnel"] == b["daemon.tunnel.consent"] and tu["soon"] is None
        assert tu["switchDisabled"] is True and tu["switchChecked"] is False, "no egress field: the switch is not live"
        assert tu["tunnelState"] == b["daemon.tunnel.unknown"]
        assert not pg._errors, pg._errors
        pg._browser.close()


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_cloud_engine_with_a_connected_relay_paints_the_remote_tabs(server, lang):
    from playwright.sync_api import sync_playwright
    b = BUNDLES[lang]
    with sync_playwright() as pw:
        pg = open_page(pw, server, {"status": _REMOTE}, lang=lang)
        mount_screen(pg)
        pg.wait_for_selector(".dsx-ovl.on [data-card='status'] .dsx-dot", timeout=5000)
        v = _visit(pg)
        st = v["status"]
        assert (st["installed"], st["running"], st["version"]) == (b["daemon.status.yes"], b["daemon.status.yes"], "0.9.2")
        prefix = b["daemon.link.relay_since"].split("{since}")[0]
        assert st["link"].startswith(prefix) and len(st["link"]) > len(prefix) + 4, st["link"]
        assert v["install"]["installedLine"] == b["daemon.install.done"].replace("{v}", "0.9.2")
        assert not v["install"]["getCard"], "linked: the download is gone"
        assert v["folders"]["foldersNote"] == b["daemon.folders.remote"], "paths never arrive on a cloud engine"
        br = v["browser"]
        assert br["browser"] == b["daemon.browser.downloading_pct_mb"].replace("{pct}", "43").replace("{mb}", "120")
        assert br["onlyChrome"] == b["daemon.browser.only_chrome_found"].replace("{names}", "Firefox, Safari")
        assert br["bar"] and br["track"] and abs(br["bar"] / br["track"] - 0.43) < 0.03, (br["bar"], br["track"])
        show(pg, "link")
        assert v["link"]["pairCard"] and v["link"]["pairLinked"] is None and pg.query_selector(".dsx-pair-get")
        assert not pg._errors, pg._errors
        pg._browser.close()


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_cloud_engine_with_no_paired_computer_says_so_in_one_line(server, lang):
    """Four "not known" rows say nothing; one line and the way forward (Install, or Link if it is installed)."""
    from playwright.sync_api import sync_playwright
    b = BUNDLES[lang]
    with sync_playwright() as pw:
        pg = open_page(pw, server, {"status": {**_REMOTE, "relay": {"paired": False, "connected": False}}}, lang=lang)
        mount_screen(pg)
        pg.wait_for_selector(".dsx-ovl.on .dsx-unlinked", timeout=5000)
        r = read(pg)
        assert r["unlinked"] == b["daemon.status.unlinked"]
        assert (r["installed"], r["running"], r["version"], r["link"]) == (None, None, None, None), r
        assert b["daemon.status.unknown"] not in r["text"]
        pg.click(".dsx-go-install")
        until_sync(lambda: read(pg)["tab"] == "install", "the Install tab", timeout_s=3)
        assert read(pg)["getCard"] and pg.query_selector(".dsx-cmd")
        show(pg, "status")
        pg.click(".dsx-go-link")
        until_sync(lambda: read(pg)["tab"] == "link", "the Link tab", timeout_s=3)
        assert pg.query_selector(".dsx-pair-get")
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
        pg.wait_for_selector(".dsx-ovl.on [data-card='status']", timeout=5000)
        v = _visit(pg)
        assert v["browser"]["browser"] == b["daemon.browser.unknown"], v["browser"]["browser"]
        if status["state"] == "remote":
            assert v["status"]["unlinked"] == b["daemon.status.unlinked"] and not pg.query_selector(".dsx-go-link")
            assert v["install"]["getCard"] and v["install"]["limit"] == b["daemon.remote.limit"], "the limit is said"
            assert not v["link"]["pairCard"] and v["link"]["pairNone"] == b["daemon.remote.limit"]
        else:
            assert v["status"]["version"] == b["daemon.status.unknown"]
            assert v["status"]["link"] == b["daemon.link.local"]
            assert v["install"]["installedLine"] == b["daemon.install.done_bare"]
        assert v["tunnel"]["switchDisabled"] is True
        assert not pg._errors, pg._errors
        pg._browser.close()


def test_the_wizard_ends_on_the_folders_tab_and_does_not_close(server):
    """Install → folders: opened while nothing answers, Status says so in one line and leads to Install; when the
    daemon answers the screen moves to the Folders tab and stays OPEN — and remembers that tab when reopened."""
    from playwright.sync_api import sync_playwright
    b = BUNDLES["es"]
    api = {"status": _ABSENT}
    with sync_playwright() as pw:
        pg = open_page(pw, server, api)
        mount_screen(pg)
        pg.wait_for_selector(".dsx-ovl.on .dsx-unlinked", timeout=5000)
        assert read(pg)["unlinked"] == b["daemon.local.lead"]
        pg.click(".dsx-go-install")
        until_sync(lambda: read(pg)["tab"] == "install", "the Install tab", timeout_s=3)
        r = read(pg)
        assert r["lead"] == b["daemon.local.lead"] and r["title"] == b["daemon.settings.title"], r
        assert not r["getCard"], "a self-hoster is never offered a download"
        api["status"] = _FRESH
        recheck(pg)
        until_sync(lambda: read(pg)["tab"] == "folders", "the wizard to end on Folders", timeout_s=5)
        api["status"] = {**_FRESH, "roots": ["/Users/x/Documents"], "state": "ok"}
        recheck(pg)
        until_sync(lambda: read(pg)["folders"] == ["/Users/x/Documents"], "the granted folder to appear", timeout_s=5)
        r = read(pg)
        assert r["open"], "the screen closed itself on connect — it is a settings screen and must stay"
        assert r["cards"] == ["folders"]
        pg.click(".dsx-head .dsx-icon")
        assert not read(pg)["open"], "the ✕ closes it"
        pg.evaluate("window.__store.setDaemonSetupOpen(true)")
        assert read(pg)["tab"] == "folders", "the open tab is remembered for the session"
        pg.keyboard.press("Escape")
        assert not read(pg)["open"], "Escape closes it"
        assert not pg._errors, pg._errors
        pg._browser.close()


def test_with_no_folder_the_documents_folder_is_the_suggested_default(server):
    from playwright.sync_api import sync_playwright
    b = BUNDLES["es"]
    with sync_playwright() as pw:
        pg = open_page(pw, server, {"status": _FRESH})
        mount_screen(pg)
        show(pg, "folders")
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
