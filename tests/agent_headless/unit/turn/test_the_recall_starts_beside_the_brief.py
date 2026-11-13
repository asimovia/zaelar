"""The durable recall starts beside the brief and nothing waits for it that does not need it (V2-903, P1-3 + P2-4).

The audit measured the class: a regex of ~150 expressions decided whether a turn recalled — it fired on 14 of 20
everyday Spanish sentences and on none of a real Japanese memory question — and the recall ran IN SERIES before the
model call, up to 800 ms; then the model call waited up to 350 ms more for the brief, only to pick the cover.

  · a recall started at the eager end of turn and arrived is taken with no wait, in any language;
  · a recall in flight is dropped, with no alarm, the moment the brief is SURE the turn needs none;
  · an unsure or absent verdict waits for the recall — never past the budget counted from its START;
  · no word table routes it: `needs_recall` is gone and the brief asks the question;
  · the cover never holds the model call: a brief in flight arms the cover when it lands.
"""
from __future__ import annotations

import asyncio
import threading
import time

import pytest

from nucleo.turn import recall_ahead, recall_budget

SLOW = 0.30


@pytest.fixture(autouse=True)
def _doubles(monkeypatch):
    from nucleo.turn.prompt import recall as recall_mod

    def _compose(q="", timings=None, lexical_only=False, skip_newest=None, his_words=""):
        if lexical_only:
            return "", []
        time.sleep(SLOW)
        return ("── RECALL ──\n· his dog is called Toby", [7])

    monkeypatch.setattr(recall_mod, "compose_recall", _compose)
    published: list = []
    monkeypatch.setattr(recall_budget, "_publish", lambda *a: published.append(a))
    monkeypatch.setattr(recall_budget, "_reinforce_delivered", lambda propias: None)
    monkeypatch.setenv("ZAELAR_RECALL_BUDGET_MS", "800")
    recall_ahead._reset_for_tests()
    yield published
    recall_ahead._reset_for_tests()


def _brief(choice: str | None, confidence: float = 0.95, *, landed: bool = True) -> dict:
    ev = threading.Event()
    result = {recall_ahead.KEY: {"choice": choice, "confidence": confidence, "probs": {}}} if choice else {}
    if landed:
        ev.set()
    return {"event": ev, "result": result}


@pytest.mark.parametrize("said", ["¿cómo se llama mi perro?", "what's my dog's name?", "私の犬の名前は何だっけ？"])
def test_a_recall_started_early_is_taken_without_waiting(said):
    async def go():
        recall_ahead.launch(said)                    # the eager end of turn
        await asyncio.sleep(SLOW + 0.05)             # the ear confirms the turn later
        t0 = time.monotonic()
        timings: dict = {}
        block, ids = await recall_ahead.take(said, _brief(None, landed=False), timings)
        return block, ids, time.monotonic() - t0, timings
    block, ids, waited, timings = asyncio.run(go())
    assert "Toby" in block and ids == [7], "the recall started at the eager end of turn was not the one taken"
    assert waited < 0.05, f"the turn waited {waited:.3f}s for a recall that had already arrived"
    assert timings["recall_ahead"] is True


def test_a_sure_none_drops_the_recall_in_flight_without_an_alarm(_doubles):
    async def go():
        t0 = time.monotonic()
        timings: dict = {}
        got = await recall_ahead.take("pon música de Queen", _brief(recall_ahead.NONE), timings)
        return got, time.monotonic() - t0, timings
    (block, ids), waited, timings = asyncio.run(go())
    assert block == "" and ids == []
    assert waited < 0.1, f"a turn the brief said needs no memory waited {waited:.3f}s for it"
    assert timings.get("recall_not_needed") is True
    assert not _doubles, f"an unneeded recall was published as a lost one: {_doubles}"


@pytest.mark.parametrize("brief", [_brief(recall_ahead.REMEMBER), _brief(recall_ahead.NONE, 0.6), None,
                                   _brief(None, landed=False)])
def test_without_a_sure_none_the_turn_waits_for_the_recall(brief):
    async def go():
        return await recall_ahead.take("pídeme la pizza de siempre", brief, {})
    block, _ids = asyncio.run(go())
    assert "Toby" in block, "an unsure or absent verdict let the turn go without the recall"


