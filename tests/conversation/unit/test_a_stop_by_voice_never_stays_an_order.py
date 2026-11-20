"""A barge-in that stopped our reply never stays an order (node 13.111, V2-941, v3.1 — the voice pass on 1800c4bcc).

«Para, para» over our reply is not a stop form, so it is his words: the model closed it silent (right), and then
closed his next two fresh questions silent too («he says "para, para"…», «he expressly asks for silence…») — it kept
obeying the stop it read in CONVERSATION. No text is read to fix it:

  · a batch whose voice began while a line of ours sounded and that line ended CUT by his voice is a barge-in; when its
    run ends silent, the window holds that FACT («[he stopped our reply]»), never his words;
  · a no_reply to his voice is the model's judgement: it stands, never asked again —
    another voice, the television or a word to someone else is silence; the `command` event says `not_his`.
"""
from __future__ import annotations

from conversation.ear import signals as S
from conversation.mouth import SayEnded
from conversation.ports import Command, Done
from conversation.testing.scripted_model import reply
from tests.conversation.unit.convkit import Harness
from tests.conversation.unit.test_a_wordless_barge_in_gives_the_line_back import _speaking


def _commands(h):
    return [p.get("command") for k, lab, p in h.tel.events if k == "conv_run" and lab == "command"]


def _barge_in(store):
    """Our line sounds on d1; his «w_para w_para» rises over it and our line ends cut; the model says nothing."""
    h = Harness(store, grace=False)
    sid = _speaking(h)
    start = next(row for _k, row in h.store.view(h.conv.account).recent("says", 2))["t_ms"]
    h.model.default = lambda ids: [Command("no_reply", {"reason": "w0"}), Done()]
    h.hear(S.VadEdge("d1", "rise", start + 50))
    h.conv.ack(SayEnded(sid, "cut", 4, start + 600, "d1", "agent_estimate"))
    h.utter([(["w_para", "w_para"], 0)], at=start + 40)
    h.settle(3000)
    return h


def test_his_barge_in_ends_silent_and_his_next_questions_are_answered(store):
    h = _barge_in(store)
    assert "no_reply_voice" not in _commands(h)                               # a stop may be silence: it stands
    h.model.default = lambda ids: [reply("w9"), Done()]
    h.typed("w1 w2?", h.clock.mono + 1000)
    h.settle(3000)
    h.typed("w3 w4?", h.clock.mono + 1000)
    h.settle(3000)
    said = [o.text for o in h.mouth.orders]
    assert said[-2:] == ["w9", "w9"]                                           # both fresh questions answered
    window = " ".join(t.text for t in h.model.calls[-1].prompt.conversation)
    assert "w_para" not in window and "[he stopped our reply]" in window      # the fact, never his words


def test_a_no_reply_to_his_voice_is_final_and_says_whether_it_was_his(store):
    h = Harness(store, grace=False)
    rounds = iter([[Command("no_reply", {"reason": "w0", "not_his": True}), Done()], [reply("w9"), Done()]])
    h.model.default = lambda ids: next(rounds)
    h.utter([(["w1", "w2"], 0)])
    h.settle(3000)
    assert len(h.model.calls) == 1 and not h.mouth.orders                     # obeyed: never asked for a reply
    [cmd] = [p for k, lab, p in h.tel.events if k == "conv_run" and lab == "command"]
    assert cmd["command"] == "no_reply" and cmd["not_his"] is True


def test_not_his_after_a_read_stands_too(store):
    """The model read, then judged the words not his: its judgement stands — never pushed to say what it found."""
    from conversation.ports import ToolCall
    h = Harness(store, grace=False)
    rounds = iter([[ToolCall("c1", "search", {"q": "w1"}), Done()],
                   [Command("no_reply", {"reason": "w0", "not_his": True}), Done()], [reply("w9"), Done()]])
    h.model.default = lambda ids: next(rounds)
    h.utter([(["w1", "w2"], 0)])
    h.settle(3000)
    assert len(h.model.calls) == 2 and not h.mouth.orders and "no_reply_after_reads" not in _commands(h)


def test_his_voice_over_a_line_that_played_whole_is_no_barge_in(store):
    """His voice rose while our line sounded, and the line played to its end (with no echo cancellation his words
    alone cut, and these did not): no stop — and a no_reply to it stands."""
    h = Harness(store, grace=False)
    sid = _speaking(h)
    start = next(row for _k, row in h.store.view(h.conv.account).recent("says", 2))["t_ms"]
    h.model.default = lambda ids: [Command("no_reply", {"reason": "w0"}), Done()]
    h.conv.ack(SayEnded(sid, "played", 20, start + 600, "d1", "agent_estimate"))
    h.utter([(["w1", "w2"], 0)], at=start + 40)
    h.settle(3000)
    assert "no_reply_voice" not in _commands(h) and not h.mouth.orders[1:]
