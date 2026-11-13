"""On voice, the brief is asked with the same context as on text — and a text turn can run the voice path (V2-903 P1-2).

The audit read it: with the Flux ear the brief left at the eager end of turn without our previous reply, the errands in
flight or the turn id, and admission reused it as is — what admission brought was dropped. Our previous reply is what
keeps a curt «enduro» or «sí» from reading as a new order (V2-716). The text channel, where every bench runs, never took
that path: green on the bench, different on the microphone.

  · the early brief and the admitted one ask the SAME questions when the state is the same (compared, not assumed);
  · an early brief asked with another state (our reply moved, an errand started) is asked again at admission;
  · a reused early brief carries the admitting turn's id;
  · `run_turn(voice_path=True)` runs a typed line down the microphone's path: the eager brief, reused at admission,
    and the cover decided as for speech.
"""
from __future__ import annotations

import asyncio
import threading

import pytest

from nucleo.turn import brief, brief_turn


@pytest.fixture
def asked(monkeypatch):
    """Every brief trip, by its questions. The trip lands at once."""
    from nucleo import jev
    trips: list[dict] = []

    def _ask_many(said, questions, *, name="", question_id="", after=None):
        trips.append({"said": said, "questions": questions})
        ev = threading.Event()
        ev.set()
        return {"event": ev, "result": {}}

    monkeypatch.setattr(jev, "enabled", lambda: True)
    monkeypatch.setattr(jev, "ask_many", _ask_many)
    monkeypatch.setattr("nucleo.flash.show_target._running_goals", lambda: ["find a flat to rent in Lisbon"])
    monkeypatch.setattr(brief, "_worker_state", lambda: (True, []))
    monkeypatch.setattr(brief, "_threads", lambda: [])
    brief_turn._PREFIRED.clear()
    yield trips
    brief_turn._PREFIRED.clear()
    brief_turn.bind(type("Nobody", (), {})())


class _Brain:
    def __init__(self, last_reply: str):
        self._last_reply, self._window, self._acc_gen = last_reply, [], 0


@pytest.mark.parametrize("said,ours", [("enduro", "¿Qué tipo de moto buscas: trail, enduro o carretera?"),
                                       ("yes, the second one", "Shall I book the first or the second hotel?")])
def test_the_early_brief_asks_what_the_admitted_one_asks(asked, said, ours):
    brain = _Brain(ours)
    brief_turn.bind(brain)
    brief_turn.fire_early(said)                                  # the ear's eager end of turn: no turn yet
    brief_turn._PREFIRED.clear()                                 # the same sentence asked as admission asks it
    brief.ask_for_turn(said, running_goals=["find a flat to rent in Lisbon"], last_reply=ours, turn_id="t-1")
    early, admitted = asked
    assert early["questions"] == admitted["questions"], "the voice path asked the brief with less than the text path"
    assert ours[:60] in str(early["questions"][brief.REQUEST_KEY]), "our previous reply is missing from the early brief"


def test_an_early_brief_asked_with_another_state_is_asked_again(asked):
    brain = _Brain("¿Lo reservo?")
    brief_turn.bind(brain)
    early = brief_turn.fire_early("sí")
    brain._last_reply = "Two flats match. Want the cheaper one?"     # our reply moved before the turn was admitted
    got = brief.ask_for_turn("sí", running_goals=["find a flat to rent in Lisbon"], last_reply=brain._last_reply,
                             turn_id="t-2")
    assert got is not early and len(asked) == 2, "admission reused a brief asked about another previous reply"
    assert "Two flats match" in str(asked[1]["questions"][brief.REQUEST_KEY])


def test_a_reused_early_brief_carries_the_admitting_turn(asked):
    brain = _Brain("¿Lo reservo?")
    brief_turn.bind(brain)
    early = brief_turn.fire_early("sí, resérvalo")
    assert early.get("turn_id") is None
    got = brief.ask_for_turn("Sí, resérvalo.", running_goals=["find a flat to rent in Lisbon"],
                             last_reply="¿Lo reservo?", turn_id="t-3")
    assert got is early and len(asked) == 1, "the same sentence, the same state, and the brief was paid twice"
    assert got["turn_id"] == "t-3", "the reused early brief does not say which turn it belongs to"


class _StreamStop(Exception):
    pass


class _NoNetworkFastClient:
    async def stream(self, *_a, **_kw):
        raise _StreamStop("no network in this test")
        yield  # pragma: no cover


def test_a_text_turn_can_run_the_voice_path(asked, monkeypatch, tmp_path):
    from memory import db as memdb
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    memdb.reset_db()
    monkeypatch.setattr("nucleo.llm.fast_client.FastClient", _NoNetworkFastClient)
    from voice.engine.speech import filler_audio as fa
    covered: list = []
    monkeypatch.setattr(fa, "enabled", lambda: True)

    async def _decide(*a, **k):
        covered.append(k.get("typed"))
        return ""
    monkeypatch.setattr(fa, "decide_and_arm", _decide)
    from nucleo.cli import turn
    sid = "test-voice-path"
    try:
        out = asyncio.run(turn.run_turn("abre la agenda de mañana", sid=sid, ingest=False, voice_path=True,
                                        eager_lead_s=0.05))
        typed_out = asyncio.run(turn.run_turn("abre la agenda de pasado", sid=sid, ingest=False))
    finally:
        turn.reset(sid)
        memdb.reset_db()
        from nucleo import done_ops
        done_ops.reset()            # the turn opened a card: what it did is not the next test's «what we just did»
    briefs = [t for t in asked if t["said"].lower().startswith("abre la agenda de mañana")]
    assert len(briefs) == 1, f"the eager brief was not the one the voice-path turn used: {len(briefs)} trips"
    assert covered[:1] == [False], "the voice-path turn decided its cover as a typed line"
    assert covered[1:] == [True], "a plain typed turn stopped being typed"
    assert out.get("voice_path", {}).get("early_brief") == "reused", out
    assert "voice_path" not in typed_out
