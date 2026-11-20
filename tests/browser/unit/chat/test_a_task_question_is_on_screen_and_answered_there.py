"""V2-851 F1c — a task's question is on the screen, bound to its task, and answered from there (node 4.359).

A task that needs his answer parks a durable question on its row (`state:"waiting"`, `waiting_for:"user_answer"`,
`ask_id`, `ask`) and the engine pushes an SSE `ask` event. Before this, the screen showed a ⏳ chip and the word
«waiting» — never the question, and no way to answer it. Rendered in Chromium against the real ChatWall, store,
SSE router (`routeEvent`), ProcessEntry, stylesheets and Spanish bundle; `/api/tasks` and the answer route are
answered by the test.

  · the SSE `ask` event draws the question on the wall as a line of its own (source «ask», tied to its task);
    quick buttons only when the ask carries `options`.
  · answering — the field or a quick button — POSTs `/api/tasks/{task_id}/answer` with that question's ask_id.
  · a 409 (no longer open) re-reads the rows: the line follows the row, not the screen's copy.
  · after a reload the open questions come back from `/api/tasks`, each bound to its task's title, on the wall
    and on the task's entry in the processes panel.
  · a `task_state` event that moves the row out of `waiting` removes the line; `waiting` itself does not.

Disarms seen red (2026-11-05), each against the test that names it: `asks.route` not called from sse.js (the event,
the answer, the 409 and the task_state tests red); the POST body without `ask_id` (the answer test red); the 409
branch not re-reading (the 409 test red); `ensureAsks` not reading the rows (the reload test red); `onTaskState`
ignoring the event (the task_state test red); quick buttons guessed from the digits of the text (the event test red).
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
_ES = json.loads((ENGINE / "i18n/genesis/es/ui.json").read_text(encoding="utf-8"))
_NOW = int(time.time())

pytest.importorskip("playwright.sync_api")


def _listening(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
        return True
    except OSError:
        return False


def _waiting(tid: str, ask_id: str, text: str, title: str, **extra) -> dict:
    return {"id": tid, "title": title, "goal": "g", "state": "waiting", "waiting_for": "user_answer",
            "ask_id": ask_id, "ask": text, "waiting_since": _NOW - 30, "deadline": _NOW + 600,
            "started_at": _NOW - 120, "visible": True, **extra}


class _Engine:
    """What the test's engine answers: the live rows, and the status of the next answer."""

    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.answer_status = 200
        self.posts: list[tuple[str, dict]] = []
        self.task_reads = 0

    def tasks(self, route):
        self.task_reads += 1
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"tasks": self.rows}))

    def answer(self, route):
        req = route.request
        if req.method != "POST":
            return route.fulfill(status=405, body="")
        self.posts.append((req.url.split("/api/tasks/")[1].split("/answer")[0], json.loads(req.post_data or "{}")))
        st = self.answer_status
        route.fulfill(status=st, content_type="application/json",
                      body=json.dumps({"ok": True} if st == 200 else {"ok": False, "error": "not_open"}))


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
def open_wall(browser_and_port):
    b, port = browser_and_port
    pages = []

    def _open(engine: _Engine):
        pg = b.new_page(viewport={"width": 1280, "height": 900})
        pages.append(pg)
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
        pg.route("**/api/tasks?*", engine.tasks)
        pg.route("**/api/tasks/*/answer", engine.answer)
        pg.route("**/api/i18n/bundle/*", lambda r: r.fulfill(status=200, content_type="application/json",
                                                              body=json.dumps({"strings": _ES})))
        pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
        pg.evaluate("""async () => {
            for (const h of ['/frontend/app/core/palette.css', '/frontend/app/core/components.css',
                             '/frontend/app/core/shared-surfaces.css', '/frontend/app/styles.css', '/frontend/side/procesos/procesos.css']) {
              const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = h; document.head.append(l); }
            const i18n = await import('/frontend/app/core/i18n.js?v=1');
            await i18n.loadBundle('es'); if (i18n.applyLang) await i18n.applyLang('es');
            const store = await import('/frontend/app/core/store.js?v=2');
            const sse = await import('/frontend/app/services/sse.js?v=6');
            const m = await import('/frontend/app/components/ChatWall.js?v=5');
            document.body.append(m.ChatWall());
            window.__store = store; window.__route = (d) => sse.routeEvent(null, d);
            // the page's ONE old-path wall writer: the URL ChatWall imports it by (another `?v=` is a blind copy)
            window.__legacy = (await import('/frontend/app/services/wall-legacy.js?v=1')).legacy;
            store.setChatTab('chat'); store.setChatOpen(true);
        }""")
        pg.wait_for_selector("#chatwall.open", timeout=5000)
        pg._errors = errors
        return pg

    yield _open
    for pg in pages:
        pg.close()


