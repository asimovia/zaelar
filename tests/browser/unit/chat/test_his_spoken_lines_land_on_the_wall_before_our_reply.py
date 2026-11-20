"""His spoken lines land on the RENDERED wall, each committed, in order, before our reply (V2-941, INI-042 #48).

In a session of the conversation manager the wall showed his speech only as the dashed live caption: each new phrase
replaced the last one there, none became a bubble, and our replies stacked above it. The wall is fed by the rows the
old turn wrote (`transcript` 🗣 + the directed verdict that releases it); the manager wrote neither. This drives the
REAL manager (the package with its scripted model, the host's `wall_lines` listener and its `WallMouth`) through two
spoken phrases, takes every event as it reaches the bus — the dicts the SSE stream sends — and replays them through
the production router (`sse.routeEvent`) into the real store and the real ChatWall in Chromium, then reads the DOM:
two bubbles of his, in order, the caption gone, then ours.

Ours (plan v3.2 C2/C4): said, our line is owed until the voice the body replays starts it with the line's trace, and
its end leaves on the wall what sounded.

Disarms: take `wall_lines.listen` off the manager's telemetry → his lines never become bubbles (red); the line's trace
not adopted at its start → ours is never painted by its voice (red).
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.waiting import until_sync

ENGINE = Path(__file__).resolve().parents[4]
_EN = json.loads((ENGINE / "i18n/genesis/en/ui.json").read_text(encoding="utf-8"))

pytest.importorskip("playwright.sync_api")

READ = """() => [...document.querySelectorAll('#chatwall .cw-list > *')].map(e =>
    e.classList.contains('cw-earlier') ? '--' : (e.classList.contains('agent') ? 'Z: ' : 'H: ')
      + (e.textContent || '').trim())"""


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


def _events(monkeypatch, wired: bool = True, voiced: bool = False) -> list[dict]:
    """Two spoken phrases through the real manager, in a voice session of it: what reaches the bus, in order. In a
    thread of its own: Playwright's sync API holds an event loop in this one, and the manager runs its own."""
    import concurrent.futures
    from voice import remote_session  # noqa: F401 — its plugins register on the main thread only
    from voice.engine.pipeline import agent_events  # noqa: F401
    with concurrent.futures.ThreadPoolExecutor(1) as pool:
        return pool.submit(_run, monkeypatch, wired, voiced).result(timeout=60)


class _Voice:
    """The voice half as the body sees it: the line starts, the voice process says it speaks, the line is cut."""

    def __init__(self):
        self.acks = []

    def speak(self, order, ack):
        self.acks.append((order, ack))
        return True


def _run(monkeypatch, wired: bool, voiced: bool = False) -> list[dict]:
    import bus
    from conversation.ports import Done
    from conversation.store import MemoryStore
    from conversation.testing.scripted_model import reply
    from nucleo.conversation_host import switch, wall_lines
    from nucleo.conversation_host.mouth import WallMouth
    from tests.conversation.unit.convkit import Harness
    from voice import remote_session as rs
    got: list[dict] = []
    real = bus.emit_sync
    monkeypatch.setattr(bus, "emit_sync", lambda topic, ev, *a, **k:
                        got.append(dict(ev)) if topic == "observer" else real(topic, ev, *a, **k))
    monkeypatch.setitem(rs._M, "session", SimpleNamespace(_conversation_switch=switch.Decision(True, "voice")))
    h = Harness(MemoryStore())
    if wired:
        port = h.tel.emit
        h.tel.emit = lambda k, lab, p: (port(k, lab, p), wall_lines.listen(k, lab, p))
    voice = _Voice() if voiced else None
    mouth = WallMouth(h.clock, voice=voice, ack_later=h.conv.ack)
    mouth.ack = h.conv.ack
    h.mouth.say = mouth.say
    h.model.default = lambda ids: [reply("Here it is."), Done()]
    rs.handle({"k": "transcript", "final": False, "text": "Show me"})            # the provider's live caption
    h.utter([(["Show", "me", "the", "agenda"], 0)])
    rs.handle({"k": "transcript", "final": False, "text": "for"})
    h.utter([(["for", "tomorrow"], 0)], at=h.clock.mono + 50)
    h.settle(9000)
    if voiced:                                # our line sounds, the voice says so, and it is cut after «Here»
        from conversation.mouth import SayEnded, SayStarted
        order, ack = voice.acks[0]
        ack(SayStarted(order.say_id, 0))
        rs.handle({"k": "state", "state": "speaking"})
        ack(SayEnded(order.say_id, "cut", 4, 0, order.endpoint))
        rs.handle({"k": "state", "state": "listening"})
    return [e for e in got if e.get("kind") in ("transcript", "interim", "ambient", "brain", "bot_speech")]


