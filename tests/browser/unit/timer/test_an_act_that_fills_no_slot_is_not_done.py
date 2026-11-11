"""A card act whose call fills none of its declared slots is refused, said, and never reported done (V2-879).

Measured in the sandbox, es and en, 4 of 4: «pon un temporizador de 10 minutos» / «set a 10-minute timer» reached the
timer as `set {"minutes": 10}` (once `{"duration": 600}`). The card reads `seconds`, set 0, answered `ok: True`, and the
turn said «Listo» / «There you go» over a timer that never ran. The single funnel every mutation crosses
(`widgets/server_api._dispatch` → `contract.guard`) now refuses a call that carries keys of its own and fills none of
the act's declared slots, naming them; the turn's one mouth says the refusal in his language; and the timer declares
its end state (`running` is true), so the claim is checked against the card.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.circuit import verify
from nucleo.turn import reply
from nucleo.turn.reply import V
from widgets import contract, runtime, server_api
from widgets.timer import data as timer


@pytest.fixture(autouse=True)
def _clean_timer():
    timer.apply_action("reset", {})
    yield
    timer.apply_action("reset", {})


def _done_when() -> dict:
    return dict(((runtime.get("timer") or {}).get("actions") or {})["set"]["done_when"])


@pytest.mark.parametrize("payload", [{"minutes": 10}, {"duration": 600}])
def test_a_timer_set_in_another_vocabulary_is_refused_and_names_its_slot(payload):
    res = asyncio.run(server_api._dispatch("timer", "set", payload))
    assert res["ok"] is False and res["error"] == contract.SLOTS_UNFILLED, res
    assert "seconds" in res["unmet"], "the refusal does not name the slot the card reads"
    assert timer.view_data()["running"] is False, "the refused act still touched the card"
    assert verify.check(_done_when()) is False, "the declared end state reads as met over a timer that never ran"


@pytest.mark.parametrize("lang, done", [("es", ("Listo", "Hecho")), ("en", ("There you go", "Done")), ("ja", ())])
def test_the_turn_says_the_refusal_in_his_language_never_done(monkeypatch, lang, done):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    res = asyncio.run(server_api._dispatch("timer", "set", {"minutes": 10}))
    out = reply.of_op("timer", "set", res)
    assert out.verdict == V.UNMET.name, out
    said = res["message"].strip()
    assert said and not any(said.lower().startswith(d.lower()) for d in done), said   # a refusal, never a claim
    if lang in ("es", "en"):
        from i18n import langs
        assert res["message"] == langs.spec(lang).widget_slots_unfilled, "the line is not his language's"


def test_the_declared_slot_starts_the_timer_and_meets_its_end_state():
    res = asyncio.run(server_api._dispatch("timer", "set", {"seconds": 600, "label": "pasta"}))
    assert res.get("ok") is True and timer.view_data()["running"] is True, res
    assert verify.check(_done_when()) is True, "a running timer does not meet its declared end state"


def test_a_running_timer_reset_by_another_vocabulary_fails_its_end_state():
    """The card CHANGED (it was running, the call zeroed it), so the door keeps the card's answer — and the act's
    declared end state is what says it is not done."""
    asyncio.run(server_api._dispatch("timer", "set", {"seconds": 600}))
    res = asyncio.run(server_api._dispatch("timer", "set", {"minutes": 10}))
    assert res.get("ok") is not False and timer.view_data()["running"] is False
    assert verify.check(_done_when()) is False


def test_a_handler_that_reads_an_undeclared_key_keeps_working():
    """`documento.append` reads `text` beside its declared `body`: the act changed the card, so it stands."""
    res = asyncio.run(server_api._dispatch("documento", "append", {"text": "hola"}))
    assert res.get("ok") is True, res


def test_an_empty_call_stays_the_handlers_business():
    """`filter_list {}` clears a filter, `read {}` reads the newest: an EMPTY call is not «another vocabulary»."""
    spec = (runtime.get("youtube") or {})["actions"]["filter_list"]
    assert contract.unfilled("youtube", "filter_list", spec, {}) is None
    timer_set = (runtime.get("timer") or {})["actions"]["set"]
    assert contract.unfilled("timer", "set", timer_set, {"seconds": 600}) is None
    assert contract.unfilled("timer", "set", timer_set, {"seconds": 600, "minutes": 10}) is None
