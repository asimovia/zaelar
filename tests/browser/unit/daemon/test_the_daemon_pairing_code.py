"""Pairing with the cloud agent (V2-575 P3) on the daemon's settings screen, RENDERED against a mocked
`POST /api/daemon/pair`.

On a hosted engine with the relay, «Get a code» shows the one-time code big, its countdown RUNS (the text changes
second by second, and an expired code says so and drops the instructions), the menu-bar instruction, and the
command-line form in a fold. `relay_not_available` hides the card. Over loopback the engine answers
`{paired, mode: "loopback"}` and the card says it is already linked.

Disarm (seen red 2026-11-09): the countdown interval removed from `pairing.js` → `the_countdown_runs` stays frozen.
"""
from __future__ import annotations

import time

import pytest

from tests.browser.unit.daemon.harness import BUNDLES, mount_screen, open_page, read, show
from tests.waiting import until_sync

pytest.importorskip("playwright.sync_api")

_REMOTE = {"ok": True, "local": False, "state": "remote", "platform": "macos",
           "downloads": {"platforms": {"macos": {"command": "curl -fsSL x | sh"}}},
           "relay": {"paired": False, "connected": False}}


def _code(seconds: float):
    return lambda: {"ok": True, "code": "ABCD-EFGH", "expires_at": time.time() + seconds}


def test_a_code_appears_and_its_countdown_runs(server):
    from playwright.sync_api import sync_playwright
    b = BUNDLES["en"]
    api = {"status": _REMOTE, "pair": (200, _code(125))}
    with sync_playwright() as pw:
        pg = open_page(pw, server, api, lang="en")
        mount_screen(pg)
        show(pg, "link")
        pg.wait_for_selector(".dsx-ovl.on .dsx-pair-get", timeout=5000)
        assert read(pg)["pairCode"] is None, "no code before it is asked for"
        pg.click(".dsx-pair-get")
        pg.wait_for_selector(".dsx-pair-code", timeout=5000)
        r = read(pg)
        assert api["pair_hits"] == 1
        assert r["pairCode"] == "ABCD-EFGH"
        assert r["pairHow"] == b["daemon.pair.how"]
        assert r["pairCli"] is None or r["pairCli"] == "", "the CLI form is folded away until opened"
        pg.click(".dsx-pair summary")
        assert read(pg)["pairCli"] == "zaelar-daemon pair ABCD-EFGH"
        first = read(pg)["pairLeft"]
        assert first.startswith("Expires in 2:0"), first
        until_sync(lambda: read(pg)["pairLeft"] != first, "the countdown to tick", timeout_s=4)
        assert read(pg)["pairCli"] == "zaelar-daemon pair ABCD-EFGH", "a tick must not close the open fold"
        assert pg.query_selector(".dsx-pair-get").inner_text() == b["daemon.pair.again"]
        assert not pg._errors, pg._errors
        pg._browser.close()


def test_an_expired_code_says_so_and_drops_its_instructions(server):
    from playwright.sync_api import sync_playwright
    b = BUNDLES["es"]
    api = {"status": _REMOTE, "pair": (200, _code(1.5))}
    with sync_playwright() as pw:
        pg = open_page(pw, server, api)
        mount_screen(pg)
        show(pg, "link")
        pg.wait_for_selector(".dsx-ovl.on .dsx-pair-get", timeout=5000)
        pg.click(".dsx-pair-get")
        pg.wait_for_selector(".dsx-pair-code", timeout=5000)
        until_sync(lambda: read(pg)["pairLeft"] == b["daemon.pair.expired"], "the code to expire", timeout_s=5)
        r = read(pg)
        assert r["pairHow"] is None and r["pairCli"] is None, "an expired code keeps no instructions"
        assert pg.query_selector(".dsx-pair.is-expired")
        assert not pg._errors, pg._errors
        pg._browser.close()


def test_an_engine_without_the_relay_hides_the_card(server):
    from playwright.sync_api import sync_playwright
    api = {"status": _REMOTE, "pair": (409, {"ok": False, "error": "relay_not_available"})}
    with sync_playwright() as pw:
        pg = open_page(pw, server, api)
        mount_screen(pg)
        show(pg, "link")
        pg.wait_for_selector(".dsx-ovl.on .dsx-pair-get", timeout=5000)
        pg.click(".dsx-pair-get")
        until_sync(lambda: not read(pg)["pairCard"], "the pairing card to hide", timeout_s=5)
        r = read(pg)
        assert r["cards"] == [] and r["pairNone"] == BUNDLES["es"]["daemon.remote.limit"], "the tab says why, no dead card"
        assert not pg._errors, pg._errors
        pg._browser.close()


def test_over_loopback_the_card_says_it_is_already_linked(server):
    """A remote-looking status whose engine still answers `loopback` (the relay writer's local mode) is linked."""
    from playwright.sync_api import sync_playwright
    b = BUNDLES["es"]
    api = {"status": _REMOTE, "pair": (200, {"ok": True, "paired": True, "mode": "loopback", "code": None})}
    with sync_playwright() as pw:
        pg = open_page(pw, server, api)
        mount_screen(pg)
        show(pg, "link")
        pg.wait_for_selector(".dsx-ovl.on .dsx-pair-get", timeout=5000)
        pg.click(".dsx-pair-get")
        until_sync(lambda: read(pg)["pairLinked"] == b["daemon.pair.loopback"], "the linked line", timeout_s=5)
        assert read(pg)["pairCode"] is None
        assert not pg._errors, pg._errors
        pg._browser.close()
