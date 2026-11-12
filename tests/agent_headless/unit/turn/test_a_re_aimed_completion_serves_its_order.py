"""A completion re-aimed to another card serves the order it was for — known by identity, never by names (node 2.1735).

Found by a unit probe (group A re-verification, 2026-11-12): music in front with the video card open, he says «next».
The empty turn's completion (`direct_action.complete`) lands on the card the conversation is about (`subject_card`):
`musica:next`. At the close the verdict still reads `youtube:next`, and `order_unserved.served` compared by card and act
— `youtube:next` was not among the ops, so the order read as unserved and the act ran AGAIN: two «next».

Now the completion that re-aims records the order it served (`direct_action.reaimed`), on the turn's trace, and
`served` recognises it. Disarm (seen red): drop the record in `complete`, or its read in `served`.
"""
from __future__ import annotations

from nucleo.flash import direct_action as da
from nucleo.request import order_unserved as O
from voice import trace


def test_an_act_that_ran_on_another_card_serves_the_order_it_stood_for():
    with trace.scope("T1·reaim"):
        assert not O.served("youtube", "next", ops=[("musica", "next")]), "the premise: names alone do not match"
        da._STOOD_FOR.setdefault("T1·reaim", set()).add(("youtube", "next"))
        assert O.served("youtube", "next", ops=[("musica", "next")])
    with trace.scope("T2·other"):
        assert not O.served("youtube", "next", ops=[("musica", "next")]), "another turn's re-aim served this one"


def test_the_completion_that_re_aims_records_the_order(monkeypatch):
    ran = []
    monkeypatch.setattr(da, "from_brief", lambda brief: ("youtube", "next"))
    monkeypatch.setattr(da, "resolve", lambda *a, **k: {"widget": "youtube", "action": "next", "payload": {},
                                                        "source": "no-payload", "label": "next"})
    monkeypatch.setattr(da, "subject_card", lambda wid, act, text: "musica")
    monkeypatch.setattr("nucleo.flash.verdict_card.canvas_yields", lambda brief: True)
    with trace.scope("T3·complete"):
        got = da.complete({}, operator_text="siguiente", emit=lambda *a, **k: None, present=lambda *a, **k: None,
                          apply_widget_data=lambda wid, act, payload: ran.append((wid, act)), require_order=False)
        assert got == "next" and ran == [("musica", "next")]
        assert O.served("youtube", "next", ops=ran), "the order its completion served is completed a second time"
