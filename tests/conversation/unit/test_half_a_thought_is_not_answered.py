"""Half a thought is not answered (node 13.35, v3.1 §1.6 ter).

The provider says whether it closed its transcript with a sentence end (`terminal`, from the language pack's marks —
the package only sees the boolean). After a close with NO mark he goes on most of the time: the batch is not eligible
for `nonterminal_start_ms` and not published before `nonterminal_grace_ms`; after a close with a mark (or unknown) the
run starts at once and does not publish before `terminal_grace_ms`. If his voice comes back within the grace on a
device that contributed to the batch, the batch waits for it and both travel in one prompt; with several voice
entries the latest grace rules; a text has none. A provider's eager hint decides nothing.

The publication hold looks at EVERY device that contributed an entry (P3 seed 60): he resumes on the device that is
not the last entry's, and nothing is said; a device that contributed nothing does not hold.

A voice never stops anything by itself: what he says while a run is in course is an entry that substitutes it, and the
model decides. A voice that cut our line and ended with no word resumes that line once, from the last sentence heard —
unless an entry with words came first, or the line was stopped by us.
"""
from __future__ import annotations

import pytest

from conversation.config import Config
from conversation.ear import signals as S
from conversation.mouth import SayEnded
from conversation.ports import Command, Done
from conversation.testing.scripted_model import reply
from tests.conversation.unit.convkit import Harness


def _run_clock(h: Harness, until: int, step: int = 100) -> None:
    """Time passes on the live timer: a pump every `step`."""
    t = h.clock.mono
    while t < until:
        t = min(until, t + step)
        h.at(t).pump()


def _say_times(h: Harness) -> list[int]:
    return [p["t_ms"] for k, lab, p in h.tel.events if k == "conv_mouth" and lab == "say"]


def _started(h: Harness) -> list[int]:
    return [p["t_ms"] for k, lab, p in h.tel.events if k == "conv_run" and lab == "started"]


@pytest.mark.parametrize("back_ms", [500, 1700, 3400])
def test_after_a_close_with_no_mark_he_goes_on_and_nothing_is_said(store, back_ms):
    h = Harness(store, grace=True)
    closed = h.utter([(["w1", "w2"], 0)], terminal=False)
    _run_clock(h, closed + back_ms)
    if back_ms < h.conv.cfg.nonterminal_start_ms:
        assert not _started(h), "a run started inside the no-mark wait"
    h.utter([(["w3", "w4"], 0)], terminal=True, at=closed + back_ms)
    _run_clock(h, h.clock.mono + 4000)
    assert len(h.mouth.orders) == 1
    said = h.model.calls[-1].prompt.input
    assert "«w1 w2»" in said and "«w3 w4»" in said
    assert _say_times(h)[0] >= closed + back_ms


def test_after_a_close_with_no_mark_and_back_at_six_seconds_the_answer_went_at_five(store):
    h = Harness(store, grace=True)
    closed = h.utter([(["w1"], 0)], terminal=False)
    _run_clock(h, closed + 6000)
    assert _say_times(h) and abs(_say_times(h)[0] - (closed + h.conv.cfg.nonterminal_grace_ms)) <= 100
    h.utter([(["w2"], 0)], terminal=True, at=closed + 6000)
    _run_clock(h, h.clock.mono + 4000)
    assert len(h.mouth.orders) == 2 and "«w2»" in h.model.calls[-1].prompt.input


@pytest.mark.parametrize("terminal,grace", [(False, "nonterminal_grace_ms"), (True, "terminal_grace_ms"),
                                            (None, "terminal_grace_ms")])
def test_with_nobody_going_on_the_answer_goes_at_its_grace_once(store, terminal, grace):
    h = Harness(store, grace=True)
    closed = h.utter([(["w1"], 0)], terminal=terminal)
    _run_clock(h, closed + 9000)
    said = _say_times(h)
    assert len(said) == 1 and abs(said[0] - (closed + getattr(h.conv.cfg, grace))) <= 100


def test_with_a_zero_grace_the_answer_goes_at_once(store):
    h = Harness(store, config=Config(terminal_grace_ms=0), grace=True)
    closed = h.utter([(["w1"], 0)], terminal=True)
    assert _say_times(h) and _say_times(h)[0] - closed <= 50


def test_after_a_close_with_a_mark_and_back_at_two_and_a_half_seconds_nothing_is_said(store):
    h = Harness(store, grace=True)
    closed = h.utter([(["w1"], 0)], terminal=True)
    assert _started(h) and _started(h)[0] - closed <= 50                # it starts at once
    _run_clock(h, closed + 2500)
    h.utter([(["w2"], 0)], terminal=True, at=closed + 2500)
    _run_clock(h, h.clock.mono + 4000)
    assert len(h.mouth.orders) == 1 and "«w1»" in h.model.calls[-1].prompt.input
    assert "«w2»" in h.model.calls[-1].prompt.input


