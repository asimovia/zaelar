"""The bridge paints a session of the manager on the wall component, in a real browser (INI-042 #49, the wall plan
B1, B2, B6 — commit 2/5, not mounted in the app yet).

The events are what the host's real adapter (`nucleo/conversation_host/wall.py`) puts on the bus for two dictated
phrases and our reply to them; a blank page loads only the bridge (`services/wall-bridge.js`) and the component, routes
the events through `bridge.route`, and reads what is PAINTED:

  · B1 two dictated phrases are two lines — the first one's node and words intact while the second is said;
  · B2 our reply is below the lines it answers;
  · B6 a reply cut by his voice ends where the voice ended, with «…»; what did not sound is never painted.
A typed line goes out with the component's own id, and the engine's acknowledgement of it is the same line.

Disarm: the adapter's live updates written as appends → B1 red (refused and counted; the line stops at its first word).
"""
from __future__ import annotations

import asyncio
import socket
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.waiting import until_sync

ENGINE = Path(__file__).resolve().parents[4]

pytest.importorskip("playwright.sync_api")

READ = """() => [...document.querySelectorAll('.cw-list > .cw-line')].filter(e => !e.hidden).map(e =>
    (e.classList.contains('cw-agent') ? 'Z: ' : 'H: ') + e.textContent)"""


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


def _events(monkeypatch) -> list[dict]:
    """In a thread of its own: Playwright's sync API holds an event loop in this one, and the mouth runs its own."""
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(1) as pool:
        return pool.submit(_run, monkeypatch).result(timeout=60)


def _run(monkeypatch) -> list[dict]:
    """The host's adapter, for real: two phrases on `holder`, then our reply, cut after «w1 w2». What the stream got."""
    from bus import sse
    from conversation.mouth import SayEnded, SayStarted
    from nucleo.conversation_host import wall
    from nucleo.conversation_host.mouth import WallMouth
    got = []
    monkeypatch.setattr(sse, "publish", lambda ev: got.append(dict(ev)))
    wall._reset_for_tests()
    for iv, parts in (("iv_1", ["Show", "Show me", "Show me the agenda"]), ("iv_2", ["for", "for tomorrow"])):
        wall.listen("conv_ear", "opened", {"refs": {"iv": iv, "endpoint": "holder", "channel": "voice"}})
        for words in parts:
            wall.heard("holder", 1, words)
        wall.listen("conv_inbox", "accepted", {"kind": "user.utterance", "text": parts[-1],
                                               "refs": {"iv": iv, "endpoint": "holder", "channel": "voice"}})

    class Voice:
        def speak(self, order, ack):
            self.ack = ack
            return True
    v = Voice()
    m = WallMouth(SimpleNamespace(now_ms=lambda: 5), voice=v, ack_later=lambda s: None)
    asyncio.run(m.say(SimpleNamespace(say_id="s_1", text="w1 w2 w3 w4", channels=frozenset({"voice"}),
                                      endpoint="holder", request_id="r_iv_2", notice_key=None)))
    v.ack(SayStarted("s_1", 1))
    v.ack(SayEnded("s_1", "cut", 5, 2, "holder"))
    wall._reset_for_tests()
    return [e for e in got if e.get("kind") == "wall"]


@pytest.fixture
def page(browser_and_port):
    br, port = browser_and_port
    pg = br.new_page(viewport={"width": 600, "height": 500})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/frontend/chat-wall/chat-wall.css", wait_until="domcontentloaded")
    pg.evaluate("""async () => {
      document.head.innerHTML = '<link rel="stylesheet" href="/frontend/chat-wall/chat-wall.css">';
      document.body.innerHTML = '<div id="m" style="height:320px;width:420px"></div>';
      const { createWallBridge } = await import('/frontend/app/services/wall-bridge.js');
      window.__sent = [];
      window.__bridge = createWallBridge({ mount: document.getElementById('m'), device: 'desktop:d1',
                                           send: (text, id) => __sent.push({ text, id }) });
    }""")
    yield pg
    assert not errors, errors
    pg.close()


def test_two_phrases_are_two_lines_and_our_reply_is_below_them_as_it_sounded(page, monkeypatch):
    pg = page
    events = _events(monkeypatch)
    first_done = next(i for i, e in enumerate(events) if e["op"]["id"] == "iv_2")
    pg.evaluate("(evs) => evs.forEach(d => __bridge.route(d))", events[:first_done + 1])
    pg.evaluate("() => { window.__first = __bridge.wall.node('iv_1'); }")
    pg.evaluate("(evs) => evs.forEach(d => __bridge.route(d))", events[first_done + 1:])
    assert pg.evaluate(READ) == ["H: Show me the agenda", "H: for tomorrow", "Z: w1 w2…"]
    assert pg.evaluate("() => __bridge.wall.node('iv_1') === __first && __first.textContent === 'Show me the agenda'")
    assert pg.evaluate("() => __bridge.wall.counts()") == {"rejected": 0, "cause_missing": 0, "trimmed": 0}


