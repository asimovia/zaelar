"""The ear's facts cross from the voice process to the body without loss (node 13.56, v3.1 §1.7, B8a).

  · the provider's messages become the ear's facts on ONE wall clock, fixed at a stream's first message: words with
    the turn as `seq` and the update count as `revision` (an open turn is rewritten), the end with its confidence
    as it came, the eager and resumed hints, and the watermark on every message — also one with no word;
  · on the line they ride a lane of their own at the front of every batch and leave it only when the body answered:
    a body that does not answer for a while loses nothing and declares nothing;
  · past the lane's ceiling the newest facts are not kept but DECLARED lost — one `gap` fact grows in their place;
  · the body applies each `seq` once (a batch carried again applies nothing twice), turns each fact into the
    package's signal, and a hole into `LinkGap`: what the ear was hearing there ends incomplete (`link_gap`).
"""
from __future__ import annotations

import asyncio

import pytest

from conversation.ear import signals as S
from nucleo.conversation_host import ear_in
from voice.engine.pipeline import body_link, ear_feed


def _msg(event, turn, words=(), end_s=1.0, start_s=0.0, prob=None):
    return {"event": event, "turn_index": turn, "audio_window_start": start_s, "audio_window_end": end_s,
            "end_of_turn_confidence": prob,
            "words": [{"word": w, "start": a, "end": b, "confidence": 0.9} for w, a, b in words]}


def test_the_providers_messages_become_facts_on_one_wall_clock():
    clock, turns = ear_feed.StreamClock(), ear_feed.Turns()
    first = ear_feed.from_turninfo(_msg("StartOfTurn", 1, [("w1", 0.1, 0.3)], end_s=0.4), stream="d1", clock=clock,
                                   turns=turns, now_ms=10_400)
    assert clock.t0_wall_ms == 10_000                                     # fixed once: arrival − audio time
    words, mark = first
    assert words["t"] == "words" and words["turn"] == 1 and words["rev"] == 1 and not words["final"]
    assert words["words"][0][1:3] == [10_100, 10_300] and mark == {"t": "mark", "stream": "d1", "through": 10_400,
                                                                     "arrived": 10_400}
    upd = ear_feed.from_turninfo(_msg("Update", 1, [("w1", 0.1, 0.3), ("w2", 0.4, 0.6)], end_s=0.8), stream="d1",
                                 clock=clock, turns=turns, now_ms=99_999)
    assert upd[0]["rev"] == 2 and upd[0]["window"][1] == 10_800           # the clock does not move with arrival
    silent = ear_feed.from_turninfo(_msg("Update", 1, end_s=1.2), stream="d1", clock=clock, turns=turns)
    assert [f["t"] for f in silent] == ["mark"]                           # the watermark, also with no word
    end = ear_feed.from_turninfo(_msg("EndOfTurn", 1, [("w1", 0.1, 0.3)], end_s=1.5, prob=0.83), stream="d1",
                                 clock=clock, turns=turns, terminal=True)
    assert [f["t"] for f in end] == ["words", "eot", "mark"] and end[0]["final"]
    assert end[1]["kind"] == "end" and end[1]["prob"] == 0.83 and end[1]["terminal"] is True
    eager = ear_feed.from_turninfo(_msg("EagerEndOfTurn", 2, end_s=2.0, prob=0.55), stream="d1", clock=clock,
                                   turns=turns)
    assert eager[0]["kind"] == "eager" and eager[0]["prob"] == 0.55


