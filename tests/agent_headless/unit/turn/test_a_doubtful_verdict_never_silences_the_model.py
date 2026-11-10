"""A verdict between LICENCE and VETO never overrules the model — its words stand and an inline answer keeps the turn;
membership in a live errand belongs to `flow_of`; a send is still held from LICENCE (node 3.186, V2-874).

Measured on a demo turn («open the one that's the best deal» while an errand searched): the brief's escalate verdict
at 0.54 routed the turn and silenced the model inline, `flow_of` injected the request into the live errand, and the
model's clarifying question was said anyway — three voices. The one rule (`nucleo.turn.commission`, in shadow):
the escalate verdict decides only errand vs inline; which errand is `flow_of`'s; the more specific question
(`errand_target`, `stop_errand`) wins over escalate; the model's words are silenced only at VETO; an act that leaves
is held from LICENCE (battery C9: the flip to escalate on sends came at 0.52-0.62). Rule (a), the one chosen: below VETO
the model's inline answer wins and the escalate verdict commissions nothing; a model that did nothing is licensed.
"""
from __future__ import annotations

import threading

import pytest

from nucleo import jev
from nucleo.turn import commission, verdicts

SAID = {"es": "abre el que sea mejor oferta", "en": "open the one that's the best deal"}


@pytest.fixture(params=["es", "en"])
def lang(request):
    return request.param


def _brief(escalate=None, target=None, stop=None):
    ev = threading.Event()
    ev.set()
    res = {"_call_id": "c1"}
    for key, val in (("escalate_or_inline", escalate), ("errand_target", target), ("stop_errand", stop)):
        if val is not None:
            res[key] = {"choice": val[0], "confidence": val[1]}
    return {"event": ev, "result": res}


@pytest.mark.parametrize("conf", [verdicts.LICENCE, 0.54, 0.7, 0.84])
def test_a_verdict_between_licence_and_veto_never_silences_the_model(lang, conf):
    w = commission.would(_brief(escalate=("escalate", conf)), flow_as="new", model_wrote=True)
    assert w["route"] == "inline" and not w["silence_words"] and not w["open_new"], (lang, conf, w)


@pytest.mark.parametrize("conf", [verdicts.LICENCE, 0.54, 0.84])
def test_a_model_that_did_nothing_is_licensed_into_an_errand(lang, conf):
    w = commission.would(_brief(escalate=("escalate", conf)), flow_as="new", model_wrote=False)
    assert w["route"] == "errand" and w["open_new"] and not w["silence_words"]


def test_the_models_own_hand_over_is_an_errand_at_any_confidence(lang):
    w = commission.would(_brief(escalate=("handle_inline", 0.9)), model_calls=[{"name": "escalate_to_slowbrain"}],
                         model_wrote=True, flow_as="new")
    assert w["route"] == "errand" and w["open_new"]


def test_variant_b_commissions_from_the_licence_beside_the_words(lang):
    w = commission.would(_brief(escalate=("escalate", 0.54)), flow_as="inject", model_wrote=True, variant="b")
    assert w["route"] == "errand" and not w["silence_words"] and not w["open_new"]


@pytest.mark.parametrize("conf", [verdicts.VETO, 0.95])
def test_at_veto_the_verdict_overrules_the_model_and_silences_it(lang, conf):
    w = commission.would(_brief(escalate=("escalate", conf)), model_wrote=True)
    assert w["silence_words"] and w["route"] == "errand"


def test_below_the_licence_the_turn_stays_inline(lang):
    w = commission.would(_brief(escalate=("escalate", 0.49)))
    assert w == {"route": "inline", "open_new": False, "silence_words": False, "hold_send": False}


@pytest.mark.parametrize("flow_as, opens", [("new", True), ("", True), ("inject", False), ("absorb", False),
                                            ("steer", False), ("reopen", False)])
def test_membership_in_a_live_errand_belongs_to_flow_of(lang, flow_as, opens):
    assert commission.would(_brief(escalate=("escalate", 0.6)), flow_as=flow_as)["open_new"] is opens