def test_a_typed_line_goes_out_with_its_id_and_its_acknowledgement_is_the_same_line(page):
    pg = page
    pg.fill(".cw-input", "w7")
    pg.press(".cw-input", "Enter")
    sent = pg.evaluate("() => __sent")
    assert [s["text"] for s in sent] == ["w7"] and sent[0]["id"].startswith("c_")
    ack = {"kind": "wall", "writer": "keyboard:desktop:d1",
           "op": {"op": "append", "id": sent[0]["id"], "role": "you", "state": "final", "text": "w7"}}
    pg.evaluate("(d) => __bridge.route(d)", ack)
    assert pg.evaluate(READ) == ["H: w7"] and pg.evaluate("() => __bridge.wall.counts().rejected") == 0


def test_a_line_of_his_no_writer_closed_is_swept_and_a_refusal_is_reported(page):
    """The review's minor: a line of his left open (its closing event lost) is deleted after `STALE_MS` with no news —
    never a final one; and every refused action reaches the host's report, with the wall's counts by reason (the
    debug stream, where `final_grows` is read)."""
    pg = page
    pg.evaluate("""async () => {
      document.body.innerHTML = '<div id="m2" style="height:320px;width:420px"></div>';
      const { createWallBridge, STALE_MS } = await import('/frontend/app/services/wall-bridge.js');
      window.__now = 1000; window.__reports = [];
      __bridge.destroy();
      window.__bridge = createWallBridge({ mount: document.getElementById('m2'), device: 'desktop:d1',
        now: () => __now, report: (r, c) => __reports.push([r.reason, c]) });
      const ap = (id, state) => __bridge.route({ kind: 'wall', writer: 'ear:holder',
                                                 op: { op: 'append', id, role: 'you', state, text: 'w1' } });
      ap('iv_1', 'pending'); ap('iv_2', 'final');
      __now += STALE_MS - 1; __bridge.sweep();
      window.__before = __bridge.wall.lines().map(l => l.id);
      __now += 2; __bridge.sweep();
      __bridge.route({ kind: 'wall', writer: 'mouth', op: { op: 'append', id: 's_1', role: 'agent', state: 'final', text: 'w2' } });
      __bridge.route({ kind: 'wall', writer: 'mouth', op: { op: 'update', id: 's_1', heard: 9 } });
    }""")
    assert pg.evaluate("() => __before") == ["iv_1", "iv_2"]
    assert pg.evaluate("() => __bridge.wall.lines().map(l => l.id)") == ["iv_2", "s_1"]
    reports = pg.evaluate("() => __reports")
    assert [r for r, _c in reports] == ["final_grows"] and reports[0][1]["final_grows"] == 1


def test_a_replace_that_carries_its_role_appends_on_a_screen_that_lacks_the_line(page):
    """INI-078 (the wall of one writer): the engine writes an errand's box (`wall_notes.ref`) once for every screen —
    appended at its first event, replaced at every later one. A screen that opened after the first (or was cleared)
    has no box to replace: a `replace` that carries its line's role appends it there, with no refusal; on a screen
    that has it, it replaces in place — one box, never two. Disarm: the bridge's upsert off → the late screen has no
    box and a `no_line` refusal is reported."""
    pg = page
    pg.evaluate("""async () => {
      document.body.innerHTML = '<div id="m3" style="height:320px;width:420px"></div>';
      const { createWallBridge } = await import('/frontend/app/services/wall-bridge.js');
      window.__reports = [];
      __bridge.destroy();
      window.__bridge = createWallBridge({ mount: document.getElementById('m3'), device: 'desktop:d1',
                                           report: (r) => __reports.push(r.reason) });
      const box = (op, state) => __bridge.route({ kind: 'wall', writer: 'ref', op: { op, id: 'ref_R1', role: 'box',
          kind: 'ref', text: 'w1', data: { role: 'ref', ref: 'R1', text: 'w1', surface: '', card: '', state, file: '' } } });
      box('replace', 'done');                  // this screen never saw the box open
      window.__late = __bridge.wall.lines().map(l => [l.id, l.role, l.kind, l.data.state]);
      box('replace', 'partial');
      window.__after = __bridge.wall.lines().map(l => [l.id, l.data.state]);
    }""")
    assert pg.evaluate("() => __late") == [["ref_R1", "box", "ref", "done"]]
    assert pg.evaluate("() => __after") == [["ref_R1", "partial"]]
    assert pg.evaluate("() => __reports") == []