def _lines(pg):
    return pg.evaluate("""() => [...document.querySelectorAll('#chatwall .tq-wall .tq')].map(n => ({
        task: n.dataset.task, ask: n.dataset.ask, source: n.dataset.source, text: n.innerText,
        opts: [...n.querySelectorAll('.tq-opt')].map(b => b.innerText), visible: n.offsetParent !== null }))""")


def _until_lines(pg, pred, what):
    return until_sync(lambda: (lambda xs: (xs,) if pred(xs) else None)(_lines(pg)), what, timeout_s=10)[0]


def _until_posts(pg, eng, n, what):
    """Wait for the n-th answer POST. The route that records it runs only while Playwright is called, so every poll
    hands Playwright a moment (`wait_for_timeout`); a bare check of `eng.posts` would wait for a handler nobody runs."""
    until_sync(lambda: pg.wait_for_timeout(20) or len(eng.posts) >= n, what, timeout_s=10)


def _until_reads_settle(pg, eng, quiet_polls=6):
    """Wait until the panel stops re-reading `/api/tasks`. Entering a tab fires several reads; one still queued at the
    route is answered during the next Playwright call and redraws the rows, so a `fill` made before it lands in an input
    that is then replaced, and the click sends nothing."""
    seen = {"n": -1, "same": 0}

    def quiet():
        pg.wait_for_timeout(50)
        seen["same"] = seen["same"] + 1 if eng.task_reads == seen["n"] else 0
        seen["n"] = eng.task_reads
        return seen["same"] >= quiet_polls
    until_sync(quiet, "the task reads to settle", timeout_s=10)


def test_the_ask_event_draws_the_question_on_the_wall(open_wall):
    eng = _Engine()
    pg = open_wall(eng)
    pg.evaluate("""() => window.__route({kind: 'ask', task_id: 'T1', ask_id: 'A1',
                                        text: '¿Para cuántas personas reservo, 2 o 4?', title: 'Reservar mesa'})""")
    xs = _until_lines(pg, lambda xs: len(xs) == 1, "the ask line on the wall")
    line = xs[0]
    assert (line["task"], line["ask"], line["source"]) == ("T1", "A1", "ask")
    assert "¿Para cuántas personas reservo, 2 o 4?" in line["text"]
    assert _ES["chat.askOf"].replace("{title}", "Reservar mesa") in line["text"], "the line is not bound to its task"
    assert line["visible"], "the question is in the DOM but not on screen"
    assert line["opts"] == [], "quick answers were guessed from the wording — only declared options are buttons"
    pg.evaluate("""() => window.__route({kind: 'ask', task_id: 'T2', ask_id: 'B1', text: '¿Qué día?',
                                        title: 'Cita', options: ['Lunes', 'Martes']})""")
    xs = _until_lines(pg, lambda xs: len(xs) == 2, "the second task's line")
    assert xs[1]["opts"] == ["Lunes", "Martes"]
    assert "raw" not in str(xs) and "chat.ask" not in str(xs), "a raw i18n key reached the screen"
    assert not pg._errors, pg._errors


def test_answering_posts_the_task_and_its_ask_id(open_wall):
    eng = _Engine()
    pg = open_wall(eng)
    pg.evaluate("""() => { window.__route({kind: 'ask', task_id: 'T1', ask_id: 'A1', text: '¿Cuántos?', title: 'Mesa'});
                           window.__route({kind: 'ask', task_id: 'T2', ask_id: 'B7', text: '¿Qué día?',
                                           title: 'Cita', options: ['Lunes', 'Martes']}); }""")
    _until_lines(pg, lambda xs: len(xs) == 2, "two lines")
    pg.fill('.tq-wall .tq[data-task="T1"] .tq-input', "Cuatro")
    pg.click('.tq-wall .tq[data-task="T1"] .tq-send')
    _until_posts(pg, eng, 1, "the answer POST")
    assert eng.posts[0] == ("T1", {"ask_id": "A1", "text": "Cuatro"})
    xs = _until_lines(pg, lambda xs: any("Cuatro" in x["text"] and not x["opts"] for x in xs if x["task"] == "T1"),
                      "the line saying it was answered")
    assert _ES["chat.askSent"].replace("{text}", "Cuatro") in [x for x in xs if x["task"] == "T1"][0]["text"]
    pg.click('.tq-wall .tq[data-task="T2"] .tq-opt >> text=Martes')
    _until_posts(pg, eng, 2, "the quick answer POST")
    assert eng.posts[1] == ("T2", {"ask_id": "B7", "text": "Martes"}), "a quick answer names its own task and question"
    assert not pg._errors, pg._errors


