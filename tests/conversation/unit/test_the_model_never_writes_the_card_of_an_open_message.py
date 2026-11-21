"""The model never writes the card of a message being written (C2, pins 3 and 7).

His live session had two drafts: the send owner's, in memory, and the one the model wrote into the messaging card's
box with a widget action. A message has ONE draft, its owner's. C: with a draft open, a composition the model asks
for (an act whose declared event is a LOCAL type the send owner owns) is refused, the draft and why travel in its
receipt, and the card's door is never reached.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

CARD = "w_chat"


@pytest.fixture
def door(monkeypatch):
    from nucleo.acts import data_ops, frontend
    from nucleo.conversation_host import acts_widget
    from widgets import effects, instances, runtime
    from widgets import read as widget_read
    seen: dict = {"ran": []}
    acts_of = {"w_write": {"event": "messaging.draft_write", "payload": {"text": "x"}}, "w_look": {}}
    monkeypatch.setattr(runtime, "get", lambda wid: {"id": CARD, "actions": acts_of} if str(wid) == CARD else None)
    monkeypatch.setattr(effects, "_manifest", lambda wid: {"id": CARD, "actions": acts_of})
    monkeypatch.setattr(widget_read, "resolve", lambda named, text="": CARD if named == CARD else None)
    monkeypatch.setattr(instances, "data_target", lambda wid, open_ids: wid)
    monkeypatch.setattr(acts_widget, "_open", lambda: [])
    monkeypatch.setattr(frontend, "action_mode_now", lambda w, a, p=None: "fast")
    monkeypatch.setattr(acts_widget, "_mount", lambda *a, **k: None)

    async def dispatch(wid, action, payload, **kw):
        seen["ran"].append((wid, action, dict(payload)))
        return {"ok": True}
    monkeypatch.setattr(data_ops, "dispatch_and_report", dispatch)
    seen["run"] = lambda args: asyncio.run(acts_widget.widget_act(args, "x_w"))
    return seen


def _open_draft(monkeypatch, d):
    from nucleo.send import draft
    monkeypatch.setattr(draft, "current", lambda: d)


def test_with_a_draft_open_the_models_composition_is_refused_and_the_card_untouched(door, monkeypatch):
    _open_draft(monkeypatch, SimpleNamespace(target={"name": "W_Ana"}, who="w_ana", text="w_goodnight"))
    got = door["run"]({"widget": CARD, "action": "w_write", "payload": {"text": "w_other words"}})
    assert got.status == "refused" and got.data["reason"] == "its_owner" and door["ran"] == []
    assert got.data["draft"] == {"who": "W_Ana", "text": "w_goodnight"} and "owner" in got.data["why"]


def test_with_no_draft_or_an_act_that_composes_nothing_the_door_runs_as_before(door, monkeypatch):
    _open_draft(monkeypatch, None)
    assert door["run"]({"widget": CARD, "action": "w_write", "payload": {"text": "w_hi"}}).status == "ok"
    _open_draft(monkeypatch, SimpleNamespace(target={}, who="w_ana", text="w_goodnight"))
    assert door["run"]({"widget": CARD, "action": "w_look"}).status == "ok"
    assert [a for _w, a, _p in door["ran"]] == ["w_write", "w_look"]
