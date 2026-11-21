"""The chat wall has one writer per line, and the engine writes the lines the page's old-path writer used to (node
13.165, INI-078 — the wall of one writer). Each line keeps the role, kind, state, data and id it had:

  · a notice painted apart from the mouth (`notify` with no `conv`: no voice of the manager holds it, or an owed one
    drained to a screen) → writer `notice`, id `notice_<key>`, an agent line, final, `🔔 ` + its text, `data.trace`
    empty; one with no key gets an id of its own (`a_…`). Not when it is the question of a card open now (a row waiting
    on his consent, compared without marks or emphasis — a clarification is dialogue and is drawn), nor when the last
    line already says it. A `conv` notice is the mouth's own line: no second one;
  · the line an answered confirmation leaves → writer `record`, a note of kind `record`, `data` {role, text};
  · an errand's reference box → writer `ref`, id `ref_<row>`, a box of kind `ref`: appended at its first event,
    replaced at every later one with the card and file it already had when the event names none; the replace carries
    the box's role, so a screen that has not got it yet appends it (`wall-bridge.js`); a skipped errand draws none. The writers live in `nucleo/conversation_host/wall_notes.py`.

Disarms seen red: each emitter's call to its writer removed in turn (`proactive._paint`, `notices.drain_to_screen`,
`ask_trace.resolved`, `chat_refs._emit`); the open-card check, the last-line check and the merge of the box's data.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from nucleo.conversation_host import wall, wall_notes


@pytest.fixture
def ops(monkeypatch):
    from voice import observer
    out = []
    monkeypatch.setattr(observer, "emit", lambda kind, label, text="", role="", extra=None, piece=None:
                        kind == "wall" and out.append((extra["writer"], dict(extra["op"]))))
    wall._reset_for_tests()
    wall_notes._reset_for_tests()
    yield out
    wall._reset_for_tests()
    wall_notes._reset_for_tests()


def _bare(op: dict) -> dict:
    """The action as the wall reads it, without the instant it was written at."""
    assert isinstance(op.pop("at", None), int), "every line says when it was written"
    return op


@pytest.fixture
def cards(monkeypatch):
    """The rows waiting on his answer, as the ledger has them: {row id: (question, kind)}."""
    from nucleo.circuit import asker, ledger
    rows: dict = {}
    store = SimpleNamespace(tasks_where=lambda **_: [
        {"id": k, "state": "waiting", "waiting_for": ledger.USER_ANSWER, "ask_id": "a_" + k, "ask": q}
        for k, (q, _kind) in rows.items()])
    monkeypatch.setattr(ledger, "store", lambda: store)
    monkeypatch.setattr(asker, "artefact", lambda uid: {"kind": rows[uid][1]} if uid in rows else {})
    return rows


def test_a_notice_painted_apart_from_the_mouth_is_its_bell_line(ops, cards):
    from voice import proactive
    proactive._paint("notify", "w0", "w1", key="k1", task_id="")
    assert [(w, _bare(op)) for w, op in ops] == [("notice", {
        "op": "append", "id": "notice_k1", "role": "agent", "state": "final", "text": "🔔 w1", "data": {"trace": ""}})]
    proactive._paint("notify", "w0", "w2", key="", task_id="")
    assert ops[-1][0] == "notice" and ops[-1][1]["id"].startswith("a_") and ops[-1][1]["text"] == "🔔 w2"
    n = len(ops)
    proactive.paint("w0", "w3", key="k3")                    # the mouth's own: its card only, never a second line
    proactive._paint("other", "w0", "w4", key="k4", task_id="")
    assert len(ops) == n


def test_an_owed_notice_drained_to_a_screen_is_its_bell_line(ops, cards, monkeypatch):
    from nucleo.pulse import notices
    monkeypatch.setattr(notices._store, "owed_all", lambda: [{"id": 7, "title": "w0", "body": "w5", "dedupe_key": "k5"}])
    monkeypatch.setattr(notices, "_set", lambda *a, **k: None)
    monkeypatch.setattr(notices._ask, "closed_answered", lambda r: False)
    assert notices.drain_to_screen("desktop:x") == 1
    assert [(w, op["id"], op["text"]) for w, op in ops] == [("notice", "notice_k5", "🔔 w5")]


def test_the_question_of_an_open_card_is_not_drawn_again(ops, cards):
    cards["r1"] = ("¿Lo **envío** a  w6?", "consent")
    wall_notes.notice("🔔 ¿lo envío a w6?", "k6")
    assert ops == [], "the question's card is its one place on screen"
    cards["r2"] = ("w7", "clarify")
    wall_notes.notice("w7", "k7")
    assert [op["id"] for _w, op in ops] == ["notice_k7"], "a clarification is dialogue: its notice is a line"


def test_a_notice_the_last_line_already_says_is_not_said_again(ops, cards):
    wall._say("mouth", {"op": "append", "id": "s_1", "role": "agent", "state": "final", "text": "w8 w9"})
    wall_notes.notice("w8", "k8")
    wall_notes.notice("w8 w9", "k9")
    assert [w for w, _op in ops] == ["mouth"]
    wall_notes.notice("w10", "k10")
    wall_notes.notice("w10", "k10")
    assert [op["id"] for w, op in ops if w == "notice"] == ["notice_k10"]


def test_an_answered_question_leaves_one_record_line(ops, monkeypatch):
    from nucleo import wording
    from nucleo.circuit import ask_trace

    async def word(fact, **kw):
        return "w11"
    monkeypatch.setattr(wording, "word_soon", word)
    monkeypatch.setattr(ask_trace, "_his_name", lambda: "w12")
    line = asyncio.run(ask_trace.resolved("u1", {"ask_id": "a1", "question": "w13"}, ask_trace.YES))
    assert line == "w11"
    (w, op), = ops
    assert w == "record" and op["id"].startswith("n_")
    assert _bare({k: v for k, v in op.items() if k != "id"}) == {
        "op": "append", "role": "note", "kind": "record", "data": {"role": "record", "text": "w11"}, "text": "w11"}


def test_an_errand_reference_is_one_box_replaced_in_place(ops):
    from nucleo import chat_refs
    rec = SimpleNamespace(trace_id="")
    base = {"ref": "R1", "task_id": "t1", "surface": "s1", "title": "w14"}
    chat_refs._emit("opened", rec, {**base, "card": "", "state": "started"})
    chat_refs._emit("retitled", rec, {**base, "card": "c1", "title": "w15", "state": "started"})
    chat_refs._emit("closed", rec, {**base, "card": "", "title": "w15", "state": "done", "file": "f1"})
    chat_refs._emit("skipped", rec, {"ref": "R2", "title": "w16", "state": "", "reason": "child"})
    got = [(w, _bare(op)) for w, op in ops]
    row = {"role": "ref", "ref": "R1", "surface": "s1", "file": ""}
    assert got == [
        ("ref", {"op": "append", "id": "ref_R1", "role": "box", "kind": "ref", "text": "w14",
                 "data": {**row, "text": "w14", "card": "", "state": "started"}}),
        ("ref", {"op": "replace", "id": "ref_R1", "role": "box", "kind": "ref", "text": "w15",
                 "data": {**row, "text": "w15", "card": "c1", "state": "started"}}),
        ("ref", {"op": "replace", "id": "ref_R1", "role": "box", "kind": "ref", "text": "w15",
                 "data": {**row, "text": "w15", "card": "c1", "state": "done", "file": "f1"}}),
    ], "one box per row, the card it had kept, a skipped errand drawing none"