def test_a_409_rereads_the_rows(open_wall):
    eng = _Engine()
    pg = open_wall(eng)
    pg.evaluate("""() => window.__route({kind: 'ask', task_id: 'T1', ask_id: 'A1', text: '¿Cuántos?', title: 'Mesa'})""")
    _until_lines(pg, lambda xs: len(xs) == 1, "the line")
    # Meanwhile it was answered by voice and the task asked something else: the row says so.
    eng.rows = [_waiting("T1", "A2", "¿Y a qué hora?", "Mesa")]
    eng.answer_status = 409
    reads = eng.task_reads
    pg.fill('.tq-wall .tq[data-task="T1"] .tq-input', "Cuatro")
    pg.click('.tq-wall .tq[data-task="T1"] .tq-send')
    xs = _until_lines(pg, lambda xs: len(xs) == 1 and xs[0]["ask"] == "A2", "the line to follow the row")
    assert eng.task_reads > reads
    assert "¿Y a qué hora?" in xs[0]["text"] and "¿Cuántos?" not in xs[0]["text"]
    # …and a question the row no longer holds goes away on the next refusal.
    eng.rows = []
    pg.fill('.tq-wall .tq[data-task="T1"] .tq-input', "A las nueve")
    pg.click('.tq-wall .tq[data-task="T1"] .tq-send')
    _until_lines(pg, lambda xs: xs == [], "the closed question to leave the wall")
    assert not pg._errors, pg._errors


def test_a_reload_brings_the_open_questions_back_from_the_rows(open_wall):
    eng = _Engine([_waiting("T1", "A1", "¿Para cuántas personas?", "Reservar mesa en Casa Lola"),
                   _waiting("T2", "B1", "¿Le digo que llegas tarde?", "Avisar a Raquel", session="sess-2"),
                   {"id": "T3", "title": "Buscar piso", "state": "running", "started_at": _NOW - 60}])
    pg = open_wall(eng)
    xs = _until_lines(pg, lambda xs: len(xs) == 2, "both open questions from /api/tasks")
    by = {x["task"]: x for x in xs}
    assert set(by) == {"T1", "T2"}, "a running task grew a question, or a waiting one lost its own"
    assert _ES["chat.askOf"].replace("{title}", "Reservar mesa en Casa Lola") in by["T1"]["text"]
    assert "¿Para cuántas personas?" in by["T1"]["text"]
    assert _ES["chat.askOf"].replace("{title}", "Avisar a Raquel") in by["T2"]["text"]
    assert "¿Le digo que llegas tarde?" in by["T2"]["text"]
    # The same question sits under its task's entry in the processes panel — and only under its own.
    pg.evaluate("() => { const s = window.__store; s.setTaskScope('live'); s.setChatTab('procesos'); "
                "s.fetchTaskScope('live'); }")
    rows = until_sync(lambda: (lambda r: r if len(r) == 3 else None)(pg.evaluate(
        """() => [...document.querySelectorAll('.cw-proc-row')].map(r => ({
             goal: r.querySelector('.cw-proc-goal').innerText,
             asks: [...r.querySelectorAll('.tq')].map(n => n.dataset.ask) }))""")), "three process rows", timeout_s=10)
    got = {r["goal"]: r["asks"] for r in rows}
    assert got == {"Reservar mesa en Casa Lola": ["A1"], "Avisar a Raquel": ["B1"], "Buscar piso": []}
    _until_reads_settle(pg, eng)
    pg.fill('.cw-proc-row .tq[data-ask="B1"] .tq-input', "Sí")
    pg.click('.cw-proc-row .tq[data-ask="B1"] .tq-send')
    _until_posts(pg, eng, 1, "the answer from the processes panel")
    assert eng.posts[0] == ("T2", {"ask_id": "B1", "text": "Sí"})
    assert not pg._errors, pg._errors


def test_a_final_task_state_removes_the_line(open_wall):
    eng = _Engine([_waiting("T1", "A1", "¿Cuántos?", "Mesa"), _waiting("T2", "B1", "¿Qué día?", "Cita")])
    pg = open_wall(eng)
    _until_lines(pg, lambda xs: len(xs) == 2, "both lines")
    pg.evaluate("() => window.__route({kind: 'task_state', task_id: 'T1', state: 'waiting', writer: 'worker'})")
    pg.wait_for_timeout(150)
    assert len(_lines(pg)) == 2, "a row still waiting lost its question"
    pg.evaluate("() => window.__route({kind: 'task_state', task_id: 'T1', state: 'done', writer: 'settle'})")
    xs = _until_lines(pg, lambda xs: len(xs) == 1, "the finished task's line to go")
    assert xs[0]["task"] == "T2", "the wrong task's question was removed"
    pg.evaluate("() => window.__route({kind: 'task_state', task_id: 'T2', state: 'cancelled', writer: 'settle'})")
    _until_lines(pg, lambda xs: xs == [], "the cancelled task's line to go")
    assert not pg._errors, pg._errors


