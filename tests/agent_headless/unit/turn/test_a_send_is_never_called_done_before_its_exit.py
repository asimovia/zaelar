"""A send is never called «Done.» before its exit door reports, and its failure is SAID (V2-903, demo E3 on b136).

Live, on b136: «send the invoice to Morgan, tell him we're already trying the new provider and he should book it». The
model wrote «I'll send that to Morgan with your note.» and routed the forward to its task. Three doors then lied:
  1. the stop verdict was «in play» (replace 0.59, no sure verdict, no `stop_worker` call): the words were held until
     after the acts, and dropped there as «already said» — by the ack that had filled the silence meanwhile;
  2. that ack was «Done.»: the catalogue rung's send set no data-op, so the routed-send start line did not fire and the
     generic widget ack spoke for an act that had not left;
  3. 1.6 s later the forward failed. The refusal was left «for the turn's mouth» — a turn that had already closed —
     so nothing was sent and nobody told him.
Words follow the act (L2): held words narrate no door's decision once no stop can run; a send that left as a task is a
START; an outcome that lands after its turn closed goes out through the out-of-turn mouth.
"""
from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace

import pytest

from nucleo.flash import follow_up_pass as fup
from nucleo.request import stop as sd
from nucleo.turn import brief as _tb

_WORDS = ["I'll send that to Morgan with your note.", "Se lo mando a Morgan con tu nota."]


def _brief(choice: str, confidence: float):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": [],
            "result": {_tb.REQUEST_KEY: {"choice": "order", "confidence": 0.9},
                       sd.KEY: {"choice": choice, "confidence": confidence}}}


def _stream(brief, words: str, calls):
    sent, events = [], []
    hold = fup.Hold(brief, sent.append)
    hold.say(words)
    assert sent == [], "the stop was in play: the words should have waited at the first word"
    asyncio.run(hold.release(calls, [], lambda kind, label="", **kw: events.append(label)))
    return hold, sent


@pytest.mark.parametrize("words", _WORDS)
def test_held_words_are_said_at_the_streams_end_when_no_stop_can_run(words):
    hold, sent = _stream(_brief("replace", 0.59), words, [{"name": "widget_data", "args": {}}])
    assert sent == [words], "the model's own line waited past the acts, where an ack could stand in for it"
    assert not hold.stop_words


@pytest.mark.parametrize("calls,choice,conf", [
    ([{"name": "stop_worker", "args": {}}], "stop", 0.47),     # the model's own stop: its door still rules
    ([], "stop", 0.99),                                          # a sure verdict stops by itself
], ids=["model-stop", "sure-verdict"])
def test_words_still_wait_while_a_stop_can_run(calls, choice, conf):
    hold, sent = _stream(_brief(choice, conf), "Stopping the flat search.", calls)
    assert sent == [] and hold.stop_words, "words that narrate a stop a door may still rule on went out early"


class _Speech:
    @staticmethod
    def sanitize(t, **_k):
        return t


def test_a_routed_send_with_no_data_op_is_a_start_never_done():
    from i18n import langs
    from nucleo.turn import reply
    said = []
    line = reply.routed_send_line("", True, False, said.append, _Speech)
    start = str(langs.current_language().done_just_started)
    assert line == start and said == [start], f"a send that left as a task with no data-op was not said as a START: {said}"
    acks = {str(a).strip().lower() for a in (langs.current_language().data_acks or ())} | {
        str(langs.current_language().data_ack).strip().lower()}
    assert line.strip().lower() not in acks


def test_the_widget_ack_never_stands_for_a_routed_send():
    import inspect
    from nucleo.flash import post_stream_settle
    src = inspect.getsource(post_stream_settle)
    i = src.index('if acted["widget"] and not spoken_text and _ack_allowed')
    assert 'not escalate_req.get("send_task")' in src[i:i + 120], "the show/close ack may still say «Done.» over a send"


@pytest.fixture
def failing_send(monkeypatch):
    """A forward the card refuses, under a turn whose mouth has CLOSED; the out-of-turn mouth is recorded."""
    import widgets
    from nucleo.flash import refusal_line
    from nucleo.pulse import notices
    from nucleo.turn import mouth
    from voice import trace
    told = []

    async def _card(tag, body):
        return {"ok": False, "message": "That message is not in the app with its attachments yet."}

    async def _notify(title, text, **kw):
        told.append(text)
    monkeypatch.setattr(widgets, "dispatch_tag", _card)
    monkeypatch.setattr(notices, "notify", _notify)

    async def _said(wid, res, **_k):
        return str(res.get("message") or "")
    monkeypatch.setattr(refusal_line, "said", _said)
    trace.adopt("T9·e3e3")
    mouth.open_for("T9·e3e3")

    def run(*, closed: bool, row: str = "e3-row"):
        if closed:
            mouth.close("", lambda *_a: None, _Speech)
        from nucleo.flash import data_ops
        told.clear()
        data_ops._RECENT_FAILURES.clear()      # the cooldown would hide a second case of the same refusal
        asyncio.run(data_ops.dispatch_and_report("mensajeria", "forward", {"contact": "Morgan", "text": "book it"},
                                                 text="forward the invoice to Morgan", row=row))
        return list(told)
    yield run
    if mouth.is_open("T9·e3e3"):
        mouth._OPEN.remove("T9·e3e3")
    trace.adopt("")


def test_a_refusal_after_its_turn_closed_is_said_out_of_turn(failing_send):
    told = failing_send(closed=True)
    assert told and "attachments" in told[0], "the send failed after its turn had closed and nobody told him"


def test_a_refusal_inside_its_open_turn_is_left_to_that_turns_mouth(failing_send):
    assert failing_send(closed=False) == [], "a refusal the live turn will say was also said out of turn (twice)"


def test_an_op_of_no_row_keeps_the_clock_alone(failing_send):
    """Audit F1: a turn's own data-op (no row: a compose rung, an inline op) is not said out of turn on a closed mouth
    — only a row's op, whose turn handed it off, is."""
    assert failing_send(closed=True, row="") == []


def test_may_run_reads_the_model_call_and_the_sure_verdict_only():
    assert fup.stop_may_run(_brief("keep", 0.9), [{"name": "stop_worker"}])
    assert not fup.stop_may_run(_brief("replace", 0.59), [{"name": "widget_data"}])
    assert not fup.stop_may_run(None, [])
