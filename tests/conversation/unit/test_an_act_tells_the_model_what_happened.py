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
    assert ok["result"]["id"] == 7 and len(ok["result"]["rows"]) == acts_widget.RECEIPT_ITEMS + 1 and "why" not in ok
    said = acts_widget.receipt("w_agenda", {"ok": False, "say": "w_key", "error": "w_bad_day"}, False)
    assert said["why"] == "w_no such day" and said["result"]["error"] == "w_bad_day"
    bare = acts_widget.receipt("w_agenda", {"ok": False, "error": "w_bad_day"}, False)
    assert bare["why"] == "w_bad_day"


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
