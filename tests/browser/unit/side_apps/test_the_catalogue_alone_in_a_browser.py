"""The widget catalogue works ALONE, in a real browser: a blank page loads only `frontend/side/apps/`, mounts it with a
hand-made bridge fed real-shaped `/widgets/registry` rows, and reads what is PAINTED.

  · hidden, nothing of it is in the DOM (its System · Custom bar never sits beside the tasks tab's own);
  · shown, System holds the shipped widgets and the forked one pale with its mark; Custom holds his own and the fork;
  · a sub-tab click goes out through the bridge, and the bridge's change re-draws; a tile opens through the bridge;
  · every `show()` re-reads the catalogue (it replaces the shell's «refresh on entering the tab»);
  · its own stylesheet is loaded by the component (the customised tile is drawn in another colour).

Disarms seen red: `hide()` leaving the body in place; `show()` not reading the catalogue again.
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from tests.waiting import until_sync

ENGINE = Path(__file__).resolve().parents[4]

pytest.importorskip("playwright.sync_api")

REGISTRY = [
    {"id": "w-music", "name": "Music", "aliases": [], "surface": "user", "origin": "builtin", "forked": False},
    {"id": "w-agenda", "name": "Agenda", "aliases": [], "surface": "user", "origin": "builtin", "forked": False},
    {"id": "w-video", "name": "Video", "aliases": [], "surface": "user", "origin": "user", "forked": True},
    {"id": "w-day", "name": "My day", "aliases": [], "surface": "user", "origin": "user", "forked": False},
    {"id": "chat", "name": "Chat", "aliases": [], "surface": "system", "origin": "system"},
]

MOUNT = """async (registry) => {
  if (!document.getElementById('pal')) {          // the host's colour tokens (--hb-*); the component brings its own rules
    const l = document.createElement('link'); l.id = 'pal'; l.rel = 'stylesheet'; l.href = '/frontend/app/core/palette.css';
    document.head.append(l); await new Promise(r => { l.onload = r; l.onerror = r; }); }
  document.body.innerHTML = '<div id="h" class="cw-apps" style="display:flex;flex-direction:column;height:400px;width:340px"></div>';
  const { mount } = await import('/frontend/side/apps/apps.js');
  const seen = { loads: 0, opened: [], scopes: [] };
  let scope = 'system'; let changed = null;
  const words = { 'chat.appsSystem': 'SYS', 'chat.appsCustom': 'MINE', 'chat.appsCustomBadge': 'CUSTOM',
                  'chat.appsForkOf': 'COPY', 'chat.appsSystemEmpty': 'NONE-SYS', 'chat.appsCustomEmpty': 'NONE-MINE',
                  'chat.appsCustomizedNote': 'NOTE' };
  const tab = mount(document.getElementById('h'), {
    t: (k) => words[k] || k, icon: '<svg viewBox="0 0 10 10"><rect width="10" height="10"/></svg>',
    load: async () => { seen.loads++; return registry; },
    open: (id) => seen.opened.push(id),
    scope: () => scope,
    setScope: (id) => { seen.scopes.push(id); scope = id; changed && changed(); },
    onChange: (fn) => { changed = fn; return () => { changed = null; }; },
  });
  window.__tab = tab; window.__seen = seen;
}"""
READ = """() => ({
  bars: document.querySelectorAll('.cw-subtabs').length,
  sub: [...document.querySelectorAll('.cw-subtab')].map(b => b.textContent + (b.classList.contains('on') ? '*' : '')),
  tiles: [...document.querySelectorAll('.ap-tile')].map(t => ({ id: t.dataset.app,
    name: t.querySelector('.ap-name').textContent, pale: t.classList.contains('ap-customized'),
    badge: (t.querySelector('.ap-badge') || {}).textContent || '', meta: (t.querySelector('.ap-meta') || {}).textContent || '',
    color: getComputedStyle(t.querySelector('.ap-thumb')).color })),
  empty: (document.querySelector('.cw-empty') || {}).textContent || '' })"""


def _listening(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
        return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def browser_and_port():
    from playwright.sync_api import sync_playwright
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    until_sync(lambda: _listening(port), "the static server to accept connections", timeout_s=10)
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            yield b, port
            b.close()
    finally:
        srv.terminate(); srv.wait(timeout=10)


@pytest.fixture
def page(browser_and_port):
    br, port = browser_and_port
    pg = br.new_page(viewport={"width": 600, "height": 500})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/frontend/side/apps/apps.css", wait_until="domcontentloaded")
    pg.evaluate(MOUNT, REGISTRY)
    yield pg
    assert not errors, errors
    pg.close()


def _show(pg):
    pg.evaluate("() => window.__tab.show()")
    until_sync(lambda: pg.evaluate("() => document.querySelectorAll('.ap-tile').length") > 0, "the tiles")


def test_hidden_it_draws_nothing(page):
    assert page.evaluate("() => [...document.scripts].length") == 0, "a blank page: nothing of the app loaded"
    assert page.evaluate("() => document.getElementById('h').childElementCount") == 0
    _show(page)
    page.evaluate("() => window.__tab.hide()")
    assert page.evaluate(READ)["bars"] == 0, "hidden, its sub-tab bar must not stay in the DOM"
    assert page.evaluate("() => document.getElementById('h').childElementCount") == 0


def test_system_and_custom_paint_from_real_shaped_rows(page):
    _show(page)
    until_sync(lambda: page.evaluate("() => !!document.getElementById('side-apps-css').sheet"), "its own stylesheet")
    r = page.evaluate(READ)
    assert r["bars"] == 1 and r["sub"] == ["SYS*", "MINE"]
    tiles = {t["id"]: t for t in r["tiles"]}
    assert list(tiles) == ["w-agenda", "w-music", "w-video"], "System: shipped + forked, by name; no native surface"
    assert tiles["w-video"]["pale"] and tiles["w-video"]["badge"] == "CUSTOM"
    assert not tiles["w-music"]["pale"] and tiles["w-music"]["badge"] == ""
    assert tiles["w-video"]["color"] != tiles["w-music"]["color"], "the customised one is drawn pale by its own CSS"
    page.click(".cw-subtab:nth-child(2)")
    assert page.evaluate("() => window.__seen.scopes") == ["custom"], "the sub-tab goes out through the bridge"
    r = page.evaluate(READ)
    assert r["sub"] == ["SYS", "MINE*"]
    assert [(t["id"], t["pale"], t["meta"]) for t in r["tiles"]] == [("w-day", False, ""), ("w-video", False, "COPY")]


def test_a_tile_opens_through_the_bridge(page):
    _show(page)
    page.click(".ap-tile[data-app='w-music']")
    assert page.evaluate("() => window.__seen.opened") == ["w-music"]


def test_every_show_reads_the_catalogue_again(page):
    _show(page)
    page.evaluate("() => window.__tab.hide()")
    _show(page)
    assert page.evaluate("() => window.__seen.loads") == 2


def test_an_empty_catalogue_says_so(page):
    page.evaluate(MOUNT, [])
    page.evaluate("() => window.__tab.show()")
    until_sync(lambda: page.evaluate("() => window.__seen.loads") == 1, "the read")
    assert page.evaluate(READ)["empty"] == "NONE-SYS"


def test_unmount_leaves_nothing(page):
    _show(page)
    page.evaluate("() => window.__tab.unmount()")
    assert page.evaluate("() => document.getElementById('h').childElementCount") == 0
