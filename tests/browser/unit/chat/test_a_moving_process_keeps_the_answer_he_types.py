"""A process that moves while he types the answer to its question keeps his answer box.

The task's question sits under its entry in the processes panel (`ProcessEntry` → `TaskAsk.AskSlot`). The entry
repaints itself whenever the engine says the process moved (`processRev`) or its record is read again (`_load`);
each repaint used to clear the entry and build a new slot, so the box he was typing in left the page: his focus and
his caret were gone, and on a slow repaint his text with them. Rendered in Chromium against the real ProcessEntry,
TaskAsk, store and asks, with `/api/tasks`, the process record and the answer route answered by the test.

He types «Sí» with the caret moved, the process moves twice (a plan, then a later step and its log): the same box is
in the page with its text, its focus and its caret, the plan around it changed, and the send posts «Sí».

Disarm: `paintEntry` building a new slot on every repaint (the old `AskSlot(...)` per paint) → red.
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.waiting import until_sync

ENGINE = Path(__file__).resolve().parents[4]
_NOW = int(time.time())

pytest.importorskip("playwright.sync_api")

ROW = {"id": "T2", "session": "s2", "title": "w1", "goal": "w1", "state": "waiting", "waiting_for": "user_answer",
       "ask_id": "B1", "ask": "w2", "waiting_since": _NOW - 30, "deadline": _NOW + 600, "started_at": _NOW - 120,
       "visible": True}


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


def test_a_process_that_moves_while_he_types_keeps_his_answer(browser_and_port):
    b, port = browser_and_port
    pg = b.new_page(viewport={"width": 900, "height": 700})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    state = {"rec": {"alive": True, "plan": ["w3", "w4"], "done": 0, "phases": [], "browser": {}}, "reads": 0}
    posts: list[tuple[str, dict]] = []

    def process(route):
        state["reads"] += 1
        route.fulfill(status=200, content_type="application/json", body=json.dumps(state["rec"]))

    def answer(route):
        req = route.request
        posts.append((req.url.split("/api/tasks/")[1].split("/answer")[0], json.loads(req.post_data or "{}")))
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True}))

    pg.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
    pg.route("**/api/tasks?*", lambda r: r.fulfill(status=200, content_type="application/json",
                                                   body=json.dumps({"tasks": [ROW]})))
    pg.route("**/api/tasks/*/process", process)
    pg.route("**/api/tasks/*/answer", answer)
    pg.goto(f"http://127.0.0.1:{port}/frontend/app/core/palette.css", wait_until="domcontentloaded")
    pg.evaluate("""async () => {
        document.head.innerHTML = '';
        const store = await import('/frontend/app/core/store.js?v=2');
        const { ProcessEntry } = await import('/frontend/app/components/ProcessEntry.js?v=1');
        document.body.innerHTML = '';
        document.body.append(ProcessEntry('s2', 'T2'));
        window.__store = store;
    }""")
    box = '.pe[data-key="s2"] .tq[data-ask="B1"] .tq-input'
    until_sync(lambda: pg.wait_for_timeout(20) or pg.query_selector(box) is not None and state["reads"] >= 1,
               "his question under the entry, and the record read", timeout_s=10)
    pg.click(box)
    pg.keyboard.type("Sí")
    pg.keyboard.press("ArrowLeft")
    pg.evaluate(f"() => {{ window.__box = document.querySelector('{box}'); }}")
    for n, rec in enumerate([{"alive": True, "plan": ["w3", "w4"], "done": 1, "phases": ["w5"], "browser": {}},
                             {"alive": True, "plan": ["w3", "w4", "w6"], "done": 2, "phases": ["w5", "w7"], "browser": {}}],
                            start=2):
        state["rec"] = rec
        pg.evaluate("() => window.__store.bumpProcess()")                 # the engine says the process moved
        until_sync(lambda n=n: pg.wait_for_timeout(20) or state["reads"] >= n, f"the record read again ({n})", timeout_s=10)
        pg.wait_for_timeout(100)                                          # …and painted
    kept = pg.evaluate(f"""() => ({{ same: document.querySelector('{box}') === __box && __box.isConnected,
                                     value: __box.value, focused: document.activeElement === __box,
                                     caret: __box.selectionStart,
                                     plan: document.querySelector('.pe[data-key="s2"]').innerText.includes('w6') }})""")
    assert kept == {"same": True, "value": "Sí", "focused": True, "caret": 1, "plan": True}, kept
    pg.click('.pe[data-key="s2"] .tq[data-ask="B1"] .tq-send')
    until_sync(lambda: pg.wait_for_timeout(20) or bool(posts), "the answer POST", timeout_s=10)
    assert posts[0] == ("T2", {"ask_id": "B1", "text": "Sí"})
    assert not errors, errors
    pg.close()
