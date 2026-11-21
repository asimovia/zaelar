"""A door with its own dialogue answers him in its own words, never the model's (node 13.151, C1 b).

The send owner asks and confirms a message itself: its line came back to the model as data and the model reworded it,
so the confirmation that sounded never ended in the draft's `confirm_line` and his first «yes» was refused. Now the
RESULT says it (`{"say": line, "says": "door"}`): whatever act reached the owner — the message act or a widget's
message act — the run publishes that line as is, with origin `door`, asks the model nothing more, and names any call
of the same answer it therefore never ran.
"""
from __future__ import annotations

import asyncio

from conversation.ports import Done, ToolCall, ToolResult
from conversation.testing.scripted_model import reply
from tests.conversation.unit.convkit import Harness

LINE = "W_Ana: «w_goodnight». w_send it?"


def test_a_doors_line_is_published_as_is_and_the_model_is_not_asked_again(store):
    h = Harness(store, grace=False)
    h.tools.answers["task.start"] = ToolResult("ok", data={"say": LINE, "says": "door"})   # a write act with a door
    h.model.default = lambda ids: ([ToolCall("c1", "task.start", {"to": "w_ana"}), ToolCall("c2", "agenda_add", {}),
                                    Done()] if len(h.model.calls) == 1 else [reply("w_shall I send it?"), Done()])
    h.typed("w_tell ana goodnight", 0)
    h.settle(3000)
    assert [o.text for o in h.mouth.orders] == [LINE] and len(h.model.calls) == 1
    assert ("conv_run", "door") in {(k, p.get("command")) for k, _lab, p in h.tel.events if isinstance(p, dict)}
    skipped = [p for k, _lab, p in h.tel.events if isinstance(p, dict) and p.get("command") == "door_skipped"]
    assert skipped and skipped[0]["tools"] == ["agenda_add"] and [c[0] for c in h.tools.calls] == ["task.start"]


def test_an_act_whose_result_is_no_door_line_is_answered_by_the_model(store):
    h = Harness(store, grace=False)
    h.tools.answers["agenda_add"] = ToolResult("ok", data={"say": "w_not a door"})
    h.model.default = lambda ids: ([ToolCall("c1", "agenda_add", {"title": "w_x"}), Done()]
                                   if len(h.model.calls) == 1 else [reply("w9"), Done()])
    h.typed("w1", 0)
    h.settle(3000)
    assert [o.text for o in h.mouth.orders] == ["w9"]


def test_a_widgets_message_act_reaches_the_owner_and_comes_back_a_door_line(monkeypatch):
    from types import SimpleNamespace

    from nucleo.conversation_host import acts_widget, routing
    from nucleo.send import draft, heard, owner
    monkeypatch.setattr(acts_widget, "_widget_target", lambda args: ("w_chat", "w_send", {"text": "w_hi",
                                                                                           "_message": True}))

    async def intake(said, hint=None, last_line="", before=None, by="call"):
        return LINE
    monkeypatch.setattr(owner, "intake", intake)
    got = asyncio.run(acts_widget.widget_act({"widget": "w_chat", "action": "w_send"}, "e1"))
    assert got.status == "ok" and got.data == {"say": LINE, "says": "door"}
    d = SimpleNamespace(confirm_line=LINE, heard=False, heard_at=0, heard_mono=0)
    monkeypatch.setattr(draft, "current", lambda: d)
    monkeypatch.setattr(heard, "_talking", lambda: False)
    routing.ours_heard(LINE)                       # the door's line, as it sounded: it IS the confirmation
    assert d.heard is True


class _HangsAfterTheAct:
    """A provider that calls the door's act and then holds its stream past the gap's deadline."""

    def __init__(self):
        self.calls = []

    async def stream(self, prompt, tools, *, run_id, model_id):
        self.calls.append(model_id)
        yield ToolCall("c1", "task.start", {"to": "w_ana"})
        await asyncio.sleep(10)
        yield ToolCall("c2", "agenda_add", {})


def test_a_provider_late_after_the_doors_line_never_fails_the_answered_run(store):
    from conversation.config import Config
    h = Harness(store, grace=False, config=Config(model_gap_ms=30))
    h.conv.model = _HangsAfterTheAct()
    h.tools.answers["task.start"] = ToolResult("ok", data={"say": LINE, "says": "door"})
    h.typed("w_tell ana goodnight", 0)
    h.settle(2000)
    assert [o.text for o in h.mouth.orders] == [LINE], "one line, the owner's: no «I lost that» after it"
    assert [lab for lab, _p in h.closes()] == ["answered"], "the batch is answered once, never failed after"
    skipped = [p for k, _lab, p in h.tel.events if isinstance(p, dict) and p.get("command") == "door_skipped"]
    assert skipped and skipped[0]["tools"] == ["unknown"]
