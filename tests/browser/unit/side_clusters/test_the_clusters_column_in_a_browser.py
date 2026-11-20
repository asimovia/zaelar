"""The «Clusters» column works ALONE, in a real browser (`frontend/side/clusters/`, V2-086).

A blank page loads only the component and mounts it through a bridge made here, fed with the rows the real backend
builds (`connectors.meshkore` manager's `clusters()`), and reads what is PAINTED:

  · the rows: name, dot, public badge, the status line, cluster_id, and the one button that connects or disconnects;
  · THE GATE (a security property): no «yes» is ever given by the column itself — not when the gate appears, not when
    the list changes under it, not when a row's «connect» is pressed; only his click on «yes» resolves it with true,
    and «no» with false;
  · `show()` asks for the list, the list's node survives a refresh (his scroll stays), `unmount()` leaves nothing.

The last test goes through the real bridge and the app's real store: his «yes» is the one thing that posts `{ok: true}`.

Disarms seen red: the column answering the gate itself when it appears; the bridge answering it when the store holds
one; the list rebuilt as a new node per refresh.
"""
from __future__ import annotations

import socket
import subprocess
import sys
from pathlib import Path

import pytest

from tests.waiting import until_sync

ENGINE = Path(__file__).resolve().parents[4]

pytest.importorskip("playwright.sync_api")

MOUNT = """async (rows) => {
  document.head.innerHTML = '<link rel="stylesheet" href="/frontend/side/clusters/clusters.css">';
  document.body.innerHTML = '<div id="host" style="display:flex;flex-direction:column;height:300px;width:380px"></div>';
  const { mount } = await import('/frontend/side/clusters/clusters.js');
  const state = { clusters: rows, confirm: null }, subs = new Set();
  const calls = window.__calls = { refresh: 0, connect: [], disconnect: [], resolve: [], stopped: 0 };
  const notify = () => subs.forEach((f) => f());
  window.__set = (patch) => { Object.assign(state, patch); notify(); };
  window.__col = mount(document.getElementById('host'), {
    clusters: () => state.clusters, confirm: () => state.confirm,
    t: (k, v) => (v ? `${k}(${Object.values(v).join('|')})` : k),
    watch: (fn) => { subs.add(fn); fn(); return () => { subs.delete(fn); calls.stopped++; }; },
    refresh: () => { calls.refresh++; }, connect: (n) => calls.connect.push(n), disconnect: (n) => calls.disconnect.push(n),
    resolve: (ok) => { calls.resolve.push(ok); state.confirm = null; notify(); },
  });
}"""
ROWS = """() => [...document.querySelectorAll('#host .cl-list > .cl-row')].map((r) => ({
  name: r.querySelector('.cl-name').textContent, on: r.querySelector('.cl-dot').classList.contains('on'),
  badge: !!r.querySelector('.cl-badge'), meta: r.querySelector('.cl-meta').textContent,
  id: r.querySelector('.cl-id')?.textContent || null, btn: r.querySelector('.cl-btns .cl-b').className }))"""


