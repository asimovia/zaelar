"""An everyday agenda edit follows the verdict (V2-781 T518, 2026-10-04).

Measured on the EN pair `agenda-everyday-edits__us` (ES 13/13 on the same code):
  · «And make it last until one» — verdict `agenda:move_meeting` 0.98; the promise repair read «I'll open it so
    you can see it» and synthesised `open_meeting`. A view the repair picks over a real op the verdict names is
    asked once more, for that op (CRIT-K2: the verdict completes the model).
  · «There's no piano on Tuesday October 13» — verdict `agenda:cancel_meeting` 1.00, brief `request_type=comment`;
    the model said «let me check», READ the agenda and the read's tool-less answer said «Got it — no piano on the
    13th» over a series that still held it. A read of the very card a sure verdict names, after the model itself
    promised to act, carries the op out. The text channel had no read-for-an-order repair at all.
"""
from __future__ import annotations


import pytest


MOVE = ("widget_data", {"widget_id": "agenda", "action": "move_meeting",
                        "payload": {"title": "Dental checkup", "endTime": "13:00"}})
CANCEL = ("widget_data", {"widget_id": "agenda", "action": "cancel_meeting",
                          "payload": {"title": "Piano lesson with Abril", "date": "2026-10-13"}})


class _Model:
    def __init__(self, *rounds):
        self.rounds, self.n = list(rounds), 0

    async def complete(self, messages, **kw):
        calls = self.rounds[self.n] if self.n < len(self.rounds) else []
        self.n += 1
        for name, args in calls:
            kw["on_tool_call"](name, args)


@pytest.fixture
def model(monkeypatch):
    import nucleo.llm.fast_client as fc
    from widgets import read as widget_read
    monkeypatch.setattr(widget_read, "read", lambda wid, *a, **k: "Piano lesson with Abril · Tuesdays 17:00")

    def use(*rounds):
        m = _Model(*rounds)
        monkeypatch.setattr(fc, "FastClient", lambda: m)
        return m
    return use


PARTE = {"executed": "widget_data", "widget": "agenda", "act": "show_day", "ops": [{"widget": "agenda", "act": "show_day"}],
         "answers": [("agenda", {"result": {"day": "2026-10-08", "meetings": [
             {"title": "Dental checkup with Dr Ruiz", "date": "2026-10-08", "startTime": "11:30"}]}})]}


def test_a_day_view_answers_with_that_days_rows_and_their_hours(tmp_path, monkeypatch):
    from widgets import store
    from widgets.agenda import data as agenda
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    agenda.apply_action("add_meeting", {"title": "Dental checkup", "date": "2026-10-08", "startTime": "11:30"})
    agenda.apply_action("add_meeting", {"title": "Piano", "date": "2026-10-07", "startTime": "17:00"})
    got = agenda.apply_action("show_day", {"day": "2026-10-08"})["result"]
    assert [m["title"] for m in got["meetings"]] == ["Dental checkup"] and got["meetings"][0]["startTime"] == "11:30"

