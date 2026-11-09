"""An ORDER served by a recall is carried out with what was recalled (V2-865, second cut).

Measured 2026-11-09 on build 118: «put on the artist I asked you about earlier» — the recall found her, and its
answer pass, which has no tools, said «I've got her — let me put her on now». Nothing played. The search lane had
`voice_after_search` for this since V2-781; the recall lane had nothing.

Pinned here:
  · `call_after_recall` runs one bounded pass on the card the brief names, with the RECALL's system prompt and what
    was recalled as the fact; a call for another card or none is nothing;
  · `voice_after_recall` applies it and marks the turn as acted — and does not run at all when the recall came back
    as an empty thread, the turn already acted, or a music request holds the turn;
  · the voice turn's recall lane calls it, after the recall spoke and before the empty-thread question.
"""
from __future__ import annotations

import asyncio
import ast
from pathlib import Path

import pytest

from nucleo.acts import card_pass, repair_after_lookup

ENGINE = Path(__file__).resolve().parents[3]
RECALLED = "I've got her: the lead singer of that drama — let me put her on now."
CALL = ("widget_data", {"widget_id": "musica", "action": "play", "payload": {"query": "the lead singer"}})


class _Model:
    def __init__(self, calls):
        self.calls, self.seen = calls, []

    async def complete(self, messages, **kw):
        self.seen.append(messages)
        for name, args in self.calls:
            kw["on_tool_call"](name, args)


@pytest.fixture
def brief(monkeypatch):
    from nucleo.flash import build_decision as bd
    from nucleo.turn import brief as tb
    said = {tb.REQUEST_KEY: "order", tb.WORDS_KEY: "act"}
    monkeypatch.setattr(tb, "read", lambda b, k, d="", min_confidence=None: (said[k], {"used": True})
                        if k in said else (d, None))
    monkeypatch.setattr(bd, "named_card", lambda b: "musica")
    monkeypatch.setattr(card_pass, "canvas_holds_the_turn", lambda *a, **k: False)
    from widgets import runtime as rt
    monkeypatch.setattr(rt, "get", lambda wid: {"actions": {"play": {"payload": {"query": "str"}}}}
                        if wid == "musica" else {})
    return said


@pytest.fixture
def model(monkeypatch):
    import nucleo.llm.fast_client as fc
    from nucleo.flash import widget_read
    monkeypatch.setattr(widget_read, "read", lambda wid, *a, **k: "")
    holder = {}

    def use(calls):
        holder["m"] = _Model(calls)
        monkeypatch.setattr(fc, "FastClient", lambda: holder["m"])
        return holder["m"]
    return use


ORDER = "put on the artist I asked you about earlier"


def test_the_pass_takes_the_call_with_what_was_recalled(brief, model):
    m = model([CALL])
    got = asyncio.run(repair_after_lookup.call_after_recall(ORDER, RECALLED, {"x": 1}))
    assert got == {"widget_id": "musica", "action": "play", "payload": CALL[1]["payload"]}
    system = m.seen[0][0]["content"]
    assert "the lead singer of that drama" in system, "what the recall found travels to the pass"
    assert "You recalled it" in system, "the recall's own system prompt, not the search's"


def test_no_call_or_another_card_is_nothing(brief, model):
    model([])
    assert asyncio.run(repair_after_lookup.call_after_recall(ORDER, RECALLED, {"x": 1})) is None
    model([("widget_data", {"widget_id": "agenda", "action": "add_meeting", "payload": {}})])
    assert asyncio.run(repair_after_lookup.call_after_recall(ORDER, RECALLED, {"x": 1})) is None


def _voice(**gate):
    applied, sent, acted, done = [], [], dict(gate.pop("acted", {})), {"v": gate.pop("done", False)}
    ran = asyncio.run(repair_after_lookup.voice_after_recall(
        ORDER, RECALLED, {"x": 1}, None, window=[], apply=lambda *a: applied.append(a), send=sent.append,
        emit=lambda *a, **k: None, acted=acted, done=done, **gate))
    return ran, applied, sent, acted, done


def test_the_voice_runs_it_and_marks_the_turn(brief, model):
    model([CALL])
    ran, applied, sent, acted, done = _voice()
    assert ran and applied == [("musica", "play", CALL[1]["payload"])]
    assert acted.get("widget") is True and done["v"] is True
    assert sent == [], "what it did is the turn's verdict — no tail said after the words"


@pytest.mark.parametrize("gate", [{"recalled": "empty_thread"}, {"acted": {"widget": True}}, {"done": True},
                                  {"music": {"query": "x"}}])
def test_it_stays_out_of_a_turn_that_is_not_its_own(brief, model, gate):
    m = model([CALL])
    ran, applied, *_ = _voice(**gate)
    assert not ran and applied == [] and m.seen == [], f"{gate}: no pass is paid"


def test_the_recall_lane_runs_it_after_the_recall_spoke():
    src = (ENGINE / "nucleo/flash/post_stream_lanes.py").read_text(encoding="utf-8")
    spoke = src.index("recall_spoken(")
    tree = ast.parse(src)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "voice_after_recall"]
    assert len(calls) == 1, "the recall lane does not carry the order out"
    kw = {k.arg for k in calls[0].keywords}
    assert {"recalled", "music", "acted", "done"} <= kw, f"its gate is not handed what it needs: {kw}"
    at = src.index("voice_after_recall(")
    assert spoke < at < src.index('_recall_empty_thread == "empty_thread"', at), \
        "after the recall spoke, before the empty-thread question"