def _page(browser, port):
    pg = browser.new_page(viewport={"width": 1280, "height": 800})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
    pg.route("**/api/i18n/bundle/*", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps({"strings": _EN})))
    pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
    pg.evaluate("""async () => {
        localStorage.clear();
        for (const h of ['/frontend/app/core/palette.css', '/frontend/app/styles.css']) {
          const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = h; document.head.append(l); }
        const i18n = await import('/frontend/app/core/i18n.js?v=1');
        await i18n.loadBundle('en'); if (i18n.applyLang) await i18n.applyLang('en');
        const store = await import('/frontend/app/core/store.js?v=2');
        const wall = await import('/frontend/app/components/ChatWall.js?v=5');
        window.__sse = await import('/frontend/app/services/sse.js?v=2');
        document.body.append(wall.ChatWall());
        window.__store = store;
        store.setAttentionMode('smart');            // there IS a gate: every spoken turn waits for its verdict
        store.openChatFrom('orb'); store.setChatTab('chat');
    }""")
    pg.wait_for_selector("#chatwall.open", timeout=5000)
    pg._errors = errors
    return pg


def _replay(pg, events):
    pg.evaluate("(evs) => evs.forEach(d => window.__sse.routeEvent(null, d))", events)


def test_two_spoken_phrases_are_two_bubbles_in_order_before_our_reply(browser_and_port, monkeypatch):
    br, port = browser_and_port
    events = _events(monkeypatch)
    pg = _page(br, port)
    _replay(pg, events)
    want = ["H: Show me the agenda", "H: for tomorrow"]
    until_sync(lambda: pg.evaluate(READ)[:2] == want, f"his two lines committed in order: {pg.evaluate(READ)}")
    rows = pg.evaluate(READ)
    assert rows[2:] and all(r == "Z: Here it is." for r in rows[2:]), rows
    assert pg.evaluate("() => window.__store.liveChat()") == "", "the live caption is gone once his line is committed"
    assert not pg._errors, pg._errors
    pg.close()


def test_unwired_his_lines_never_become_bubbles(browser_and_port, monkeypatch):
    """The failure the operator saw, reproduced: without the listener his lines stay a caption."""
    br, port = browser_and_port
    pg = _page(br, port)
    _replay(pg, _events(monkeypatch, wired=False))
    until_sync(lambda: "Z: Here it is." in pg.evaluate(READ), "our reply lands")
    assert not [r for r in pg.evaluate(READ) if r.startswith("H: ")]
    pg.close()


def test_our_said_line_is_painted_when_its_voice_starts_and_kept_to_what_sounded(browser_and_port, monkeypatch):
    """C2/C4: said, our line is owed until the voice the body replays starts it (with the line's trace), and its end
    leaves on the wall what sounded — below his two lines."""
    br, port = browser_and_port
    events = _events(monkeypatch, voiced=True)
    kinds = [(e["kind"], e.get("role") or e.get("label")) for e in events if e["kind"] in ("brain", "transcript")]
    assert kinds[-2:] == [("brain", "assistant"), ("transcript", "assistant")], kinds
    pg = _page(br, port)
    owed = next(i for i, e in enumerate(events) if e["kind"] == "brain") + 1
    _replay(pg, events[:owed])
    until_sync(lambda: pg.evaluate(READ) == ["H: Show me the agenda", "H: for tomorrow"], "his lines")
    pg.wait_for_timeout(300)
    assert pg.evaluate(READ) == ["H: Show me the agenda", "H: for tomorrow"], "owed, not painted before its voice"
    _replay(pg, events[owed:])
    until_sync(lambda: pg.evaluate(READ) == ["H: Show me the agenda", "H: for tomorrow", "Z: Here…"],
               f"his two lines, then ours as it sounded: {pg.evaluate(READ)}")
    assert not pg._errors, pg._errors
    pg.close()
