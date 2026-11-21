"""The cold-turn attention judge starts on the EAGER end of turn, and the gate still waits for a verdict (cloud speed (iii)).

Measured on a cloud test Machine (2026-11-19): a COLD turn (after 30 s of silence) paid the judge — one model call,
~1.0-1.25 s — in series after the ear confirmed the turn and before the prompt. Now `attention.prefire` starts it on the
words the ear announced (`brief_turn.fire_early`), and `evaluate_content` uses that verdict when the turn opens: the
call overlaps the end-of-turn wait. Nothing about the decision moves: the gate still awaits a verdict before anything
acts, a prefired judgement is reused only for the SAME words with the SAME frame, and otherwise it judges as always.
"""
from __future__ import annotations

import asyncio

import pytest

from voice import attention

LINE = "I can book it for Thursday, shall I?"


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for k in ("ZAELAR_ATTENTION", "ZAELAR_ATTENTION_WINDOW", "ZAELAR_WAKEWORDS"):
        monkeypatch.delenv(k, raising=False)
    attention.reset()
    monkeypatch.setattr(attention._prefire, "_last_said", lambda: LINE)
    yield
    attention.reset()
    attention.set_directed_judge(None)


def _judge(calls, *, delay=0.3, directed=True):
    async def judge(text, context):
        calls.append((text, context))
        await asyncio.sleep(delay)
        return {"directed": directed, "request": True}
    return judge


def test_a_cold_turn_is_judged_once_from_the_eager_end_and_the_gate_waits_only_what_is_left():
    calls: list = []
    attention.set_directed_judge(_judge(calls, delay=0.3))

    async def run():
        attention.prefire("Yes, book it")              # the ear announced the end of turn
        await asyncio.sleep(0.25)                       # …and confirmed it a moment later
        t0 = asyncio.get_running_loop().time()
        v = await attention.evaluate_content("Yes, book it", context=LINE)
        return v, asyncio.get_running_loop().time() - t0
    v, waited = asyncio.run(run())
    assert v.directed and v.judged
    assert calls == [("Yes, book it", LINE)], "one call, started on the eager end of turn"
    assert waited < 0.2, f"the gate waited only what was left of the judge ({waited:.2f} s)"


@pytest.mark.parametrize("final_text, frame", [("Yes, book it for Friday", LINE), ("Yes, book it", "Something else.")])
def test_other_words_or_another_frame_are_judged_again(final_text, frame):
    calls: list = []
    attention.set_directed_judge(_judge(calls, delay=0.01))

    async def run():
        attention.prefire("Yes, book it")
        await asyncio.sleep(0.05)
        return await attention.evaluate_content(final_text, context=frame)
    asyncio.run(run())
    assert calls[-1] == (final_text, frame) and len(calls) == 2, "the verdict judges the words and frame of the turn"


def test_the_spoken_lead_in_before_the_reply_does_not_waste_the_early_verdict(monkeypatch):
    """The timeline's line is what was SAID — the lead-in cover and then the reply; the gate's frame is the reply alone
    (`_last_reply`). Measured on a cloud Machine 2026-11-19: with an exact match the early verdict was reused in 1 cold
    turn of ~5. A frame that ENDS in the reply is the same frame."""
    calls: list = []
    attention.set_directed_judge(_judge(calls, delay=0.01))
    monkeypatch.setattr(attention._prefire, "_last_said", lambda: "Ya voy… " + LINE)

    async def run():
        attention.prefire("Yes, book it")
        await asyncio.sleep(0.05)
        return await attention.evaluate_content("Yes, book it", context=LINE)
    assert asyncio.run(run()).directed and len(calls) == 1, "one judge call: the lead-in is not another frame"


def test_an_ambient_verdict_still_stops_the_turn():
    calls: list = []
    attention.set_directed_judge(_judge(calls, delay=0.01, directed=False))

    async def run():
        attention.prefire("pass me the salt")
        await asyncio.sleep(0.05)
        return await attention.evaluate_content("pass me the salt", context=LINE)
    assert asyncio.run(run()).directed is False


def test_a_warm_turn_starts_no_judge():
    calls: list = []
    attention.set_directed_judge(_judge(calls, delay=0.01))
    attention.note_directed()

    async def run():
        attention.prefire("and the other one")
        await asyncio.sleep(0.05)
    asyncio.run(run())
    assert calls == [], "inside the conversation window nobody judges"

