"""A held act, or a fact missing to do it, is a reply — never a silent close (node 13.84, V2-941).

The live suite found the model choosing `no_reply` where it had something to say: «send a message to Rowan» read the
contacts and closed silent with the send held («the send is held… I can't send it»), and «and for dinner?» closed
silent while its own reason said the place was still unknown. The prefix DECLARES what each order is for — `no_reply`
for an entry not addressed to the assistant, or with nothing to say; a held or refused act, or missing information, a
reply saying so or asking — and what `complete` means: the person finished the thought, whether or not it can be
answered yet. Replayed with a scripted model: the act refused at the gateway reaches the model as its result, and the
reply that follows is said.
"""
from __future__ import annotations

from conversation.ports import Done, ToolCall
from conversation.testing.scripted_model import reply
from nucleo.conversation_host import prefix
from tests.conversation.unit.convkit import Harness


def _lines() -> dict:
    return dict(line.split(": ", 1) for line in prefix.build([], native="English", name="English").splitlines())


def test_the_orders_say_what_no_reply_is_for_and_that_a_held_act_is_a_reply():
    orders = _lines()["ORDERS"]
    assert orders.startswith("reply(text, claims, complete) | no_reply(reason, complete)")
    assert "no_reply: an entry not addressed to you, or nothing to say" in orders
    assert "an act held or refused, or information missing: a reply saying so or asking for it" in orders


def test_complete_is_whether_the_thought_is_finished_not_whether_it_can_be_answered():
    complete = _lines()["COMPLETE"]
    assert "finished this thought, whether or not you can answer it yet" in complete and "can be answered" not in \
        complete


def test_a_send_refused_at_the_gateway_reaches_the_model_and_its_reply_is_said(store):
    h = Harness(store, grace=False)
    rounds = [[ToolCall("c1", "send_message", {"to": "w2", "text": "w3"}), Done()], [reply("w9"), Done()]]
    h.model.default = lambda ids: rounds[min(len(h.model.calls) - 1, len(rounds) - 1)]
    h.utter([(["w1"], 0)])
    second = h.model.calls[1].prompt.steps
    assert [(c.name, r.status) for c, r in second] == [("send_message", "refused")]
    assert h.tools.calls == []                                                     # nothing left the gateway
    assert [o.text for o in h.mouth.orders] == ["w9"] and [lab for lab, _ in h.closes()] == ["answered"]