def test_the_budget_runs_from_the_launch_not_from_the_wait(monkeypatch):
    monkeypatch.setenv("ZAELAR_RECALL_BUDGET_MS", "200")

    async def go():
        recall_ahead.launch("where did I park last week?")
        await asyncio.sleep(0.15)
        t0 = time.monotonic()
        got = await recall_ahead.take("where did I park last week?", None, {})
        return got, time.monotonic() - t0
    _got, waited = asyncio.run(go())
    assert waited < 0.11, f"waited {waited:.3f}s: the budget restarted at the wait (50 ms of it were left)"


def test_no_word_table_routes_the_recall():
    from nucleo.flash import recall_heuristics
    from nucleo.turn import brief
    from voice.engine.llm.providers import turn_prompt
    import inspect
    assert not hasattr(recall_heuristics, "needs_recall"), "the regex router of the recall is back"
    assert recall_ahead.KEY in brief.asked_keys(), "the brief no longer asks whether the turn needs memory"
    src = inspect.getsource(turn_prompt.compose_the_prompt)
    assert "recall_ahead.take(" in src and "needs_recall" not in src


def test_the_eager_end_of_turn_starts_the_recall(monkeypatch):
    from nucleo.turn import brief, brief_turn
    monkeypatch.setattr(brief, "ask_for_turn", lambda text, **k: {"event": threading.Event(), "result": None})
    brief_turn._PREFIRED.clear()

    async def go():
        brief_turn.fire_early("¿qué te dije de mi viaje a Japón?")
        return recall_ahead._AHEAD.get(recall_ahead._key("Qué te dije de mi viaje a Japón"))
    assert asyncio.run(go()) is not None, "the eager end of turn fired the brief and left the recall for later"
    brief_turn._PREFIRED.clear()


def test_the_cover_never_holds_the_model_call(monkeypatch):
    from voice.engine.speech import filler_audio as fa
    fa._reset_for_tests()
    monkeypatch.setattr(fa, "enabled", lambda: True)
    monkeypatch.setattr(fa, "answering_fast", lambda: False)
    monkeypatch.setattr(fa, "stranded", lambda: False)
    monkeypatch.setattr("nucleo.style_policy.filler_allowed", lambda k: True)
    brain = type("B", (), {"_last_reply": "", "_last_filler": ""})()
    late = _brief(None, landed=False)

    async def go():
        msgs = [{"role": "user", "content": "¿me buscas un hotel en Soria?"}]
        t0 = time.monotonic()
        now = fa.cover_the_turn(brain, "¿me buscas un hotel en Soria?", messages=msgs, brief=late,
                                still_silent=lambda: True)
        returned = time.monotonic() - t0
        armed_before = fa._arm
        late["event"].set()                           # the brief lands while the model is already being paid
        await asyncio.sleep(0.1)
        return now, returned, armed_before, fa._consume_arm(), msgs
    now, returned, armed_before, armed_after, msgs = asyncio.run(go())
    assert returned < 0.02, f"the cover held the model call {returned:.3f}s"
    assert now == "" and armed_before is None
    assert armed_after is not None, "the brief landed and no cover was armed"
    assert fa.MAY_COVER_NOTE in msgs[-1]["content"], "the model was not told a cover may sound"
    fa._reset_for_tests()


def test_a_late_cover_never_sounds_after_the_first_word(monkeypatch):
    from voice.engine.speech import filler_audio as fa
    fa._reset_for_tests()
    monkeypatch.setattr(fa, "enabled", lambda: True)
    monkeypatch.setattr(fa, "answering_fast", lambda: False)
    monkeypatch.setattr(fa, "stranded", lambda: False)
    monkeypatch.setattr("nucleo.style_policy.filler_allowed", lambda k: True)
    brain = type("B", (), {"_last_reply": "", "_last_filler": ""})()
    late = _brief(None, landed=False)

    async def go():
        fa.cover_the_turn(brain, "¿me buscas un hotel en Soria?", messages=[{"role": "user", "content": "x"}],
                          brief=late, still_silent=lambda: False)
        late["event"].set()
        await asyncio.sleep(0.1)
        return fa._consume_arm()
    assert asyncio.run(go()) is None, "a cover was armed for a turn that had already spoken"
    fa._reset_for_tests()
