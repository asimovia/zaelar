"""A door with its own dialogue answers him in its own words, never the model's (node 13.151, C1 b).

The send owner asks and confirms a message itself: its line came back to the model as data and the model reworded it,
so the confirmation that sounded never ended in the draft's `confirm_line` and his first «yes» was refused. Now an act
declares that its ok result's `say` IS the answer (`ToolSpec.says == "door"`, `declared.json`): the run publishes that
line as is, with origin `door`, and asks the model nothing more.
"""
from __future__ import annotations

from conversation.ports import Done, EffectClass, ToolCall, ToolResult, ToolSpec
from conversation.testing.scripted_model import reply
from tests.conversation.unit.convkit import Harness

LINE = "W_Ana: «w_goodnight». w_send it?"


def test_a_doors_line_is_published_as_is_and_the_model_is_not_asked_again(store):
    h = Harness(store, grace=False)
    h.tools.specs.append(ToolSpec("w_draft", act="a5.draft", effect_class=EffectClass.WRITE, says="door"))
    h.tools.answers["w_draft"] = ToolResult("ok", data={"say": LINE})
    h.model.default = lambda ids: ([ToolCall("c1", "w_draft", {"to": "w_ana"}), Done()]
                                   if len(h.model.calls) == 1 else [reply("w_shall I send it to ana?"), Done()])
    h.typed("w_tell ana goodnight", 0)
    h.settle(3000)
    assert [o.text for o in h.mouth.orders] == [LINE] and len(h.model.calls) == 1
    assert ("conv_run", "door") in {(k, p.get("command")) for k, _lab, p in h.tel.events if isinstance(p, dict)}


def test_an_act_with_no_door_of_its_own_is_answered_by_the_model(store):
    h = Harness(store, grace=False)
    h.tools.answers["agenda_add"] = ToolResult("ok", data={"say": "w_not a door"})
    h.model.default = lambda ids: ([ToolCall("c1", "agenda_add", {"title": "w_x"}), Done()]
                                   if len(h.model.calls) == 1 else [reply("w9"), Done()])
    h.typed("w1", 0)
    h.settle(3000)
    assert [o.text for o in h.mouth.orders] == ["w9"]


def test_the_message_act_is_declared_a_door_and_its_confirmation_is_heard_whole(monkeypatch):
    from types import SimpleNamespace

    from nucleo.conversation_host import acts, routing
    from nucleo.send import draft, heard
    assert {s.name: s.says for s in acts.catalog()}["send_message"] == "door"
    d = SimpleNamespace(confirm_line=LINE, heard=False, heard_at=0, heard_mono=0)
    monkeypatch.setattr(draft, "current", lambda: d)
    monkeypatch.setattr(heard, "_talking", lambda: False)
    routing.ours_heard(LINE)                       # the door's line, as it sounded: it IS the confirmation
    assert d.heard is True
