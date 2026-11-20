"""A typed line is ONE line on the wall, whichever path answers it (node 4.614, INI-042 #49 — the wall plan's commit 3/5,
B9; the review's F3-2 and its minor on the keyboard's name), in a real browser on the real page.

He types into the composer; the page writes his line with its own id and keeps it for the engine with that id (the
outbox, `cid` — sent as `POST /api/chat` when a session is up). Then the engine announces it:

  · the switch OFF — the old path's announcement (`transcript` text-injected chat, with `cid` and `dev`): the screen
    that typed it reads it as ITS line — one line, no refusal — with nothing compared by text;
  · the switch ON — the manager's own action (`wall`, writer `keyboard:<device>` as the engine cleans the device,
    `voice.screens.clean`) is the same line: this screen's keyboard and the engine's name for it are one name;
  · mixed (B9) — a session of the manager marks the old path's events (`conv`): its spoken line written by the ear
    (`ear:<device>`) is not painted again by the old path's `transcript`, nor its live words by the `interim`.

What is read is what is PAINTED (rectangles), never only the nodes. Disarms seen red: the announcement acknowledged by
the old writer (two lines); the keyboard's writer named by the raw device (a refusal and a second line); the router's
`conv` branch removed (two lines).
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time

import pytest

ENGINE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
PREVIEW = '''
import sys; sys.path.insert(0, %r)
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from server import pages, i18n_api
app = FastAPI(); app.include_router(pages.router); app.include_router(i18n_api.router)
@app.get("/static/app/services/session.js")   # as the engine serves it on LiveKit (`server/livekit_api.py`)
def _lk(): return FileResponse(%r + "/app/services/session-lk.js", media_type="application/javascript")
app.mount("/static", StaticFiles(directory=%r), name="static")
uvicorn.run(app, host="127.0.0.1", port=%d, log_level="critical")
'''
READ = """() => [...document.querySelectorAll('.cw-list > .cw-line')].filter(e => {
    const r = e.getBoundingClientRect(); return !!e.offsetParent && r.width > 0 && r.height > 0; })
  .map(e => (e.classList.contains('cw-agent') ? 'Z: ' : e.classList.contains('cw-you') ? 'H: ' : 'B: ')
            + (e.textContent || '').trim())"""
ROUTE = """async (d) => { const sse = await import('/static/app/services/sse.js?v=6'); sse.routeEvent(window.__zaelarDesktop, d); }"""


@pytest.fixture(scope="module")
def page():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    front = os.path.join(ENGINE, "frontend")
    proc = subprocess.Popen([sys.executable, "-c", PREVIEW % (ENGINE, front, front, port)],
                            cwd=ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 30.0
    while time.time() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close(); break
        except OSError:
            time.sleep(0.5)
    else:  # pragma: no cover
        proc.terminate(); pytest.skip("preview server never came up in 30 s")
    sent: list[dict] = []
    refused: list[dict] = []
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch(headless=True, args=["--no-sandbox"])
            pg = b.new_context(viewport={"width": 1280, "height": 800}).new_page()
            errors: list[str] = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.route("**/api/chat", lambda r: (sent.append(json.loads(r.request.post_data or "{}")),
                                                r.fulfill(status=200, content_type="application/json",
                                                          body='{"ok": true}')))
            pg.route("**/api/client-log", lambda r: ((refused.append(json.loads(r.request.post_data or "{}"))
                                                      if "refused" in (r.request.post_data or "") else None),
                                                     r.fulfill(status=200, content_type="application/json", body="{}")))
            pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
            pg.wait_for_timeout(2500)
            pg.evaluate("() => document.querySelectorAll('.boot-ovl, .lang-onb, .lang-onb-veil').forEach(e=>e.remove())")
            pg.evaluate("""async () => { const s = await import('/static/app/core/store.js?v=2');
                s.setChatTab('chat'); s.setChatOpen(true); s.setAttentionMode('always');
                const { legacy } = await import('/static/app/services/wall-legacy.js?v=1'); legacy.reset(); }""")
            pg.wait_for_timeout(300)
            yield pg, sent, errors, refused
            b.close()
    finally:
        proc.terminate()


def _type(pg, sent, text):
    """He types a line: the id it has on the wall is the id the outbox keeps it with for the engine."""
    pg.fill(".cw-input textarea", text)
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(300)
    line = pg.evaluate("""(t) => { const e = [...document.querySelectorAll('.cw-list > .cw-line')]
                                    .find(n => (n.textContent || '').trim() === t); return e ? e.dataset.id : ''; }""", text)
    kept = pg.evaluate("() => JSON.parse(localStorage.getItem('hb_outbox_v1') || '[]')")
    sent_ids = [x.get("cid") for x in kept] + [x.get("cid") for x in sent]
    assert line.startswith("c_") and line in sent_ids, (line, kept, sent)
    return {"cid": line, "dev": _device(pg)}


def _device(pg) -> str:
    return pg.evaluate("async () => (await import('/static/app/services/api.js?v=2')).DEVICE")


def test_the_switch_off_announcement_is_the_same_line(page):
    pg, sent, errors, refused = page
    out = _type(pg, sent, "w1 typed")
    assert out["cid"].startswith("c_") and out["dev"] == _device(pg)
    pg.evaluate(ROUTE, {"kind": "transcript", "label": "text-injected chat", "text": "w1 typed", "role": "user",
                        "extra": {"dev": out["dev"], "cid": out["cid"]}})
    pg.wait_for_timeout(300)
    assert pg.evaluate(READ).count("H: w1 typed") == 1, pg.evaluate(READ)
    assert not errors and not refused, (errors, refused)


def test_the_managers_keyboard_is_this_screens_keyboard(page):
    """The engine names the keyboard by the device it cleaned (`voice.screens.clean`); the page by its own id. One name."""
    from voice import screens
    pg, sent, errors, refused = page
    out = _type(pg, sent, "w2 typed")
    writer = f"keyboard:{screens.clean(out['dev'])}"
    op = {"op": "append", "id": out["cid"], "role": "you", "state": "final", "text": "w2 typed"}
    pg.evaluate(ROUTE, {"kind": "wall", "label": "append", "writer": writer, "op": op,
                        "extra": {"writer": writer, "op": op}})
    pg.wait_for_timeout(300)
    assert pg.evaluate(READ).count("H: w2 typed") == 1, pg.evaluate(READ)
    assert not errors and not refused, (errors, refused)     # a second name for one keyboard is a refusal


def test_a_session_of_the_manager_is_painted_once(page):
    """B9: the manager writes his spoken line (`ear:`); the old path's marked events for it paint nothing more."""
    pg, _sent, errors, refused = page
    ear = {"op": "append", "id": "iv_77", "role": "you", "state": "pending", "text": "w3 spoken"}
    pg.evaluate(ROUTE, {"kind": "wall", "label": "append", "writer": "ear:holder", "op": ear,
                        "extra": {"writer": "ear:holder", "op": ear}})
    pg.evaluate(ROUTE, {"kind": "interim", "label": "…", "text": "w3 spoken", "role": "user", "extra": {"conv": True}})
    fin = {"op": "update", "id": "iv_77", "state": "final", "text": "w3 spoken"}
    pg.evaluate(ROUTE, {"kind": "wall", "label": "update", "writer": "ear:holder", "op": fin,
                        "extra": {"writer": "ear:holder", "op": fin}})
    pg.evaluate(ROUTE, {"kind": "transcript", "label": "🗣", "text": "w3 spoken", "role": "user",
                        "extra": {"conv": True}})
    pg.evaluate(ROUTE, {"kind": "notify", "label": "🔔 w", "text": "w4 notice", "role": "assistant",
                        "extra": {"conv": True, "key": "k9"}})
    pg.wait_for_timeout(300)
    lines = pg.evaluate(READ)
    assert lines.count("H: w3 spoken") == 1 and not any("w4 notice" in x for x in lines), lines
    assert not errors and not refused, (errors, refused)
