"""The «Procesos» column works ALONE, in a real browser.

A blank page loads only `frontend/side/procesos/` — no app, no store, no engine — and mounts it with a bridge fed
with the rows the server sends (`/api/tasks?scope=…` shapes). What is read is what is PAINTED:

  · the four sub-tabs and the ⚙ switch, labelled through the bridge's `t`, the open one marked; a click asks the
    bridge to change the scope and fetch it;
  · each scope paints its own row shape — a running row with its state pill and its process entry, a finished row
    with its ending and, only when the server kept a report, the button that reopens it (and opens the card the
    server names), a timed row with its cadence and a delete that removes it and refetches;
  · an empty list says so;
  · `show()` is entering the tab (the live set and the open sub-tab are fetched); while shown, a change of the live
    set refetches the open sub-tab, and once hidden it no longer does; `unmount()` removes it and its subscriptions.

  · a refetch that lands while he types an answer to a task's question (same rows, or rows that changed and grew)
    keeps the row's node and its answer box: the text, the focus and the caret are intact, and the send sends it.

Disarms: `show()` stops marking the column shown → the live-change refetch never happens, red; the rows rebuilt on
every render instead of kept by key → the typed answer is lost, red.
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

ROWS = {
    "live": [{"id": "a1", "session": "s1", "title": "w1 w2", "goal": "w0", "kind": "web", "state": "running",
              "visible": True, "started_at": 1700000000, "phase": "w3", "pct": 40, "mode": "now",
              "silent_s": 90, "attempts": 1},
             {"id": "a2", "title": "w4", "goal": "w4", "kind": "errand", "state": "waiting", "visible": True,
              "started_at": 1700000000, "phase": "w4", "mode": "now"}],
    "recurring": [{"id": "c1", "title": "w9", "kind": "web", "state": "pending", "mode": "recurring",
                   "schedule": {"display": "w10", "next_run": 1700600000, "type": "interval"}}],
    "scheduled": [],
}

MOUNT = """async (server) => {
  document.head.innerHTML = '<link rel="stylesheet" href="/frontend/side/procesos/procesos.css">';
  document.body.innerHTML = '<div id="m" class="cw-tasks" style="display:flex;flex-direction:column;height:480px;width:420px"></div>';
  const { mount } = await import('/frontend/side/procesos/procesos.js');
  // The smallest signal there is: a value and the callbacks that follow it.
  const sig = (v) => { const subs = new Set(); const get = () => v;
                       get.set = (x) => { v = x; for (const f of [...subs]) f(); }; get.subs = subs; return get; };
  const rows = sig({ live: [], recurring: [], scheduled: [] });
  const scope = sig('live'), showAll = sig(false), live = sig(0);
  const calls = [];
  const follow = (...sigs) => (fn) => { for (const s of sigs) s.subs.add(fn);
                                        return () => { for (const s of sigs) s.subs.delete(fn); }; };
  const bridge = {
    t: (k, p) => (p ? `${k}(${Object.values(p).join(',')})` : k), lang: () => 'en',
    rows, scope, showAll,
    setScope: (s) => { calls.push('setScope:' + s); scope.set(s); },
    setShowAll: (on) => { calls.push('setShowAll:' + on); showAll.set(on); },
    fetchScope: async (s) => { calls.push('fetch:' + s); rows.set({ ...rows(), [s]: server[s] || [] }); },
    fetchLive: () => calls.push('fetchLive'),
    reopen: async (id) => { calls.push('reopen:' + id); return { ok: true, instance: 'results::' + id }; },
    openCard: (id) => calls.push('open:' + id),
    removeScheduled: async (id) => { calls.push('remove:' + id); },
    // The process entry, shaped like the real one where it matters here: the box where he answers its question.
    entry: (key, task) => { const e = document.createElement('div'); e.className = 'pe';
                            e.dataset.key = key; e.dataset.task = task;
                            e.innerHTML = '<input class="tq-input"><button class="tq-send">send</button>';
                            e.lastChild.onclick = () => calls.push('send:' + task + ':' + e.firstChild.value);
                            return e; },
    icons: { trash: '<svg class="trash"></svg>' },
    watch: follow(rows, scope, showAll),
    onLiveChange: follow(live),
  };
  Object.assign(window, { __calls: calls, __live: live, __scope: scope, __server: server });
  window.__view = mount(document.getElementById('m'), bridge);
}"""

READ = """() => {
  const q = (s) => [...document.querySelectorAll(s)];
  return {
    subs: q('#m > .cw-subtabs > .cw-subtab').map(e => e.textContent),
    on: q('#m .cw-subtab.on').map(e => e.textContent),
    allTitle: (document.querySelector('#m .cw-subtab.all') || {}).title || '',
    rows: q('#m > .cw-tasklist > .cw-proc-row').map(r => ({
      cls: r.className, dot: r.querySelector('.cw-proc-dot').textContent,
      goal: r.querySelector('.cw-proc-goal').textContent,
      note: (r.querySelector('.cw-proc-note') || {}).textContent || '',
      meta: r.querySelector('.cw-proc-meta').textContent,
      pill: (r.querySelector('.cw-proc-tag.state') || {}).textContent || '',
      entry: (r.querySelector('.cw-proc-main > .pe') || { dataset: {} }).dataset.key || '',
      btns: [...r.querySelectorAll('.cron-btns .cron-b')].map(b => b.className + '|' + b.textContent + '|' + b.title),
    })),
    empty: (document.querySelector('#m > .cw-tasklist > .cw-empty') || {}).textContent || '',
    calls: [...__calls],
  };
}"""


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
    pg = br.new_page(viewport={"width": 600, "height": 600})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/frontend/side/procesos/procesos.css", wait_until="domcontentloaded")
    pg.evaluate(MOUNT, ROWS)
    yield pg
    assert not errors, errors
    pg.close()


def _read(pg):
    return pg.evaluate(READ)


def test_it_paints_alone_and_entering_the_tab_fetches(page):
    pg = page
    assert pg.evaluate("() => [...document.scripts].length") == 0, "a blank page: nothing of the app loaded"
    first = _read(pg)
    assert first["subs"] == ["chat.subLive", "chat.subRecurring", "chat.subScheduled", "⚙"]
    assert first["on"] == ["chat.subLive"] and first["allTitle"] == "chat.taskShowAll"
    assert first["empty"] == "chat.subLiveEmpty" and first["calls"] == []
    pg.evaluate("() => __view.show()")
    until_sync(lambda: len(_read(pg)["rows"]) == 2, "the live rows painted after show()")
    seen = _read(pg)
    assert seen["calls"][:2] == ["fetchLive", "fetch:live"], seen["calls"]
    run, wait = seen["rows"]
    assert run["cls"] == "cw-proc-row live run" and run["dot"] == "●" and run["goal"] == "w1 w2"
    assert run["note"] == "w3" and run["pill"] == "chat.running" and run["entry"] == "s1"
    assert "40%" in run["meta"] and "chat.procSilent(1 min)" in run["meta"] and "chat.procRestarted(1)" in run["meta"]
    assert wait["cls"] == "cw-proc-row live waiting" and wait["dot"] == "⏳" and wait["pill"] == "chat.waitingYou"
    assert wait["note"] == "", "a note that repeats the title is not painted twice"
    assert wait["entry"] == "a2", "no session: the entry is keyed by the row"


def test_each_sub_tab_fetches_and_paints_its_own_shape(page):
    pg = page
    pg.evaluate("() => __view.show()")
    assert pg.evaluate("() => [...document.querySelectorAll('#m .cw-subtab:not(.all)')].length") == 3, \
        "live, recurring, scheduled: an ended task is not a tab of its own (INI-078 Q-2)"
    pg.click("#m .cw-subtab:nth-child(2)")
    until_sync(lambda: any("sched" in r["cls"] for r in _read(pg)["rows"]), "the recurring rows")
    row = _read(pg)["rows"][0]
    assert row["dot"] == "⏱" and row["goal"] == "w9" and row["meta"].startswith("w10 · chat.taskNextRun(")
    assert row["btns"] == ["cron-b hb-icbtn danger||chat.delete"]
    assert pg.evaluate("() => !!document.querySelector('#m .cron-b.danger svg.trash')"), "the bridge's icon"
    n = len(_read(pg)["calls"])
    pg.click("#m .cron-b.danger")
    until_sync(lambda: _read(pg)["calls"][n:] == ["remove:c1", "fetch:recurring"], "removed, then refetched")

    pg.click("#m .cw-subtab:nth-child(3)")
    until_sync(lambda: _read(pg)["empty"] == "chat.subScheduledEmpty", "an empty list says so")

    pg.click("#m .cw-subtab.all")
    until_sync(lambda: "setShowAll:true" in _read(pg)["calls"], "the ⚙ switch")
    assert pg.evaluate("() => document.querySelector('#m .cw-subtab.all').classList.contains('on')")


def test_a_live_change_refetches_only_while_shown_and_unmount_lets_go(page):
    pg = page
    pg.evaluate("() => __view.show()")
    until_sync(lambda: "fetch:live" in _read(pg)["calls"], "the first fetch")
    n = len(_read(pg)["calls"])
    pg.evaluate("() => __live.set(1)")
    assert _read(pg)["calls"][n:] == ["fetch:live"], "a task ended while he looks: the open sub-tab is refetched"
    pg.evaluate("() => __view.hide()")
    n = len(_read(pg)["calls"])
    pg.evaluate("() => __live.set(2)")
    assert _read(pg)["calls"][n:] == [], "hidden, it does not fetch"
    pg.evaluate("() => __view.unmount()")
    assert pg.evaluate("() => document.getElementById('m').children.length") == 0
    assert pg.evaluate("() => __live.subs.size + __scope.subs.size") == 0, "its subscriptions are released"


def test_a_refetch_while_he_types_an_answer_keeps_it(page):
    """A `/api/tasks` refetch landed while he typed «Sí» into a task's question in the panel: the rows were redrawn,
    the box was replaced, and the send sent nothing. Now the row is kept by key and its entry is never rebuilt."""
    pg = page
    pg.evaluate("() => __view.show()")
    until_sync(lambda: len(_read(pg)["rows"]) == 2, "the live rows")
    box = '#m .cw-proc-row .pe[data-task="a2"] .tq-input'
    pg.click(box)
    pg.keyboard.type("Sí")
    pg.keyboard.press("ArrowLeft")
    pg.evaluate(f"() => {{ window.__box = document.querySelector('{box}'); window.__row = __box.closest('.cw-proc-row'); }}")
    pg.evaluate("() => __live.set(1)")                                     # the same rows, read again
    pg.evaluate("""() => { __server.live = [...__server.live.map(r => r.id === 'a2' ? { ...r, phase: 'w11' } : r),
                                            { id: 'a3', title: 'w12', state: 'running', started_at: 1700000000 }];
                           __live.set(2); }""")                           # …and rows that changed and grew
    until_sync(lambda: len(_read(pg)["rows"]) == 3, "the third row")
    kept = pg.evaluate("""() => ({ same: document.querySelector('#BOX') === __box && __box.isConnected,
                                   row: __row.isConnected, value: __box.value, focused: document.activeElement === __box,
                                   caret: __box.selectionStart,
                                   note: __row.querySelector('.cw-proc-note') && __row.querySelector('.cw-proc-note').textContent })"""
                       .replace("#BOX", box))
    assert kept == {"same": True, "row": True, "value": "Sí", "focused": True, "caret": 1, "note": "w11"}, kept
    pg.click('#m .cw-proc-row .pe[data-task="a2"] .tq-send')
    assert "send:a2:Sí" in _read(pg)["calls"], "the send sends what he typed"