@pytest.mark.parametrize("target, stop, opens", [
    (("running_errand", 0.6), None, False),
    (("none", 0.9), None, True),
    (("running_errand", 0.3), None, True),        # unsure: not more specific than escalate
    (None, ("steer", 0.6), False),
    (None, ("settled", 0.5), False),
    (None, ("steer", 0.32), True),                # the demo turn's own reading: unsure, it does not count
    (None, ("keep", 0.9), True),
])
def test_the_more_specific_question_wins_over_escalate(lang, target, stop, opens):
    w = commission.would(_brief(escalate=("escalate", 0.7), target=target, stop=stop), flow_as="new")
    assert w["open_new"] is opens, (target, stop, w)


@pytest.mark.parametrize("call", [{"name": "reply_message", "args": {"text": "ok"}},
                                  {"name": "widget_data", "args": {"widget_id": "mensajeria", "action": "reply"}}])
def test_a_send_is_still_held_at_the_licence(lang, call):
    assert commission.leaves(call)
    w = commission.would(_brief(escalate=("escalate", verdicts.LICENCE)), model_calls=[call], model_wrote=True)
    assert w["hold_send"] and w["route"] == "errand", "a send is held even when the model wrote words"
    assert not commission.would(_brief(escalate=("escalate", 0.49)), model_calls=[call])["hold_send"]


def test_an_act_that_stays_on_the_machine_is_not_a_send(lang):
    call = {"name": "widget_data", "args": {"widget_id": "markets", "action": "range"}}
    assert not commission.leaves(call)
    assert not commission.would(_brief(escalate=("escalate", 0.6)), model_calls=[call])["hold_send"]


def test_the_shadow_says_both_and_changes_nothing(lang, monkeypatch):
    monkeypatch.setattr(jev, "_emit_read", lambda *a, **k: pytest.fail("the shadow added a jev read"))
    events, req = [], {"v": SAID[lang], "routed": True}
    before = dict(req)
    out = commission.shadow(lambda *a, **k: events.append((a, k)), at="close", text=SAID[lang], launched=True,
                            brief=_brief(escalate=("escalate", 0.54), target=("none", 0.9), stop=("steer", 0.32)),
                            escalate_req=req, flow_as="inject", words_said=False)
    assert req == before and len(events) == 1 and events[0][0][1] == commission.LABEL
    assert out["would"] == {"route": "errand", "open_new": False, "silence_words": False, "hold_send": False}
    assert out["did"]["silence_words"] and out["changes"] == ["silence_words"] and not out["model_wrote"]


def test_the_shadow_reads_the_held_words_as_the_models_answer(lang):
    req = {"v": SAID[lang], "routed": True, "held_words": "¿De qué es la oferta?" if lang == "es" else "Which deal?"}
    out = commission.shadow(lambda *a, **k: None, at="close", text=SAID[lang], launched=True, escalate_req=req,
                            brief=_brief(escalate=("escalate", 0.54), target=("none", 0.9), stop=("steer", 0.32)),
                            flow_as="inject", words_said=False)
    assert out["model_wrote"] and out["would"]["route"] == "inline" and out["would_b"]["route"] == "errand"
    assert set(out["changes"]) == {"route", "silence_words"} and out["changes_b"] == ["silence_words"]
    assert out["escalate"] == ["escalate", 0.54] and out["call_id"] == "c1" and out["flow_as"] == "inject"


def test_a_call_the_gate_held_is_the_models_inline_answer(lang):
    req = {"v": SAID[lang], "routed": True, "held_calls": [{"name": "search_listings", "args": {}}]}
    out = commission.shadow(lambda *a, **k: None, at="close", text=SAID[lang], launched=True, escalate_req=req,
                            brief=_brief(escalate=("escalate", 0.6)), flow_as="new", words_said=False)
    assert out["model_calls"] == ["search_listings"] and out["would"]["route"] == "inline"


def test_below_the_licence_the_shadow_leaves_the_turns_own_path(lang):
    req = {"v": None}
    out = commission.shadow(lambda *a, **k: None, at="close", text=SAID[lang], escalate_req=req, launched=False,
                            brief=_brief(escalate=("handle_inline", 0.76)), flow_as="inject", words_said=True,
                            model_calls=[{"name": "escalate_to_slowbrain", "args": {}}])
    assert out["changes"] == [] and out["changes_b"] == [], "another door dropped the model's own call: not the rule's"
