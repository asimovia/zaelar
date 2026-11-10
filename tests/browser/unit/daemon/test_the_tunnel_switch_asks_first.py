"""The 🖥 screen's tunnel switch (V2-836), RENDERED in ES and EN: ON is asked first, OFF is immediate, and an engine
away from his computer only shows the state and where it is switched.

  · local, capable, off: clicking the switch shows «I understand, turn it on» under the consent text and sends
    NOTHING; «Not now» takes the question away; the button sends `{enabled: true, consent: true}`;
  · local, on: the switch is checked, the line says it is carrying and how many sites; clicking sends
    `{enabled: false}` at once, with no question;
  · remote (a cloud engine): the switch shows his daemon's state, disabled, and says to use the Zaelar icon on his
    computer; nothing is ever posted from there;
  · every `daemon.tunnel.*` key the card uses exists in both bundles.

Disarm (seen red 2026-11-09): `flip` switching on directly (no asking step) → the consent case red.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.browser.unit.daemon.harness import BUNDLES, ENGINE, mount_screen, open_page, read, show
from tests.waiting import until_sync

pytest.importorskip("playwright.sync_api")

_BASE = {"ok": True, "local": True, "installed": True, "reachable": True, "running": True, "state": "ok",
         "version": "0.2.3", "expected_version": "0.2.3", "capabilities": ["files.list"], "roots": ["/Users/x/Docs"],
         "candidates": [], "platform": "macos", "downloads": {"platforms": {}},
         "browser": {"state": "ready", "channel": "chrome"}}
_OFF = {**_BASE, "egress": {"capable": True, "enabled": False, "connected": False, "hosts_last_hour": 0}}
_ON = {**_BASE, "egress": {"capable": True, "enabled": True, "connected": True, "hosts_last_hour": 4}}
_REMOTE = {"ok": True, "local": False, "state": "remote", "platform": "macos", "downloads": {"platforms": {}},
           "relay": {"paired": True, "connected": True, "caps": ["egress"], "version": "0.2.3", "platform": "macos",
                     "since": "2026-11-09T10:00:00Z"},
           "egress": {"capable": True, "enabled": True, "connected": False, "hosts_last_hour": 0}}


def _click_switch(pg):
    pg.click(".dsx-ovl.on .dsx-switch", force=True)


@pytest.mark.parametrize("lang", ["es", "en"])
def test_on_is_asked_first_and_sends_consent(server, lang):
    from playwright.sync_api import sync_playwright
    b = BUNDLES[lang]
    api = {"status": _OFF, "after_egress": lambda body: _ON if body.get("enabled") else _OFF}
    with sync_playwright() as pw:
        pg = open_page(pw, server, api, lang=lang)
        mount_screen(pg)
        show(pg, "tunnel")
        pg.wait_for_selector(".dsx-ovl.on .dsx-tunnel-state", timeout=5000)
        r = read(pg)
        assert r["switchDisabled"] is False and r["switchChecked"] is False
        assert r["tunnelState"] == b["daemon.tunnel.off"] and r["tunnel"] == b["daemon.tunnel.consent"]
        _click_switch(pg)
        pg.wait_for_selector(".dsx-tunnel-confirm", timeout=3000)
        r = read(pg)
        assert r["switchChecked"] is False, "the box shows the daemon's state, not the click"
        assert not api.get("egress_posts"), "nothing is sent before he confirms"
        assert pg.inner_text(".dsx-tunnel-confirm") == b["daemon.tunnel.confirm"]
        pg.click(".dsx-tunnel-cancel")
        until_sync(lambda: not read(pg)["tunnelAsk"], "the question to go away", timeout_s=3)
        assert not api.get("egress_posts")
        _click_switch(pg)
        pg.click(".dsx-tunnel-confirm")
        until_sync(lambda: api.get("egress_posts"), "the switch to be posted", timeout_s=3)
        assert api["egress_posts"] == [{"enabled": True, "consent": True}]
        until_sync(lambda: read(pg)["switchChecked"] is True, "the switch to show on", timeout_s=3)
        r = read(pg)
        assert r["tunnelState"] == b["daemon.tunnel.carrying"].replace("{n}", "4") and not r["tunnelAsk"]
        assert not pg._errors, pg._errors
        pg._browser.close()


def test_off_is_immediate(server):
    from playwright.sync_api import sync_playwright
    api = {"status": _ON, "after_egress": lambda body: _ON if body.get("enabled") else _OFF}
    with sync_playwright() as pw:
        pg = open_page(pw, server, api)
        mount_screen(pg)
        show(pg, "tunnel")
        pg.wait_for_selector(".dsx-ovl.on .dsx-tunnel-state", timeout=5000)
        assert read(pg)["switchChecked"] is True
        _click_switch(pg)
        until_sync(lambda: api.get("egress_posts"), "the switch to be posted", timeout_s=3)
        assert api["egress_posts"] == [{"enabled": False, "consent": False}]
        until_sync(lambda: read(pg)["switchChecked"] is False, "the switch to show off", timeout_s=3)
        assert not read(pg)["tunnelAsk"]
        pg._browser.close()


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_cloud_engine_shows_the_state_and_where_to_switch_it(server, lang):
    from playwright.sync_api import sync_playwright
    b = BUNDLES[lang]
    api = {"status": _REMOTE}
    with sync_playwright() as pw:
        pg = open_page(pw, server, api, lang=lang)
        mount_screen(pg)
        show(pg, "tunnel")
        pg.wait_for_selector(".dsx-ovl.on .dsx-tunnel-where", timeout=5000)
        r = read(pg)
        assert r["switchDisabled"] is True and r["switchChecked"] is True
        assert r["tunnelState"] == b["daemon.tunnel.waiting"] and r["tunnelWhere"] == b["daemon.tunnel.on_computer"]
        _click_switch(pg)
        pg.wait_for_timeout(300)
        assert not api.get("egress_posts") and not read(pg)["tunnelAsk"]
        pg._browser.close()


def test_every_tunnel_key_exists_in_both_bundles():
    src = (Path(ENGINE) / "frontend/app/components/daemon/cards.js").read_text(encoding="utf-8")
    keys = set(re.findall(r'"(daemon\.tunnel\.[a-z_]+)"', src))
    assert {"daemon.tunnel.confirm", "daemon.tunnel.carrying", "daemon.tunnel.on_computer"} <= keys
    for lang in ("es", "en"):
        missing = sorted(k for k in keys if k not in BUNDLES[lang])
        assert not missing, (lang, missing)
    assert "{n}" in BUNDLES["es"]["daemon.tunnel.carrying"] and "{n}" in BUNDLES["en"]["daemon.tunnel.carrying"]
