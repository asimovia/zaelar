"""An unsure verdict against the model's `stop_worker` lets the stop run (V2-886 D2, operator 2026-11-11).

It used to ASK («Do you want me to stop the task that's running, then?») and keep an «offer» his next «yes» could take
(refactor2710-99). The operator's rule — at the likely reading we act and he corrects — made both go: the model's call
is the order unless a SURE verdict reads no stop; the doubt is recorded, never put to him. The backstop (no model
call) still stops only on a sure verdict.

Disarm: `against_the_model` returning `ask_which` again in the LICENCE..VETO band → the stop does not run → red.
"""
from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from nucleo.request import stop as sd
from nucleo.flash import tool_executor_calls as _calls
from nucleo.turn import brief as _tb


def _brief(stop: str | None, confidence: float, *, kind: str = "order"):
    ev = threading.Event()
    ev.set()
    result = {_tb.REQUEST_KEY: {"choice": kind, "confidence": 0.9}}
    if stop is not None:
        result[sd.KEY] = {"choice": stop, "confidence": confidence}
    return {"event": ev, "turn_id": "t-1", "open_ids": [], "result": result}


def _model_calls_stop(text: str, brief, monkeypatch) -> tuple[list, dict]:
    from nucleo import dispatch
    killed: list = []
    monkeypatch.setattr(dispatch, "cancel_soon", lambda w: killed.append(w) or ["1"])
    clarify: dict = {}
    _calls._t_stop_worker(args={"which": "the running errand"}, _norm_nfkd=lambda s: s.lower(),
                          _say=lambda: SimpleNamespace(stop_which_worker="which?"),
                          clarify=clarify, emit=lambda *a, **k: None, text=text,
                          worker_acted={"v": None}, brief=brief)
    return killed, clarify


@pytest.mark.parametrize("said", ["yeah just give it to me straight", "vale, déjalo, dímelo tú"])
def test_an_unsure_verdict_against_the_stop_lets_it_run_and_asks_nothing(said, monkeypatch):
    killed, clarify = _model_calls_stop(said, _brief("keep", 0.65), monkeypatch)
    assert killed == ["the running errand"] and not clarify.get("msg"), "a doubt of ours became his question"


def test_a_sure_verdict_still_vetoes_the_stop(monkeypatch):
    killed, clarify = _model_calls_stop("keep looking, I meant the other one", _brief("keep", 0.92), monkeypatch)
    assert killed == [] and not clarify.get("msg")


def test_the_backstop_stops_nothing_on_an_unsure_verdict(monkeypatch):
    from nucleo import dispatch
    monkeypatch.setattr(dispatch, "has_active", lambda: True)
    monkeypatch.setattr(dispatch, "cancel_soon", lambda w: ["1"])
    assert sd.repair(_brief("stop", 0.4), "yes, stop it", escalating=False) == []