def test_an_eager_hint_decides_nothing(store):
    h = Harness(store, grace=True)
    t = 10
    h.hear(S.VadEdge("d1", "rise", t))
    ws = h.words(["w1", "w2"], t)
    h.hear(S.WordSpan("d1", 1, 1, False, ws, (t, ws[-1][2])), h.beats(ws[-1][2], ws[-1][2] + 200),
           S.EotHint("d1", "flux", "eager", .6, ws[-1][2] + 200))
    _run_clock(h, ws[-1][2] + 900)
    assert not h.model.calls and not h.mouth.orders and h.conv.ear.open_ids()


def test_a_text_has_no_grace(store):
    h = Harness(store, grace=True)
    h.typed("w1", 100)
    _run_clock(h, 600)
    assert _say_times(h) and _say_times(h)[0] <= 100 + h.conv.cfg.collect_ms + 100


def test_a_monologue_of_pieces_with_no_mark_is_answered_once_after_its_last_piece(store):
    h = Harness(store, grace=True)
    t = 0
    for i in range(12):
        t = h.utter([([f"w{i}"], 0)], terminal=i == 11, at=t + 900)
        _run_clock(h, t + 900)
    _run_clock(h, t + 6000)
    assert len(h.mouth.orders) == 1 and _say_times(h)[0] >= t
    assert all(f"«w{i}»" in h.model.calls[-1].prompt.input for i in range(12))


def test_he_goes_on_on_the_other_device_that_contributed_and_nothing_is_said(store):
    """P3 seed 60 as a fixed case: two voices close at the same instant on two devices; he goes on on the one that is
    not the batch's «last» entry — the hold looks at every device that contributed, so nothing is said and the next
    batch carries the three entries. Its mirror: a device that contributed nothing does not hold."""
    h = Harness(store)
    h.conv.device("d2", voice_live=True, speaker_open=True)
    h.live = False
    h.utter([(["w1"], 0)], ep="d1", at=0)
    h.utter([(["w2"], 0)], ep="d2", at=0)
    once: list = []

    def he_goes_on_on_d1():                                  # d2 is the «last» entry (the tie goes to it)
        if not once:
            once.append(1)
            h.utter([(["w3"], 0)], ep="d1", at=h.clock.mono + 10)

    h.model.script["iv_000001"] = [[he_goes_on_on_d1, reply("w9"), Done()]]
    h.pump()
    assert len(h.mouth.orders) == 1 and "conv_run/held" in h.tel.labels()
    assert all(f"«{w}»" in h.model.calls[-1].prompt.input for w in ("w1", "w2", "w3"))


def test_a_device_that_contributed_nothing_does_not_hold(store):
    h = Harness(store)
    h.conv.device("d3", voice_live=True, speaker_open=True)
    once: list = []

    def elsewhere():
        if once:
            return
        once.append(1)
        h.hear(S.VadEdge("d3", "rise", h.clock.mono + 10))

    h.model.script["iv_000001"] = [[elsewhere, reply("w9"), Done()]]
    h.utter([(["w1"], 0)], ep="d1")
    assert [o.text for o in h.mouth.orders] == ["w9"] and "conv_run/held" not in h.tel.labels()


def test_a_voice_never_stops_anything_by_itself_the_model_decides(store):
    """His words during a run are an entry that substitutes it — no control, no cancel; if the model reads them as a
    stop, it answers nothing, and the request ends silent with its reason."""
    h = Harness(store)
    went: list = []

    def he_speaks():
        if went:
            return
        went.append(1)
        h.utter([(["w8"], 0)], at=h.clock.mono + 10)

    h.model.default = lambda ids: ([he_speaks, reply("w9"), Done()] if len(ids) == 1     # the model reads his words:
                                   else [Command("no_reply", {"reason": "w_stop"}), Done()])   # «stop», it says nothing
    h.utter([(["w1"], 0)])
    assert not h.mouth.orders and not h.mouth.calls                       # no stop order reached our mouth
    assert not [lab for k, lab, p in h.tel.events if k == "conv_inbox" and p.get("kind") == "user.control"]
    assert [lab for lab, _ in h.closes()] == ["silent", "silent"]


LINE = "w1 w2. w3 w4. w5 w6."


def _cut_line(h: Harness, heard: int) -> str:
    h.mouth.ack = None
    h.model.default = lambda ids: [reply(LINE), Done()]
    h.typed("w0", 100, ep="d1")
    h.at(600).pump()
    sid = h.mouth.orders[-1].say_id
    h.hear(S.VadEdge("d1", "rise", 700))                                 # his voice cuts our line
    h.conv.ack(SayEnded(sid, "cut", heard, 720, "d1", "agent_estimate"))
    return sid


