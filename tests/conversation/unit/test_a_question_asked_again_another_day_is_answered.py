"""A question asked again in another session is answered, and he always hears something (node 13.55, v3.1 B7c).

The tester's live passes: the model closed a question silently as «already answered» because the same question had
been asked in an EARLIER session of the account — a person asking again on another day would be ignored. The turns
before the last long silence reach the model marked as an earlier session, with their age; the prefix declares INPUT
as what is answered now, each entry on its own. And never silence: two rounds of text with no order, or a run that
reads to its cap, end in the language's own «I lost that» line, said once and counted.
"""
from __future__ import annotations

from conversation.ports import Done, TextDelta, ToolCall
from conversation.testing.scripted_model import reply
from tests.conversation.unit.convkit import Harness

HOUR = 3_600_000


class _Words:
    def line(self, key, near=""):
        return {"mute_lines": "w_lost", "unverified_fact": "w_unverified"}.get(key, "")


def _conversation(h) -> list[str]:
    return [t.text for t in h.model.calls[-1].prompt.conversation]


def test_the_same_question_in_a_later_session_is_answered_and_the_earlier_one_is_history(store):
    h = Harness(store, grace=False)
    h.typed("w1", 1000)
    h.at(2000).pump()
    h.typed("w1", 2 * HOUR)
    h.at(2 * HOUR + 1000).pump()
    assert len(h.mouth.orders) == 2                                        # both answered
    earlier = _conversation(h)
    assert earlier and all(t.startswith("[earlier session · ") and " ago] " in t for t in earlier), earlier
    assert "«w1»" in h.model.calls[-1].prompt.input                        # what is answered now


def test_within_one_session_nothing_is_marked(store):
    h = Harness(store, grace=False)
    h.typed("w1", 1000)
    h.at(2000).pump()
    h.typed("w2", 60_000)
    h.at(61_000).pump()
    assert _conversation(h) and not any("earlier session" in t for t in _conversation(h))


def test_two_rounds_of_text_with_no_order_end_in_the_lost_line_once(store):
    h = Harness(store, grace=False)
    h.conv.words = _Words()
    h.model.default = lambda ids: [TextDelta("w8"), Done()]
    h.utter([(["w1"], 0)])
    assert [o.text for o in h.mouth.orders] == ["w_lost"] and [lab for lab, _ in h.closes()] == ["answered"]
    assert [p.get("command") for k, lab, p in h.tel.events if k == "conv_run" and lab == "command"][-1] == "no_order"


def test_a_run_that_reads_to_its_cap_ends_in_the_lost_line(store):
    h = Harness(store, grace=False)
    h.conv.words = _Words()
    h.model.default = lambda ids: [ToolCall("c", "market_data", {"q": "w1"}), Done()]
    h.utter([(["w1"], 0)])
    assert [o.text for o in h.mouth.orders] == ["w_lost"]
    assert len(h.model.calls) == h.conv.cfg.max_steps
    assert any(p.get("command") == "max_steps" for k, lab, p in h.tel.events if k == "conv_run")


def test_the_prefix_declares_input_as_now_and_the_states_language_apart():
    from nucleo.conversation_host import prefix
    lines = dict(x.split(": ", 1) for x in prefix.build([], native="English", name="English").splitlines())
    assert lines["INPUT"].startswith("the entries to answer now, each on its own whatever CONVERSATION holds")
    assert "earlier session marked with its age" in lines["INPUT"]
    assert "another language than the conversation's" in lines["INPUT"]               # STATE's notes: not the reply's
    assert lines["LANGUAGE"].endswith("English (English)")
