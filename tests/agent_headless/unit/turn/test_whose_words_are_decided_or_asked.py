"""Whose are his words: when the flow judge runs out of time with an errand open, they join the errand he named last
(V2-886 D3; it was asked under V2-878 §3 (e), node 2.1678).

  · The flow judge has the turn's budget (`JUDGE_S`); past it the route read «no flow» and a refinement said while
    the model was slow opened a SECOND errand beside the one it refined. With an errand open a timeout is now
    `undecided`: the portal opens nothing and asks «for X, or something new?» on a row (the one asker, two declared
    answers in his language); his answer routes it. With no errand open, a timeout cannot happen (no judge is asked).

Disarm (seen red): the timeout read as `new` again.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from nucleo.turn import flow_door, flow_of

MONITOR = {"id": "w1", "request": "busca tres monitores de 27 pulgadas 4k por menos de 400", "label": "monitores",
           "parked": False}


@pytest.fixture
def judged(monkeypatch):
    """A flow judge that places everything in the monitor hunt; `slow` makes it miss the budget."""
    state = {"slow": False, "asked": []}

    def judge(text, live):
        state["asked"].append(text)
        if state["slow"]:
            time.sleep(0.3)
        return "w1"
    monkeypatch.setattr("nucleo.request.append.about_a_live_errand", judge)
    monkeypatch.setattr(flow_of, "candidates", lambda: [dict(MONITOR)])
    monkeypatch.setattr("nucleo.request.stop.verdict", lambda brief: None)
    monkeypatch.setattr(flow_of, "chat", lambda brief: False)
    return state


def _route(text):
    return asyncio.run(flow_of.route(text, brief=None))


@pytest.mark.parametrize("said", ["y que tengan altavoces integrados", "and they should have built-in speakers"])
def test_a_judge_out_of_time_joins_the_errand_he_named_last_and_asks_nothing(judged, monkeypatch, said):
    """V2-886 D3: the likely reading wins — no «for X, or something new?», no second errand."""
    monkeypatch.setattr(flow_of, "JUDGE_S", 0.05)
    judged["slow"] = True
    r = _route(said)
    assert r["as"] == flow_of.UNDECIDED and r["flow"] == "w1", "a judge out of time read as «no flow»"

    asked, relayed = [], []
    monkeypatch.setattr("nucleo.turn.which_flow.ask", lambda req, route, ctx: asked.append(req) or "a1")
    monkeypatch.setattr("nucleo.dispatch.relay_his_words", lambda flow, text: relayed.append(flow) or True)
    assert flow_door.obey(said, r, {}) is False, "the portal opened an errand anyway"
    assert relayed == ["w1"] and not asked, "a slow judge interrupted him with a question"


@pytest.mark.parametrize("lang,that,new", [("es", "Para lo de", "Algo nuevo"), ("en", "For", "Something new")])
def test_his_answer_routes_it(judged, monkeypatch, lang, that, new):
    from nucleo.turn import which_flow
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    opts = which_flow.options("monitores")
    assert opts[0].startswith(that) and opts[1] == new
    relayed, opened = [], []
    monkeypatch.setattr("nucleo.dispatch.relay_his_words", lambda which, words: relayed.append(which) or True)
    monkeypatch.setattr("nucleo.acts.errand.escalate_to_slowbrain", lambda req, context=None: opened.append(context) or 1)
    monkeypatch.setattr("nucleo.request.inline_ask.take", lambda ask_id: True)
    monkeypatch.setattr("nucleo.circuit.settle", lambda **k: None)
    entry = {"ask_id": "a1", "options": opts,
             "retained": {"kind": "which", "request": "y con altavoces", "flow": "w1", "context": {}}}
    assert which_flow.answered("u1", entry, opts[0], None)["into"] == "w1" and relayed == ["w1"] and not opened
    assert which_flow.answered("u1", entry, "", 1)["into"] == "" and opened == [{"routed": "new:"}]
    assert which_flow.answered("u1", entry, "pues no sé", None)["unclear"], "a reply that is neither answer decided"
