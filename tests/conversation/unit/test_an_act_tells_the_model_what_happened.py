"""An act tells the model what happened, and a run that acted never says it lost the answer (node 13.145, C4).

A widget act's receipt carries back what the card's door answered — its result, bounded — and, refused, WHY (the card's
own sentence when it has one, else its reason): acting blind, the model repeated a refused act to its step cap. A run
that hits its step cap after an act of it LANDED says that part was done (`lost_after_acts`), never «I lost that».
"""
from __future__ import annotations

import pytest

from conversation.config import Config
from conversation.ports import Done, ToolCall
from conversation.testing.fakes import FixedWords
from nucleo.conversation_host import acts_widget
from tests.conversation.unit.convkit import Harness


def test_the_receipt_carries_the_result_and_why_it_was_refused(monkeypatch):
    from nucleo.request import refusal_line
    monkeypatch.setattr(refusal_line, "speakable", lambda card, res: "w_no such day" if res.get("say") else "")
    ok = acts_widget.receipt("w_agenda", {"ok": True, "id": 7, "rows": list(range(20))}, True)
    assert ok["id"] == 7 and len(ok["rows"]) == acts_widget.RECEIPT_ITEMS + 1 and "why" not in ok
    said = acts_widget.receipt("w_agenda", {"ok": False, "say": "w_key", "error": "w_bad_day"}, False)
    assert said["why"] == "w_no such day" and said["error"] == "w_bad_day"
    bare = acts_widget.receipt("w_agenda", {"ok": False, "error": "w_bad_day"}, False)
    assert bare["why"] == "w_bad_day"


def test_a_large_answer_is_cut_to_the_cap_keeping_what_it_said_and_why(monkeypatch):
    from nucleo.request import refusal_line
    why = "w_" + "the card names its reason in full " * 60
    monkeypatch.setattr(refusal_line, "speakable", lambda card, res: why)
    rows = [{f"w_f{i}": "w_" + "x" * 300 for i in range(12)} for _ in range(40)]
    big = {"ok": False, **{f"w_extra{i}": "w_" + "y" * 390 for i in range(30)}, "rows": rows, "message": "w_saved 40"}
    got = acts_widget.receipt("w_card", big, False)
    assert got["message"] == "w_saved 40" and got["why"] == why, "its answer and its reason survive the cut"
    assert acts_widget._size({k: v for k, v in got.items() if k != "why"}) <= acts_widget.RECEIPT_MAX
    assert got[acts_widget.CUT] > 0, "a cut receipt says how many of its fields were cut"
    flat = acts_widget._bounded({f"w_k{i}": i for i in range(20)})
    assert flat[acts_widget.CUT] == 20 - acts_widget.RECEIPT_ITEMS, "a cut level says so too"


def test_a_field_that_does_not_fit_is_shrunk_never_dropped():
    """A view's answer (`view_data`-shaped): its first field keeps its first items, the whole under the cap."""
    rows = [{"w_from": f"w_person {i}", "w_subject": "w_" + "s" * 200, "w_body": "w_" + "b" * 900} for i in range(40)]
    view = {"ok": True, "result": {"w_items": rows, "w_total": 40}, "w_folder": "w_inbox",
            **{f"w_panel{i}": {"w_rows": rows} for i in range(5)}}
    got = acts_widget.receipt("w_mail", view, True)
    assert acts_widget._size(got) <= acts_widget.RECEIPT_MAX
    first = got["result"]
    shown = first if isinstance(first, str) else str(first)
    assert "w_person 0" in shown and "w_person 1" in shown, "its first field keeps its first items"
    assert got.get("w_folder") == "w_inbox" or got.get(acts_widget.CUT), "what does not fit is counted, not hidden"


def _cap(store, tool):
    h = Harness(store, grace=False, config=Config(max_steps=3))
    h.conv.words = FixedWords()
    h.model.default = lambda ids: [ToolCall(f"c{len(h.model.calls)}", tool, {"q": "w1"}), Done()]
    h.typed("w1", 0)
    h.settle(3000)
    return [o.text for o in h.mouth.orders]





@pytest.mark.parametrize("tool,line", [("agenda_add", "w_partly"), ("search", "w_lost")])
def test_a_run_that_acted_says_part_was_done_and_one_that_only_read_says_it_lost_it(store, tool, line):
    assert _cap(store, tool) == [line]