def test_a_barge_in_with_no_word_resumes_the_cut_line_once_from_the_last_sentence_heard(store):
    h = Harness(store)
    _cut_line(h, heard=9)                                                  # «w1 w2. w3» heard: back to «w1 w2.»
    h.hear(S.VadEdge("d1", "fall", 800), S.Tick(800 + h.conv.cfg.close_cap_ms))   # a breath: no word, discarded
    h.at(3400).pump()
    assert [o.text for o in h.mouth.orders][-1] == "w3 w4. w5 w6." and "voice" in h.mouth.orders[-1].channels
    h.at(5000).pump()
    assert len(h.mouth.orders) == 2                                        # once


def test_an_entry_with_words_first_and_no_resume(store):
    h = Harness(store)
    _cut_line(h, heard=9)
    h.mouth.ack = h.conv.ack                                               # his text is answered, and that line ends
    h.typed("w7", 750, ep="d2")
    h.hear(S.VadEdge("d1", "fall", 800), S.Tick(800 + h.conv.cfg.close_cap_ms))
    h.at(4000).pump()
    assert "w3 w4. w5 w6." not in [o.text for o in h.mouth.orders]


def test_a_line_we_stopped_or_a_breath_too_late_is_not_resumed(store):
    h = Harness(store)
    _cut_line(h, heard=9)
    late = 720 + h.conv.cfg.resume_cut_within_ms                          # the breath ends past the window
    h.hear(S.VadEdge("d1", "fall", late - h.conv.cfg.close_cap_ms + 10), S.Tick(late + 20))
    h.at(late + 500).pump()
    assert "w3 w4. w5 w6." not in [o.text for o in h.mouth.orders]


def test_a_line_we_stopped_is_never_resumed(store):
    from conversation.types import ControlOp
    from tests.conversation.unit.inboxkit import control
    h = Harness(store)
    h.mouth.ack = None
    h.model.default = lambda ids: [reply(LINE), Done()]
    h.typed("w0", 100, ep="d1")
    h.at(600).pump()
    sid = h.mouth.orders[-1].say_id
    h.hear(S.VadEdge("d1", "rise", 700))
    h.conv.give(control(ControlOp.STOP, 705, "k-stop", endpoint="d1"))   # the button: our stop, not his voice
    h.conv.ack(SayEnded(sid, "cut", 9, 720, "d1", "agent_estimate"))
    h.hear(S.VadEdge("d1", "fall", 800), S.Tick(800 + h.conv.cfg.close_cap_ms))
    h.at(4000).pump()
    assert "w3 w4. w5 w6." not in [o.text for o in h.mouth.orders]


def test_with_two_voice_entries_the_latest_grace_rules(store):
    """A piece with no mark (5 s) then one with a mark half a second later (3 s): the batch publishes at the later of
    the two — the first one's 5 s — never at the second's 3 s."""
    h = Harness(store, grace=True)
    first = h.utter([(["w1"], 0)], terminal=False)
    h.utter([(["w2"], 0)], terminal=True, at=first + 500)
    _run_clock(h, first + 9000)
    said = _say_times(h)
    assert len(said) == 1 and said[0] >= first + h.conv.cfg.nonterminal_grace_ms
    assert "«w1»" in h.model.calls[-1].prompt.input and "«w2»" in h.model.calls[-1].prompt.input


def test_an_entry_answered_since_the_cut_and_no_resume(store):
    """His words on another device after the cut were answered: the old line does not come back after that."""
    h = Harness(store)
    h.conv.device("d2", voice_live=True, speaker_open=True)
    _cut_line(h, heard=9)
    h.mouth.ack = h.conv.ack
    h.utter([(["w7"], 0)], ep="d2", at=900)
    h.hear(S.VadEdge("d1", "fall", 800), S.Tick(800 + h.conv.cfg.close_cap_ms))
    h.at(4000).pump()
    assert "w3 w4. w5 w6." not in [o.text for o in h.mouth.orders]


def test_an_entry_that_comes_before_the_resume_is_said_cancels_it(store):
    h = Harness(store)
    _cut_line(h, heard=9)
    h.mouth.ack = h.conv.ack
    h.live = False                                                          # the breath is noted, nothing runs yet
    h.hear(S.VadEdge("d1", "fall", 800), S.Tick(800 + h.conv.cfg.close_cap_ms))
    h.typed("w7", 3400, ep="d2")                                            # …and his text comes first
    h.at(4000).pump()
    h.at(5000).pump()
    assert "w3 w4. w5 w6." not in [o.text for o in h.mouth.orders]
