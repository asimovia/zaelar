"""The browser download's progress on the daemon's settings screen (V2-575), RENDERED from POLLED fixtures.

While `browser.state === "downloading"` the status is asked for every 2 s with nobody pressing anything, and the
bar and its sentence follow each answer (10 % → 43 %); the first answer that is not `downloading` ends the fast
poll — Chrome found, and no more requests than the slow 20 s poll would make. The folder field the person is
typing in survives the repaints.

Disarm (seen red 2026-11-09): `_armDownloadPoll` made a no-op → the second fixture never arrives.
"""
from __future__ import annotations

import pytest

from tests.browser.unit.daemon.harness import BUNDLES, mount_screen, open_page, read, show
from tests.waiting import until_sync

pytest.importorskip("playwright.sync_api")

_BASE = {"ok": True, "local": True, "installed": True, "reachable": True, "running": True, "state": "ok",
         "version": "0.9.1", "capabilities": ["files.list"], "roots": ["/Users/x/Documents"], "candidates": [],
         "platform": "macos", "downloads": {"platforms": {}}, "unsupported_browsers": []}


def _st(browser):
    return {**_BASE, "browser": browser}


def test_the_progress_follows_two_polls_and_the_poll_stops_when_done(server):
    from playwright.sync_api import sync_playwright
    b = BUNDLES["en"]
    seq = [_st({"state": "downloading", "channel": "chromium", "progress": 0.10, "size_mb": 120}),
           _st({"state": "downloading", "channel": "chromium", "progress": 43, "size_mb": 120}),
           _st({"state": "ready", "channel": "chrome"})]
    # The test moves the engine's answer forward; only the screen's own poll can bring it to the page (the slow
    # poll is 20 s away, and nothing here calls `check()` after the mount).
    api = {"status": seq[0]}
    line = lambda pct: b["daemon.browser.downloading_pct_mb"].replace("{pct}", str(pct)).replace("{mb}", "120")
    with sync_playwright() as pw:
        pg = open_page(pw, server, api, lang="en")
        mount_screen(pg)
        show(pg, "folders")
        pg.fill(".dsx-input", "/Users/x/half-typed")
        show(pg, "browser")
        pg.wait_for_selector(".dsx-ovl.on .dsx-progress-bar", timeout=5000)
        r = read(pg)
        assert r["browser"] == line(10), r["browser"]
        assert abs(r["bar"] / r["track"] - 0.10) < 0.03
        api["status"] = seq[1]
        until_sync(lambda: read(pg)["browser"] == line(43), "the second poll (2 s) without a click", timeout_s=4)
        until_sync(lambda: abs(read(pg)["bar"] / read(pg)["track"] - 0.43) < 0.03, "the bar to follow", timeout_s=2)
        api["status"] = seq[2]
        until_sync(lambda: read(pg)["browser"] == b["daemon.browser.ready_chrome"], "the download to end", timeout_s=4)
        assert read(pg)["bar"] is None, "no progress bar once the browser is ready"
        hits = api["hits"]
        # `wait_for_timeout`, not `time.sleep`: the sync API serves routes only while Playwright is driven, so a
        # sleep would leave a stray poll unanswered — and uncounted — until after the assertion.
        pg.wait_for_timeout(4500)
        assert api["hits"] == hits, f"the fast poll kept going after the download ended ({api['hits'] - hits} more)"
        show(pg, "folders")
        assert pg.input_value(".dsx-input") == "/Users/x/half-typed", "a repaint or a tab switch wiped the typed folder"
        assert not pg._errors, pg._errors
        pg._browser.close()


def test_a_download_with_no_known_progress_draws_an_indeterminate_bar(server):
    from playwright.sync_api import sync_playwright
    b = BUNDLES["es"]
    with sync_playwright() as pw:
        pg = open_page(pw, server, {"status": _st({"state": "downloading"})})
        mount_screen(pg)
        show(pg, "browser")
        pg.wait_for_selector(".dsx-ovl.on .dsx-progress.is-indeterminate", timeout=5000)
        assert read(pg)["browser"] == b["daemon.browser.downloading"]
        assert not pg._errors, pg._errors
        pg._browser.close()
