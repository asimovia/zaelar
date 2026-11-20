"""The wall shows only what SOUNDED, at the instant it sounds (node 4.615, V2-941, INI-042 #49 — the operator's rule
of 2026-11-20, from his live session a9d82a54: «the wall is a faithful transcript of what is said»), in a real browser on
the real page, reading what is PAINTED.

A twelve-word reply of ours starts: nothing of it shows until its voice is heard; the voice's audio-synced captions
make it grow word by word (`heardAloud`). He cuts us at the fifth word: his line is appended at the instant his voice
rises, right under ours; ours freezes and goes final with exactly the five words that sounded — a caption that comes
late with more words never makes it grow again.

Disarms seen red: our line shown whole while live; the caption crawl removed; his line appended at his first words
after our line moved on (an insert above); a late caption growing the cut line.
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



REPLY = "Vale, mensaje a Toni Estupiña: dime qué texto quieres que le ponga ahora mismo."
WORDS = REPLY.split()


def _wall(pg, writer, op):
    pg.evaluate(ROUTE, {"kind": "wall", "label": op["op"], "writer": writer, "op": op,
                        "extra": {"writer": writer, "op": op}})


def _heard(pg, k):
    pg.evaluate("""async (t) => { const m = await import('/static/app/services/wall-bridge.js?v=1');
                                  m.heardAloud(t); }""", " ".join(WORDS[:k]))
    pg.wait_for_timeout(60)


def test_our_line_grows_as_it_sounds_and_a_cut_freezes_it_with_his_line_below(page):
    pg, _sent, errors, refused = page
    _wall(pg, "ear:holder", {"op": "append", "id": "iv_1", "role": "you", "state": "final", "text": "Mándale un mensaje"})
    _wall(pg, "mouth", {"op": "append", "id": "s_1", "role": "agent", "re": ["iv_1"], "text": REPLY, "state": "live",
                        "heard": 0})
    pg.wait_for_timeout(200)
    assert pg.evaluate(READ) == ["H: Mándale un mensaje"], "nothing of our line before its voice is heard"
    for k in range(1, 6):
        _heard(pg, k)
        assert pg.evaluate(READ)[-1] == "Z: " + " ".join(WORDS[:k]), (k, pg.evaluate(READ))
    # he cuts us: his voice rises (its line takes its place now), then ours freezes where it was heard
    _wall(pg, "ear:holder", {"op": "append", "id": "iv_2", "role": "you", "state": "pending", "text": ""})
    _wall(pg, "ear:holder", {"op": "update", "id": "iv_2", "text": "para"})
    _wall(pg, "mouth", {"op": "update", "id": "s_1", "state": "final", "heard": len(" ".join(WORDS[:5]))})
    _heard(pg, 7)                                          # a caption that comes late with more words
    pg.wait_for_timeout(200)
    lines = pg.evaluate(READ)
    assert lines == ["H: Mándale un mensaje", "Z: " + " ".join(WORDS[:5]) + "…", "H: para"], lines
    assert not errors and not refused, (errors, refused)