_ORDER = """() => [...document.querySelectorAll('#chatwall .cw-list > *')].filter(n => !n.hidden).map(n => {
    const q = n.classList.contains('tq') ? n : n.querySelector(':scope > .tq');
    return q ? 'tq:' + q.dataset.ask : (n.innerText || '').trim(); })"""


def _until_order(pg, pred, what):
    return until_sync(lambda: (lambda xs: (xs,) if pred(xs) else None)(pg.evaluate(_ORDER)), what, timeout_s=10)[0]


def test_a_question_sits_under_the_turn_that_caused_it_and_has_a_close(open_wall):
    """V2-886 D6/D7 — a question whose row was opened by a turn in the conversation is drawn in the conversation,
    under that turn — a box line of its own (`legacy.asks`, kind `ask`) — never pinned at the foot; a question with
    no anchor stays in the foot block. Each card has its ✕. When it closes, its box leaves the wall.

    The wall plan §5.1 (decided by the operator): a line's place is where it STARTS — the box is APPENDED when the
    question opens and never moves after. So a question that opens while its turn is the last one sits right under
    it, and one that opens after a later turn is appended after that turn: nothing is inserted above a line."""
    eng = _Engine()
    pg = open_wall(eng)
    pg.evaluate("""() => { window.__legacy.youSaid('cierra todo');
                           window.__legacy.pushAgentChat('Voy.', {trace: 'tr-1'}); }""")
    pg.evaluate("""() => window.__route({kind: 'ask', task_id: 'T9', ask_id: 'Z1', text: '¿Se lo mando a Zarina?',
                                        title: 'Enviar borrador', trace: 'tr-1'})""")
    pg.evaluate("""() => window.__route({kind: 'ask', task_id: 'T8', ask_id: 'Z2', text: '¿Qué día?',
                                        title: 'Cita', trace: 'tr-none'})""")
    _until_order(pg, lambda xs: 'tq:Z1' in xs, "the anchored question inside the list")
    pg.evaluate("""() => { window.__legacy.youSaid('pon música');
                           window.__legacy.pushAgentChat('Suena.', {trace: 'tr-2'}); }""")
    order = _until_order(pg, lambda xs: 'Suena.' in xs, "the next turn on the wall")
    assert order.index('tq:Z1') == order.index('Voy.') + 1, order
    assert order.index('tq:Z1') < order.index('pon música'), "the question was not placed under its own turn"
    assert order.count('tq:Z1') == 1, order
    foot = [x["ask"] for x in _lines(pg)]
    assert foot == ["Z2"], f"only the question with no anchor stays at the foot: {foot}"
    assert pg.evaluate("() => document.querySelectorAll('#chatwall .tq .tq-close').length") == 2
    # §5.1: a question of the FIRST turn that opens after the second one is appended where it starts — at the end.
    pg.evaluate("""() => window.__route({kind: 'ask', task_id: 'T7', ask_id: 'Z3', text: '¿A qué hora?',
                                        title: 'Recordatorio', trace: 'tr-1'})""")
    order = _until_order(pg, lambda xs: 'tq:Z3' in xs, "the late question appended")
    assert order[-1] == 'tq:Z3' and order.index('tq:Z1') == order.index('Voy.') + 1, order
    # It closes: its box leaves the wall (and the foot), the others stay where they are.
    pg.evaluate("() => window.__route({kind: 'task_state', task_id: 'T9', state: 'done', writer: 'settle'})")
    order = _until_order(pg, lambda xs: 'tq:Z1' not in xs, "the closed question's box to leave the wall")
    assert order == ['cierra todo', 'Voy.', 'pon música', 'Suena.', 'tq:Z3'], order
    assert [x["ask"] for x in _lines(pg)] == ["Z2"]
    assert not pg._errors, pg._errors


def test_a_question_is_drawn_once_its_card_and_not_a_chat_line_too():
    """V2-931 — the question of an open card, spoken or notified with the same words, is not painted again as an agent
    line: one question, one place. (Markdown marks and the bell of a notice do not make it a different text.)"""
    from pathlib import Path
    root = Path(__file__).resolve().parents[4] / "frontend" / "app"
    sse, asks = (root / "services" / "sse.js").read_text("utf-8"), (root / "core" / "asks.js").read_text("utf-8")
    assert "export const isOpenQuestion" in asks and "openAsks().some" in asks
    # The wall left the store: the spoken record goes through `legacy.pushAgentChat`, the notice through `legacy.notice`.
    assert sse.count("if (!asks.isOpenQuestion(d.text)) legacy.pushAgentChat(") == 1, "the spoken line is drawn beside its card"
    assert sse.count("if (!asks.isOpenQuestion(d.text)) legacy.notice(") == 1, "the notice is drawn beside its card"
