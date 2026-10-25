"""Two screens, one agent — RENDERED (V2-792, node 4.267).

The desktop and the phone open the same engine at once, in two real browsers with their own storage, each on its
own event stream. Events are pushed through the engine's REAL stream (`voice/observer.emit` → bus → `GET /events`),
and what each screen DID is read from the page — its host's `show` calls and the chips it painted. A source-level
test cannot see the one regression this initiative exists for: «both of them played it».

  · a card asked for on the desktop opens ON THE DESKTOP, and the phone paints a chip naming the computer — and
    does not open the card;
  · the conversation reaches both: the transcript line lands on both walls;
  · a line typed on the phone, which holds no voice room, reaches the live session through `POST /api/chat` with the
    phone's device;
  · `screens/moved` takes a one-screen card away from the screen that had it;
  · a video asked for on the phone while the desktop plays one MOVES to the phone (the widget declares
    `"screens": "single"`): the desktop closes its player, the phone opens one.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

ENGINE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
DESK, PHONE = "desktop:deskaaaa", "mobile:phonebbb"

# The engine's own routers: the voice lock (it serves the LiveKit session module), pages, i18n, the event stream,
# the canvas, the screens and the widget index. Plus two
# routes that exist ONLY in this preview — one to push an event into the real stream, one to read what the typed
# door received — so the test drives the product's channel instead of a double of it.
PREVIEW = '''
import sys; sys.path.insert(0, %r)
import uvicorn
from fastapi import FastAPI, Body
from fastapi.staticfiles import StaticFiles
from server import pages, i18n_api, voice_api, canvas_api, screens_api, livekit_api
from widgets import server_api as widgets_api
from voice import observer, screens
app = FastAPI()
for r in (livekit_api.router, pages.router, i18n_api.router, voice_api.router, canvas_api.router, screens_api.router,
          widgets_api.router):
    app.include_router(r)
TYPED = []
async def _door(text, dev): TYPED.append({"text": text, "dev": dev})
screens.register_typed(_door)
@app.post("/__emit")
def _emit(ev: dict = Body(...)):
    observer.emit(ev.pop("kind"), ev.pop("label", ""), text=ev.pop("text", ""), role=ev.pop("role", ""), extra=ev)
    return {"ok": True}
@app.get("/__typed")
def _typed(): return TYPED
@app.get("/__screens")
def _screens(): return screens.open_screens()
app.mount("/static", StaticFiles(directory=%r), name="static")
uvicorn.run(app, host="127.0.0.1", port=%d, log_level="critical")
'''

SPY = """() => {
  window.__shows = [];
  const h = window.__zaelarDesktop;
  const orig = h.show.bind(h);
  h.show = (id, o) => { window.__shows.push(String(id)); return Promise.resolve(); };
  h._origShow = orig;
  return !!h;
}"""

READ = """() => {
  const painted = e => { const r = e.getBoundingClientRect(); return !!e.offsetParent && r.width > 0 && r.height > 0; };
  return {
    shows: window.__shows || [],
    chips: [...document.querySelectorAll('.ew-chip')].filter(painted).map(e => (e.textContent || '').trim()),
  };
}"""


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def _post(base, path, body):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=10).read() or b"{}")


def _get(base, path):
    return json.loads(urllib.request.urlopen(base + path, timeout=10).read() or b"null")


@pytest.fixture(scope="module")
def base():
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception:  # pragma: no cover
        pytest.skip("playwright not installed")
    port = _free_port()
    proc = subprocess.Popen([sys.executable, "-c", PREVIEW % (ENGINE, os.path.join(ENGINE, "frontend"), port)],
                            cwd=ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            # the workspace, DB and logs are the suite's temp ones (root conftest); a temp workspace
                            # has no language chosen, and the language gate would keep the agent stopped
                            env={**os.environ, "ZAELAR_LANGUAGE_GATE": "0"})
    deadline = time.time() + 60.0
    while time.time() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close(); break
        except OSError:
            time.sleep(0.5)
    else:  # pragma: no cover
        proc.terminate(); pytest.skip("preview server never came up in 60 s")
    time.sleep(1.0)
    yield f"http://127.0.0.1:{port}"
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:  # pragma: no cover
        proc.kill()


def _wait(pred, budget_s=8.0):
    end = time.time() + budget_s
    while time.time() < end:
        v = pred()
        if v:
            return v
        time.sleep(0.2)
    return pred()


@pytest.fixture(scope="module")
def seen(base):
    from playwright.sync_api import sync_playwright
    out = {"errors": []}
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, args=["--no-sandbox"])
        pages = {}
        for name, dev, path, vp in (("desk", DESK, "/", {"width": 1280, "height": 800}),
                                    ("phone", PHONE, "/m", {"width": 390, "height": 844})):
            ctx = b.new_context(viewport=vp)
            surface, did = dev.split(":")
            ctx.add_init_script(f"try{{localStorage.setItem('hb_device_id','{did}');localStorage.setItem('hb_lang','en')}}catch(_){{}}")
            pg = ctx.new_page()
            pg.on("pageerror", lambda e, n=name: out["errors"].append(f"{n}: {e}"))
            pg.goto(base + path, wait_until="domcontentloaded")
            pages[name] = pg
        for pg in pages.values():
            pg.wait_for_timeout(2500)
            pg.evaluate("() => document.querySelectorAll('.boot-ovl, .lang-onb, .lang-onb-veil, .zm-held').forEach(e=>e.remove())")
            assert pg.evaluate(SPY)
        out["registered"] = _wait(lambda: sum(1 for x in _get(base, "/__screens") if x["streams"]) >= 2
                                  and _get(base, "/__screens")) or _get(base, "/__screens")

        # 1 · the desktop asks for a document: a desktop turn, then the card
        _post(base, "/__emit", {"kind": "transcript", "label": "final", "text": "open the document", "role": "user",
                                "dev": DESK, "trace": "e2e-1"})
        _post(base, "/__emit", {"kind": "widget", "label": "show", "id": "documento", "src": "flash", "trace": "e2e-1"})
        _wait(lambda: pages["phone"].evaluate(READ)["chips"])
        out["desk_1"] = pages["desk"].evaluate(READ)
        out["phone_1"] = pages["phone"].evaluate(READ)
        out["phone_wall"] = pages["phone"].evaluate("async () => (await import('/static/app/core/store.js?v=2')).chatMsgs().map(m => m.text)")
        out["desk_wall"] = pages["desk"].evaluate("async () => (await import('/static/app/core/store.js?v=2')).chatMsgs().map(m => m.text)")

        # 2 · the phone types — it holds no voice room
        pages["phone"].evaluate("async () => (await import('/static/app/services/session.js?v=3')).sendText('make me a report')")
        out["typed"] = _wait(lambda: _get(base, "/__typed"))
        out["phone_state"] = pages["phone"].evaluate("async () => { const s = await import('/static/app/core/store.js?v=2'); return {started: s.started(), starting: s.starting(), power: s.powerOff(), agent: s.agentState()}; }")

        # 3 · a one-screen card moves to the phone: the desktop lets it go and keeps a chip
        pages["desk"].evaluate("() => { const h = window.__zaelarDesktop; h.list = () => ['youtube']; window.__closed = []; h.close = (id) => window.__closed.push(id); }")
        _post(base, "/__emit", {"kind": "screens", "label": "moved", "id": "youtube", "to": PHONE, "origin_dev": PHONE})
        out["desk_closed"] = _wait(lambda: pages["desk"].evaluate("() => window.__closed"))
        out["desk_3"] = pages["desk"].evaluate(READ)

        # 4 · the video plays on the desktop and the PHONE asks for a video: the server moves it (manifest
        #     `"screens": "single"`) — the desktop closes its player, the phone opens one
        pages["desk"].evaluate("() => { window.__closed = []; }")
        _post(base, "/__emit", {"kind": "transcript", "label": "final", "text": "put on a video of cats",
                                "role": "user", "dev": PHONE, "trace": "e2e-4"})
        _post(base, "/__emit", {"kind": "widget", "label": "show", "id": "youtube", "src": "flash", "trace": "e2e-4"})
        out["desk_closed_4"] = _wait(lambda: pages["desk"].evaluate("() => window.__closed"))
        out["phone_4"] = _wait(lambda: "youtube" in pages["phone"].evaluate(READ)["shows"]
                               and pages["phone"].evaluate(READ)) or pages["phone"].evaluate(READ)
        b.close()
    return out


def test_both_screens_are_registered_by_their_event_stream(seen):
    """By the STREAM, not only by the visibility beat: a screen whose stream is down for good is gone after
    `GONE_AFTER_S`, and only an open stream keeps it registered (its disarm: the stream without `?dev=`)."""
    streams = {s["dev"]: s["streams"] for s in seen["registered"] or []}
    assert streams.get(DESK, 0) >= 1 and streams.get(PHONE, 0) >= 1, seen["registered"]


def test_a_card_asked_on_the_desktop_opens_only_on_the_desktop(seen):
    assert "documento" in seen["desk_1"]["shows"], seen["desk_1"]
    assert "documento" not in seen["phone_1"]["shows"], seen["phone_1"]


def test_the_phone_paints_a_chip_that_names_the_computer(seen):
    chips = seen["phone_1"]["chips"]
    assert chips and any("computer" in c.lower() for c in chips), chips
    assert not seen["desk_1"]["chips"], seen["desk_1"]


def test_the_conversation_reaches_both_walls(seen):
    assert any("open the document" in str(t) for t in seen["desk_wall"]), seen["desk_wall"]
    assert any("open the document" in str(t) for t in seen["phone_wall"]), seen["phone_wall"]


def test_a_line_typed_on_the_screen_without_the_voice_reaches_the_session(seen):
    assert {"text": "make me a report", "dev": PHONE} in (seen["typed"] or []), (seen["typed"], seen.get("phone_state"))


def test_a_card_moved_to_the_phone_leaves_the_desktop_with_a_chip(seen):
    assert seen["desk_closed"] == ["youtube"], seen["desk_closed"]
    assert any("phone" in c.lower() for c in seen["desk_3"]["chips"]), seen["desk_3"]


def test_no_page_error_on_either_screen(seen):
    assert not seen["errors"], seen["errors"]


def test_a_video_asked_on_the_phone_while_the_desktop_plays_one_moves_to_the_phone(seen):
    """`"screens": "single"`: the desktop stops and closes its player, the phone opens one — never both."""
    assert seen["desk_closed_4"] == ["youtube"], seen["desk_closed_4"]
    assert "youtube" in seen["phone_4"]["shows"], seen["phone_4"]
