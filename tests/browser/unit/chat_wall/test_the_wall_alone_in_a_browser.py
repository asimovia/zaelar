"""The chat wall works ALONE, in a real browser (INI-042 #49, the wall's plan B4, B5, B10).

A blank page that loads only `frontend/chat-wall/` — no app, no store, no engine — mounts the component and drives
it through its one interface, reading what is PAINTED:

  · B10 its four actions (append, update, replace, delete) and its three notices (submit, action, rejected) work;
  · B5 a foreign writer changes nothing: the painted wall is identical and the refusal is counted and told;
  · B4 a line keeps its node through 200 actions on the others, and a reader who scrolled up is never moved.

Disarm: the view rebuilding a line's node on update → B4 red.
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

MOUNT = """async () => {
  document.head.innerHTML = '<link rel="stylesheet" href="/frontend/chat-wall/chat-wall.css">';
  document.body.innerHTML = '<div id="m" style="height:320px;width:420px"></div>';
  const { createChatWall } = await import('/frontend/chat-wall/chat-wall.js');
  const seen = { submit: [], action: [], rejected: [] };
  const wall = createChatWall({
    mount: document.getElementById('m'), labels: { send: 'Send', placeholder: 'Type' },
    renderers: { task: (data, act) => { const b = document.createElement('button');
                                         b.className = 'task-btn'; b.textContent = 'task ' + data.v;
                                         b.onclick = () => act('open'); return b; } } });
  for (const k of Object.keys(seen)) wall.on(k, (d) => seen[k].push(d));
  window.__wall = wall; window.__seen = seen;
  window.__w = { ear: wall.writer('ear:holder'), mouth: wall.writer('mouth'), tasks: wall.writer('tasks') };
}"""
READ = """() => [...document.querySelectorAll('.cw-list > .cw-line')].filter(e => !e.hidden).map(e =>
    (e.classList.contains('cw-agent') ? 'Z: ' : e.classList.contains('cw-you') ? 'H: ' : 'B: ') + e.textContent)"""


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
    pg.goto(f"http://127.0.0.1:{port}/frontend/chat-wall/chat-wall.css", wait_until="domcontentloaded")
    pg.evaluate(MOUNT)
    yield pg
    assert not errors, errors
    pg.close()


def test_its_four_actions_and_three_notices_work_alone(page):
    pg = page
    assert pg.evaluate("() => [...document.scripts].length") == 0, "a blank page: nothing of the app loaded"
    pg.evaluate("""() => {
      __w.ear.apply({ op: 'append', id: 'iv_1', role: 'you', state: 'live', text: 'w1' });
      __w.ear.apply({ op: 'update', id: 'iv_1', text: 'w1 w2', state: 'final' });
      __w.mouth.apply({ op: 'append', id: 's_1', role: 'agent', state: 'live', text: 'w3 w4 w5', re: ['iv_1'] });
      __w.mouth.apply({ op: 'update', id: 's_1', state: 'final', heard: 5 });
      __w.tasks.apply({ op: 'append', id: 't_1', role: 'box', kind: 'task', data: { v: 1 } });
      __w.tasks.apply({ op: 'replace', id: 't_1', data: { v: 2 } });
      __w.ear.apply({ op: 'append', id: 'iv_2', role: 'you', state: 'live', text: 'w9' });
      __w.ear.apply({ op: 'delete', id: 'iv_2' });
    }""")
    assert pg.evaluate(READ) == ["H: w1 w2", "Z: w3 w4…", "B: task 2"]
    pg.fill(".cw-input", "w6 w7")
    pg.press(".cw-input", "Enter")
    until_sync(lambda: pg.evaluate("() => __seen.submit.length") == 1, "the submit notice")
    sub = pg.evaluate("() => __seen.submit[0]")
    assert sub["text"] == "w6 w7" and pg.evaluate(READ)[-1] == "H: w6 w7"
    assert pg.input_value(".cw-input") == "", "the only thing the wall does to his box is empty it on send"
    pg.click(".task-btn")
    assert pg.evaluate("() => __seen.action") == [{"id": "t_1", "action": "open"}]
    pg.evaluate("() => __w.mouth.apply({ op: 'update', id: 'iv_1', text: 'x' })")
    assert pg.evaluate("() => __seen.rejected.map(r => r.reason)") == ["not_owner"]


def test_a_foreign_writer_changes_nothing(page):
    pg = page
    pg.evaluate("""() => { __w.ear.apply({ op: 'append', id: 'iv_1', role: 'you', state: 'live', text: 'w1' });
                           __w.mouth.apply({ op: 'append', id: 's_1', role: 'agent', state: 'final', text: 'w2' }); }""")
    before = pg.evaluate("() => document.querySelector('.cw-list').innerHTML")
    pg.evaluate("""() => { __w.mouth.apply({ op: 'update', id: 'iv_1', text: 'w9' });
                           __w.ear.apply({ op: 'delete', id: 's_1' });
                           __w.tasks.apply({ op: 'append', id: 'iv_1', role: 'box', data: {} });
                           __w.ear.apply({ op: 'update', id: 'iv_1', owner: 'mouth', text: 'w8' }); }""")
    assert pg.evaluate("() => document.querySelector('.cw-list').innerHTML") == before
    assert pg.evaluate("() => __wall.counts().rejected") == 4
    assert pg.evaluate("() => __seen.rejected.map(r => r.reason)") == ["not_owner", "not_owner", "not_owner",
                                                                      "forged_owner"]


def test_a_line_keeps_its_node_and_a_reader_is_never_moved(page):
    pg = page
    pg.evaluate("""() => {
      __w.ear.apply({ op: 'append', id: 'iv_0', role: 'you', state: 'final', text: 'w0' });
      window.__node = __wall.node('iv_0');
      for (let i = 1; i <= 200; i++) {
        const id = 's_' + (i % 7);
        if (!__wall.node(id)) __w.mouth.apply({ op: 'append', id, role: 'agent', state: 'live', text: 'w' + i });
        else __w.mouth.apply({ op: 'update', id, text: 'w' + i + ' w' + i });
      }
      __w.ear.apply({ op: 'update', id: 'iv_0', text: 'never' });          // final: refused, untouched
    }""")
    assert pg.evaluate("() => __wall.node('iv_0') === __node && __node.isConnected && __node.textContent === 'w0'")
    nodes_before = pg.evaluate("() => { window.__all = [...document.querySelectorAll('.cw-line')]; return __all.length; }")
    pg.evaluate("() => { for (let i = 1; i < 7; i++) __w.mouth.apply({ op: 'update', id: 's_' + i, text: 'w' }); }")
    assert pg.evaluate("() => [...document.querySelectorAll('.cw-line')].every((e, i) => e === __all[i])"), nodes_before
    pg.evaluate("""() => { for (let i = 0; i < 40; i++) __w.ear.apply({ op: 'append', id: 'f' + i, role: 'you', text: 'line ' + i });
                           const l = document.querySelector('.cw-list'); l.scrollTop = 0; }""")
    pg.evaluate("() => { for (let i = 0; i < 5; i++) __w.mouth.apply({ op: 'append', id: 'g' + i, role: 'agent', text: 'more' }); }")
    assert pg.evaluate("() => document.querySelector('.cw-list').scrollTop") == 0, "he scrolled up to read: kept"
    pg.evaluate("() => { const l = document.querySelector('.cw-list'); l.scrollTop = l.scrollHeight; }")
    pg.evaluate("() => __w.mouth.apply({ op: 'append', id: 'h', role: 'agent', text: 'newest' })")
    assert pg.evaluate("() => { const l = document.querySelector('.cw-list'); return l.scrollHeight - l.scrollTop - l.clientHeight; }") <= 24


def test_a_restored_history_is_not_written_again(page):
    """What a reload restores is already kept: restoring it writes nothing, so the time it was kept — the divider's
    «earlier, X ago» — stays the time it was said, never the time of the reload."""
    pg = page
    got = pg.evaluate("""async () => {
      const { createChatWall } = await import('/frontend/chat-wall/chat-wall.js');
      const saves = [];
      const m = document.createElement('div'); document.body.appendChild(m);
      const w = createChatWall({ mount: m, input: false, labels: { earlier: 'earlier' }, storage: {
        load: () => [{ id: 'o1', owner: 'legacy:you', role: 'you', state: 'final', text: 'w1' }],
        save: (xs) => saves.push(xs.length) } });
      await new Promise(r => setTimeout(r, 120));
      const before = saves.length;
      w.writer('mouth').apply({ op: 'append', id: 's1', role: 'agent', state: 'final', text: 'w2' });
      await new Promise(r => setTimeout(r, 120));
      return { before, after: saves.length, divider: m.querySelectorAll('.cw-earlier').length };
    }""")
    assert got == {"before": 0, "after": 1, "divider": 1}, got