def test_the_body_turns_each_fact_into_the_ears_signal():
    got = ear_in.signals({"t": "words", "stream": "d1", "turn": 3, "rev": 2, "final": True,
                          "words": [["w1", 10, 20, 0.9]], "window": [5, 25]})
    assert got == [S.WordSpan("d1", 3, 2, True, (("w1", 10, 20, 0.9),), (5, 25))]
    assert ear_in.signals({"t": "eot", "stream": "d1", "kind": "end", "prob": 0.7, "t_ms": 30, "terminal": False}) == \
        [S.EotHint("d1", "flux", "end", 0.7, 30, False)]
    assert ear_in.signals({"t": "mark", "stream": "d1", "through": 40}) == [S.Watermark("d1", 40)]
    assert ear_in.signals({"t": "vad", "stream": "d1", "edge": "rise", "t_ms": 5, "echo_safe": False}) == \
        [S.VadEdge("d1", "rise", 5, False)]
    assert ear_in.signals({"t": "gap", "streams": ["d1", "d2"], "t_ms": 50}) == \
        [S.LinkGap("d1", 50), S.LinkGap("d2", 50)]


def test_the_body_applies_each_seq_once():
    ear_in._reset_for_tests()
    seen = []
    ev = {"k": "ear", "boot": "b1", "seq": 1, "t": "mark", "stream": "d1", "through": 40}
    assert ear_in.receive(ev, seen.append) == 1 and ear_in.receive(ev, seen.append) == 0       # carried again
    assert ear_in.receive({**ev, "boot": "b2"}, seen.append) == 1                              # a new process
    assert len(seen) == 2


def _link(fail_first: int, monkeypatch) -> tuple:
    link = body_link.BodyLink(base="http://127.0.0.1:1", token="t")
    delivered, calls = [], {"n": 0}

    async def deliver(batch):
        calls["n"] += 1
        if calls["n"] <= fail_first:
            link._fail_streak += 1
            return False
        delivered.extend(ev for ev in batch if ev.get("k") == "ear")
        link._fail_streak = 0
        return True

    monkeypatch.setattr(link, "_deliver", deliver)
    monkeypatch.setattr(body_link, "RETRY_GAP_S", 0.0)
    return link, delivered


def _run(link, facts: int, settle_s: float = 0.3) -> None:
    async def go():
        link.start()
        for i in range(facts):
            link.send_ear({"t": "mark", "stream": "d1", "through": i})
        await asyncio.sleep(settle_s)
        await link.aclose()
    asyncio.run(go())


def test_a_body_that_does_not_answer_for_a_while_loses_nothing(monkeypatch):
    link, delivered = _link(fail_first=25, monkeypatch=monkeypatch)
    _run(link, 250)
    assert [ev["seq"] for ev in delivered] == list(range(1, 251))            # every fact, once, in order
    assert not any(ev.get("t") == "gap" for ev in delivered) and not link._ear and link.stats["ear_lost"] == 0


def test_past_the_ceiling_the_loss_is_declared_by_one_gap(monkeypatch):
    monkeypatch.setattr(body_link, "EAR_MAX", 10)
    link = body_link.BodyLink(base="http://127.0.0.1:1", token="t")
    for i in range(25):
        link.send_ear({"t": "mark", "stream": "d1", "through": i})
    kinds = [ev["t"] for ev in link._ear]
    assert kinds == ["mark"] * 10 + ["gap"]                                   # the oldest kept, the newest declared
    gap = link._ear[-1]
    assert gap["covers"] == [11, 25] and gap["streams"] == ["d1"] and link.stats["ear_lost"] == 15


def test_a_hole_ends_what_the_ear_was_hearing_incomplete(store):
    from tests.conversation.unit.convkit import Harness
    h = Harness(store, grace=False)
    t = 1000
    ws = h.words(["w1"], t)
    h.hear(S.VadEdge("d1", "rise", t), S.WordSpan("d1", 1, 1, False, ws, (t, ws[-1][2])))
    assert h.conv.ear.open_ids()
    h.hear(S.LinkGap("d1", t + 400))
    assert not h.conv.ear.open_ids()                                       # at the hole itself, not at a later stall
    inc = [p for k, lab, p in h.tel.events if k == "conv_ear" and lab == "incomplete"]
    assert inc and inc[-1]["reason"] == "link_gap" and inc[-1]["refs"].get("iv")
    h.at(t + 2000).pump()
    assert "· cut off" in h.model.calls[-1].prompt.input                   # its run asks for it again
