"""V2-792 — the promise harness (V2-790) never says «I have not done it» over a reply that is TRUE.

The class, as measured: a search ran and put six numbered videos on screen; the next turn's reply said «they're all
six on screen, numbered — tell me the number and I'll play it». Nothing ran in THAT turn, no second pass had a card,
and the turn end appended «I have not done it: I could not run it from here». Two holes:

  · the reply's verdict read `ask_first` (0.72); below `ASK_FIRST_MIN` it was cached as `act`, and the harness
    asked the phrase tables anyway — «te lo pongo» reads as a promise to them, though the act is HIS next choice;
  · a reply that DESCRIBES the screen an op of this request left there was treated as a claim over nothing.

The verdict now speaks before any table (`reply_promise.held_for_him`, any confidence), and a claimed state holds
when the previous acting turn's own op left its card open with nothing refused (`canvas_focus.last_turn_held`).
"""
from __future__ import annotations

import pytest

from nucleo import canvas_focus
from nucleo.flash import reply_promise as rp
from nucleo.turn import promise_kept as pk

ON_SCREEN = {
    "es": "Ya están los seis en pantalla, numerados; dime el número que quieras y te lo pongo.",
    "en": "All six are on screen, numbered — tell me the number you want and I'll put it on.",
}
CLAIM = {"es": "Ya lo tienes en pantalla, el primero de la lista.", "en": "There it is — it's on your screen."}
PROMISE = {"es": "Te lo pongo ahora mismo.", "en": "I'll put it on right now."}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    rp.reset()
    saved = {k: (list(v) if isinstance(v, list) else v) for k, v in canvas_focus._state.items()}
    from nucleo.flash import canvas_visibility
    monkeypatch.setattr(canvas_visibility, "open_ids", lambda: frozenset({"youtube"}))
    yield
    rp.reset()
    canvas_focus._state.update(saved)


def _verdict(monkeypatch, reply: str, choice: str, confidence: float) -> None:
    """Settle the reply's verdict through the real `_settle` — the downgrade below `ASK_FIRST_MIN` included."""
    from nucleo import jev
    answers = {"reply_promise": (choice, {"confidence": confidence}), rp.STATE_KEY: ("other", {"confidence": 1.0})}
    monkeypatch.setattr(jev, "read", lambda handle, key, default="": answers.get(key, (default, {})))
    rp._settle(rp._key(reply), {"event": None})


def _a_search_ran_last_turn(*, refused: bool = False) -> None:
    canvas_focus.note("transcript", "🗣", role="user")
    canvas_focus.note("widget", "data:search", extra={"id": "youtube", "src": "flash"})
    if refused:
        canvas_focus.note("widget", "action_failed", extra={"id": "youtube", "action": "search"})
    canvas_focus.note("transcript", "🗣", role="user")               # his next turn: the reply is about the screen


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_held_act_below_the_sure_mark_still_owes_nothing(monkeypatch, lang):
    reply = ON_SCREEN[lang]
    _verdict(monkeypatch, reply, "ask_first", 0.72)
    assert rp.verdict(reply) == "act", "the repair's reading is unchanged: below the mark it stays a promise"
    assert rp.held_for_him(reply)
    assert pk.close(reply, {}, acted=False) == "", "the next act is his choice — nothing was owed"


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_promise_the_verdict_reads_is_still_owed(monkeypatch, lang):
    _verdict(monkeypatch, PROMISE[lang], "act", 0.97)
    assert not rp.held_for_him(PROMISE[lang])
    assert pk.close(PROMISE[lang], {}, acted=False), "a promise to act now, with nothing run, is said undone"


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_claimed_state_an_op_of_this_request_left_on_screen_holds(monkeypatch, lang):
    _verdict(monkeypatch, CLAIM[lang], "none", 0.95)
    _a_search_ran_last_turn()
    assert canvas_focus.last_turn_held(["youtube"]) == "youtube"
    assert pk.close(CLAIM[lang], {}, acted=False) == ""


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_claim_over_nothing_or_over_a_refused_op_is_still_said_undone(monkeypatch, lang):
    _verdict(monkeypatch, CLAIM[lang], "none", 0.95)
    canvas_focus._state.update(previous=[], prev_failed=[], current=[])
    assert pk.close(CLAIM[lang], {}, acted=False), "nothing put it there"
    _a_search_ran_last_turn(refused=True)
    assert canvas_focus.last_turn_held(["youtube"]) == ""
    assert pk.close(CLAIM[lang], {}, acted=False), "the card refused the op: the claimed state does not hold"
    _a_search_ran_last_turn()
    assert pk.owed(CLAIM[lang], open_ids=[]) is True, "the card it acted on is closed now"


def test_with_the_verdict_absent_the_tables_still_decide():
    """The fallback is unchanged: no verdict, and «te lo pongo» reads as a promise to the tables."""
    assert pk.close(ON_SCREEN["es"], {}, acted=False)