def _listening(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
        return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def backend_rows():
    """The rows the backend really serves: one live public cluster, one with credentials and no client."""
    import connectors.meshkore as _mk

    class _Live:
        name, cluster_id, handle = "commons", "c_abc", "h1"
        connected, public = True, True
        online, msgs_in, msgs_out = {"p1"}, 2, 3

    mp = pytest.MonkeyPatch()
    m = _mk.get_manager()
    mp.setattr(m, "_clients", {"commons": _Live()}, raising=False)
    mp.setattr("connectors.meshkore.store.load_clusters",
               lambda: {"saved": {"cluster_id": "c_x", "token": "t", "handle": "h2"}})
    try:
        rows = m.clusters()
    finally:
        mp.undo()
    assert {r["name"] for r in rows} == {"commons", "saved"}
    return sorted(rows, key=lambda r: r["name"])


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
def page(browser_and_port, backend_rows):
    br, port = browser_and_port
    pg = br.new_page(viewport={"width": 500, "height": 400})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/frontend/side/clusters/clusters.css", wait_until="domcontentloaded")
    pg.evaluate(MOUNT, backend_rows)
    yield pg
    assert not errors, errors
    pg.close()


def test_the_rows_paint_what_the_backend_serves(page):
    pg = page
    assert pg.evaluate("() => [...document.scripts].length") == 0, "a blank page: nothing of the app loaded"
    assert pg.evaluate(ROWS) == [
        {"name": "commonschat.public", "on": True, "badge": True, "id": "c_abc", "btn": "cl-b",
         "meta": "chat.connectedchat.clusterAs(h1)chat.clusterPeer(1|p1)chat.clusterMsgs(5)"},
        {"name": "saved", "on": False, "badge": False, "id": "c_x", "btn": "cl-b on",
         "meta": "chat.disconnectedchat.clusterAs(h2)chat.clusterNobodychat.clusterMsgs(0)"},
    ]
    pg.click("#host .cl-row:nth-child(1) .cl-b")
    pg.click("#host .cl-row:nth-child(2) .cl-b")
    assert pg.evaluate("() => [__calls.disconnect, __calls.connect]") == [["commons"], ["saved"]]
    pg.evaluate("() => __set({ clusters: [] })")
    assert pg.evaluate("() => document.querySelector('#host .cl-list').textContent") == "chat.clustersEmpty"


def test_only_his_yes_on_the_gate_connects(page):
    pg = page
    assert pg.evaluate("() => document.querySelector('#host .cl-confirm')") is None, "no gate with nothing pending"
    pg.evaluate("() => __set({ confirm: { question: 'Connect to commons?' } })")
    gate = pg.evaluate("""() => { const g = document.querySelector('#host .cl-confirm');
      return { first: g === document.getElementById('host').firstElementChild, q: g.querySelector('.cl-q').textContent,
               btns: [...g.querySelectorAll('.cl-cbtns .cl-b')].map((b) => [b.className, b.textContent]) }; }""")
    assert gate == {"first": True, "q": "Connect to commons?",
                    "btns": [["cl-b on", "chat.yesConnect"], ["cl-b", "chat.no"]]}
    # nothing the column does by itself answers it: a refresh of the list, a row's own «connect», showing it again
    pg.evaluate("() => { __set({ clusters: [{ name: 'n2' }] }); __col.show(); }")
    pg.click("#host .cl-row .cl-b.on")
    pg.evaluate("() => __set({ confirm: { question: 'Connect to commons?' } })")
    assert pg.evaluate("() => [__calls.resolve, __calls.connect]") == [[], ["n2"]]
    pg.click("#host .cl-confirm .cl-b:not(.on)")
    assert pg.evaluate("() => __calls.resolve") == [False]
    assert pg.evaluate("() => document.querySelector('#host .cl-confirm')") is None, "answered: the gate leaves"
    pg.evaluate("() => __set({ confirm: {} })")
    assert pg.evaluate("() => document.querySelector('#host .cl-q').textContent") == "chat.clusterConfirmQ"
    pg.click("#host .cl-confirm .cl-b.on")
    assert pg.evaluate("() => __calls.resolve") == [False, True]


def test_show_asks_for_the_list_and_unmount_leaves_nothing(page):
    pg = page
    assert pg.evaluate("() => __calls.refresh") == 0, "mounting asks for nothing"
    pg.evaluate("() => { window.__list = document.querySelector('#host .cl-list'); __col.show(); }")
    assert pg.evaluate("() => __calls.refresh") == 1
    pg.evaluate("() => { __set({ clusters: [{ name: 'n1' }] }); __col.hide(); }")
    assert pg.evaluate("() => document.querySelector('#host .cl-list') === __list"), "a refresh keeps the list's node"
    pg.evaluate("() => __col.unmount()")
    assert pg.evaluate("() => [document.getElementById('host').childNodes.length, __calls.stopped]") == [0, 1]


def test_the_real_bridge_wires_the_gate_to_the_store(browser_and_port, backend_rows):
    """Through `services/clusters-bridge.js` and the app's real store: a pending connect paints the gate, nothing is
    posted until his click, and his «yes» posts `{ok: true}` to the backend's one confirm door, then reads the list."""
    br, port = browser_and_port
    pg = br.new_page()
    errors: list[str] = []
    posts: list[tuple[str, str | None]] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.route("**/api/**", lambda r: (posts.append((r.request.url.split("/api/")[1], r.request.post_data)),
                                     r.fulfill(status=200, body='{"clusters": []}', content_type="application/json")))
    try:
        pg.goto(f"http://127.0.0.1:{port}/frontend/side/clusters/clusters.css", wait_until="domcontentloaded")
        pg.evaluate("""async (rows) => {
          document.body.innerHTML = '<div id="host" class="cw-clusters"></div>';
          const store = await import('/frontend/app/core/store.js?v=2');
          const { mountClusters } = await import('/frontend/app/services/clusters-bridge.js?v=1');
          window.__col = mountClusters(document.getElementById('host'));
          store.setClusters(rows); store.setClusterConfirm({ question: 'Connect to commons?' }); }""", backend_rows)
        assert pg.evaluate("() => document.querySelector('#host .cl-confirm .cl-q').textContent") == "Connect to commons?"
        assert pg.evaluate("() => document.querySelectorAll('#host .cl-row').length") == 2
        assert posts == [], "nothing reaches the backend before his answer"
        pg.click("#host .cl-confirm .cl-b.on")
        until_sync(lambda: pg.wait_for_timeout(20) or len(posts) >= 2, "the confirm and the refresh")   # the wait pumps the routes
        assert posts[:2] == [("meshkore/confirm", '{"ok":true}'), ("meshkore/status", None)]
        assert pg.evaluate("() => document.querySelector('#host .cl-confirm')") is None
        assert not errors, errors
    finally:
        pg.close()
