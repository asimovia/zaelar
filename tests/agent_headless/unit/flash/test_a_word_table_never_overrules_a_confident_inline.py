"""A word table never turns an empty promise into a worker (V2-802 T-07, CRIT-K1; A7: never at all, not only over a
confident `handle_inline`, and an owed act is read at the act floor).

Live run: «Ayer te pedí hacer una reserva en un restaurante. Te di mi nombre completo y mi teléfono. ¿Todo eso ya
debería estar en tu memoria permanente?» — brief `question` (unsure) · `tell` · `handle_inline` 1.00. The model said
«Eso es lo que estoy comprobando ahora mismo…» and called nothing; the post-stream promise branch met «reserva» in
`looks_like_escalate_task` and a web worker went looking for restaurants. V2-753 had put «only a confident
handle_inline stops the escalation» in `promise_backstop`; this branch lacked it.

The variant here is another language and another domain on purpose: a hotel, in English.
"""
from __future__ import annotations

import asyncio
import inspect
import threading
import types


from nucleo.turn import brief as tb

SAID = "Last week I asked you to book a hotel in Lisbon and gave you my passport number. Do you still remember all that?"
REPLY = "That's exactly what I'm checking right now, give me a second."


def _brief(escalate: str, conf: float) -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "result": {
        tb.ESCALATE_KEY: {"choice": escalate, "confidence": conf},
        tb.REQUEST_KEY: {"choice": "question", "confidence": 0.45},     # unsure, as in the live run
        tb.WORDS_KEY: {"choice": "tell", "confidence": 0.9}}}


def _voice_lane(monkeypatch, brief) -> tuple[dict, list]:
    """The voice lane itself, run with the turn's state stubbed; the root conftest isolates every store."""
    from nucleo.flash import post_stream as P, post_stream_lanes as L, router

    async def _untouched(no_tool, *a, **k):
        return no_tool
    monkeypatch.setattr(P._resume_turn, "before_backstops", _untouched)
    events: list = []
    escalate_req = {"v": None}
    kw = {n: None for n in inspect.signature(L.run_the_light_lanes).parameters}
    kw.update(_brief=brief, _op_text=SAID, operator_text=SAID, text=SAID, spoken_text=REPLY, spoken=REPLY,
              _no_tool=True, _router=router, emit=lambda *a, **k: events.append(a), escalate_req=escalate_req,
              music_req={"v": None}, acted={}, data_done={"v": False}, clarify={}, _tool_fired=set(),
              _shown_ids=set(), brain=types.SimpleNamespace(_window=[], _last_spoken=""), _named_by_verdict="",
              _identify=lambda t: "", _identify_system=lambda t: None, with_also_named=lambda ids, t: ids,
              **{k: {"v": None} for k in ("read_req", "recall_req", "reopen_req", "reveal_req", "search_req",
                                          "listing_req", "images_req")})
    asyncio.run(L.run_the_light_lanes(**kw))
    return escalate_req, events


def test_the_voice_lane_does_not_escalate_a_question_the_verdict_kept_inline(monkeypatch):
    req, _events = _voice_lane(monkeypatch, _brief("handle_inline", 1.0))
    assert req["v"] is None, req


def _owed(escalate: str, conf: float) -> dict:
    """The same turn read as a sure ORDER: an act is owed (refactor2710-03), so the lane reaches the word tables."""
    b = _brief(escalate, conf)
    b["result"][tb.REQUEST_KEY] = {"choice": "order", "confidence": 0.95}
    return b


def test_a_sure_order_with_errand_words_opens_no_worker_without_a_sure_escalation(monkeypatch):
    """A7: the word table (`looks_like_escalate_task`: «book a hotel») used to send a sure ORDER to a worker when the
    escalate verdict was unsure. An errand opens by the model's call or a sure verdict, never by his words."""
    req, events = _voice_lane(monkeypatch, _owed("handle_inline", 0.3))
    assert req["v"] is None, (req, events)


def test_owing_an_act_is_read_at_the_act_floor(monkeypatch):
    """A7: the lane opened on an order at 0.55 and an escalation at 0.55 (the licence) — under the operator's 60 %."""
    b = _brief("escalate", 0.55)
    b["result"][tb.REQUEST_KEY] = {"choice": "order", "confidence": 0.55}
    from nucleo.turn import reply
    assert reply.owes_an_act(b) == "", "an act owed under the act floor"
    req, _ = _voice_lane(monkeypatch, b)
    assert req["v"] is None, req
    b["result"][tb.ESCALATE_KEY]["confidence"] = 0.65
    assert reply.owes_an_act(b) == "escalate"


def test_an_unsure_verdict_invents_no_worker_from_our_words(monkeypatch):
    """refactor2710-03: an act is owed only when the brief says so; an unsure question leaves the model's turn."""
    req, _ = _voice_lane(monkeypatch, _brief("handle_inline", 0.3))
    assert req["v"] is None, req
    req, _ = _voice_lane(monkeypatch, {**_brief("escalate", 0.95)})
    assert req["v"] == SAID, "a sure escalation over nothing fired still gets its worker"


def _read(**verdicts) -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "result": {k: {"choice": c, "confidence": p, "used": True} for k, (c, p) in verdicts.items()}}


def test_every_launch_reads_the_one_act_floor():
    """A7: the readers that LAUNCH an act the model did not make read the operator's floor (0.6) — not the licence
    (0.5) and not a bar of their own (0.8 · 0.85). Each pair: just under the floor launches nothing, just over it does."""
    from nucleo.acts import card_verdict, repair_after_lookup
    from nucleo.turn import reply
    for low, high in ((0.55, 0.65),):
        assert reply.owes_an_act(_read(**{tb.REQUEST_KEY: ("order", low)})) == ""
        assert reply.owes_an_act(_read(**{tb.REQUEST_KEY: ("order", high)})) == "order"
        assert not card_verdict.verdict_shows(_read(**{tb.CANVAS_KEY: ("show", low), tb.REQUEST_KEY: ("order", 0.9)}))
        assert card_verdict.verdict_shows(_read(**{tb.CANVAS_KEY: ("show", high), tb.REQUEST_KEY: ("order", 0.9)}))
        cat = {tb.CATALOG_KEY: ("documento", 0.9)}
        assert not card_verdict.order_over_a_card_left_undone(_read(**{tb.REQUEST_KEY: ("order", low)}, **cat))
        assert card_verdict.order_over_a_card_left_undone(_read(**{tb.REQUEST_KEY: ("order", high)}, **cat))
    sure = {tb.REQUEST_KEY: ("order", 0.7), tb.TARGET_KEY: ("agenda:cancel_meeting", 0.7)}
    assert repair_after_lookup.same_card_order_after_read(_read(**sure), "agenda") == "cancel_meeting", \
        "a 0.7 target used to need 0.85 to repair a read"
