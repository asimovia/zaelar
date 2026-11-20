"""Half a thought is not answered (node 13.35, v3.1 §1.6 ter).

The provider says whether it closed its transcript with a sentence end (`terminal`, from the language pack's marks —
the package only sees the boolean). After a close with NO mark he goes on most of the time: the batch is not eligible
for `nonterminal_start_ms` and not published before `nonterminal_grace_ms`; after a close with a mark (or unknown) the
run starts at once and does not publish before `terminal_grace_ms`. If his voice comes back within the grace on a
device that contributed to the batch, the batch waits for it and both travel in one prompt; with several voice
entries the latest grace rules; a text has none. A provider's eager hint decides nothing.

The publication hold looks at EVERY device that contributed an entry (P3 seed 60): he resumes on the device that is
not the last entry's, and nothing is said; a device that contributed nothing does not hold.

The model may say, with its order, whether the thought is answerable (`complete`, §1.6 quater): an answerable one is
published not before `complete_grace_ms` from the last voice close, one with something missing not before
`incomplete_grace_ms` — and a `no_reply` read as incomplete closes silent only then. No field, or one that is not a
boolean, leaves the marks' graces; on a text the field changes nothing.

A voice never stops anything by itself: what he says while a run is in course is an entry that substitutes it, and the
model decides. A voice that cut our line and ended with no word resumes that line once, from the last word heard —
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
    h = Harness(store, grace=False)
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
    h = Harness(store, grace=False)
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
REST = "w4. w5 w6."           # from the last whole word heard: one heard number for every reader


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
    assert [o.text for o in h.mouth.orders][-1] == REST and "voice" in h.mouth.orders[-1].channels
    h.at(5000).pump()
    assert len(h.mouth.orders) == 2                                        # once


def test_an_entry_with_words_first_and_no_resume(store):
    h = Harness(store)
    _cut_line(h, heard=9)
    h.mouth.ack = h.conv.ack                                               # his text is answered, and that line ends
    h.typed("w7", 750, ep="d2")
    h.hear(S.VadEdge("d1", "fall", 800), S.Tick(800 + h.conv.cfg.close_cap_ms))
    h.at(4000).pump()
    assert REST not in [o.text for o in h.mouth.orders]


def test_a_line_we_stopped_or_a_breath_too_late_is_not_resumed(store):
    h = Harness(store)
    _cut_line(h, heard=9)
    late = 720 + h.conv.cfg.resume_cut_within_ms                          # the breath ends past the window
    h.hear(S.VadEdge("d1", "fall", late - h.conv.cfg.close_cap_ms + 10), S.Tick(late + 20))
    h.at(late + 500).pump()
    assert REST not in [o.text for o in h.mouth.orders]


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
    assert REST not in [o.text for o in h.mouth.orders]


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
    assert REST not in [o.text for o in h.mouth.orders]


def test_an_entry_that_comes_before_the_resume_is_said_cancels_it(store):
    h = Harness(store)
    _cut_line(h, heard=9)
    h.mouth.ack = h.conv.ack
    h.live = False                                                          # the breath is noted, nothing runs yet
    h.hear(S.VadEdge("d1", "fall", 800), S.Tick(800 + h.conv.cfg.close_cap_ms))
    h.typed("w7", 3400, ep="d2")                                            # …and his text comes first
    h.at(4000).pump()
    h.at(5000).pump()
    assert REST not in [o.text for o in h.mouth.orders]


def _parked(h: Harness) -> bool:
    return h.conv.current is not None and h.conv.current.parked is not None


def test_a_stop_during_the_grace_cancels_the_reply_waiting_for_it(store):
    from conversation.types import ControlOp
    from tests.conversation.unit.inboxkit import control
    h = Harness(store)
    closed = h.utter([(["w1"], 0)], terminal=True)
    assert _parked(h)
    h.conv.give(control(ControlOp.STOP, closed + 1000, "k-stop", endpoint="d1"))
    _run_clock(h, closed + 8000)
    assert not h.mouth.orders and [(lab, p["reason"]) for lab, p in h.closes()] == [("silent", "stopped")]


def test_a_text_during_the_grace_supersedes_the_reply_waiting_for_it(store):
    h = Harness(store)
    closed = h.utter([(["w1"], 0)], terminal=True)
    assert _parked(h)
    h.typed("w2", closed + 1000)
    _run_clock(h, closed + 9000)
    assert len(h.mouth.orders) == 1                                       # one answer, to both
    assert "«w1»" in h.model.calls[-1].prompt.input and "«w2»" in h.model.calls[-1].prompt.input


def test_the_liveness_ends_a_reply_still_waiting_and_it_is_never_said(store):
    h = Harness(store, config=Config(terminal_grace_ms=8000, liveness_ms=5000))
    closed = h.utter([(["w1"], 0)], terminal=True)
    assert _parked(h)
    h.at(closed + 5500)
    h.conv.sweep()                                                         # the liveness sweep, on its own timer
    _run_clock(h, closed + 9000)
    assert [lab for lab, _ in h.closes()] == ["stalled"]
    assert all(o.notice_key for o in h.mouth.orders)                      # never the reply: only the line he is owed


def test_a_line_owed_waits_while_a_reply_waits_for_its_grace(store):
    h = Harness(store)
    closed = h.utter([(["w1"], 0)], terminal=True)
    h.owed.add("n1", "w5")
    _run_clock(h, closed + 2000)
    assert not h.mouth.orders                                             # neither the reply nor the line owed yet
    _run_clock(h, closed + 6000)
    assert [o.text for o in h.mouth.orders] == ["ok iv_000001", "w5"]


def test_a_noise_that_keeps_rising_resumes_the_line_once_and_never_its_resumption(store):
    """Review TC-2: a fan or an echo leak rises again and again with no word: the first wordless rise resumes the cut
    line; the resumption, cut in its turn, is never resumed — the rest is said once, not once per cycle."""
    h = Harness(store, grace=False)
    _cut_line(h, heard=9)
    t = 800
    for _ in range(5):
        h.hear(S.VadEdge("d1", "fall", t), S.Tick(t + h.conv.cfg.close_cap_ms))
        t += h.conv.cfg.close_cap_ms + 100
        h.at(t).pump()
        h.hear(S.VadEdge("d1", "rise", t + 50))
        h.conv.ack(SayEnded(h.mouth.orders[-1].say_id, "cut", 0, t + 60, "d1", "agent_estimate"))
        t += 100
    assert [o.text for o in h.mouth.orders].count(REST) == 1


# ── §1.6 quater: the model's own reading sets the grace ─────────────────────────────────────────────────────────

def _reads(h: Harness, **field) -> None:
    h.model.default = lambda ids: [reply("ok " + "+".join(ids), **field), Done()]


@pytest.mark.parametrize("terminal", [True, False])
def test_read_as_complete_it_goes_out_at_its_short_grace(store, terminal):
    h = Harness(store, grace=True)
    _reads(h, complete=True)
    closed = h.utter([(["w1"], 0)], terminal=terminal)
    _run_clock(h, closed + 9000)
    start = h.conv.cfg.nonterminal_start_ms if terminal is False else 0       # the mark still decides the start
    said = _say_times(h)
    assert len(said) == 1 and closed + h.conv.cfg.complete_grace_ms <= said[0] <= closed + max(
        h.conv.cfg.complete_grace_ms, start) + 100, said


def test_read_as_incomplete_with_nobody_going_on_it_goes_once_at_its_grace(store):
    h = Harness(store, grace=True)
    _reads(h, complete=False)
    closed = h.utter([(["w1"], 0)], terminal=True)
    _run_clock(h, closed + 12_000)
    said = _say_times(h)
    assert len(said) == 1 and abs(said[0] - (closed + h.conv.cfg.incomplete_grace_ms)) <= 100, said


def test_read_as_incomplete_and_back_at_four_seconds_nothing_is_said_and_both_travel(store):
    h = Harness(store, grace=True)
    _reads(h, complete=False)
    closed = h.utter([(["w1"], 0)], terminal=True)
    _run_clock(h, closed + 4000)
    assert not h.mouth.orders
    _reads(h, complete=True)
    h.utter([(["w2"], 0)], terminal=True, at=closed + 4000)
    _run_clock(h, h.clock.mono + 4000)
    assert len(h.mouth.orders) == 1
    assert "«w1»" in h.model.calls[-1].prompt.input and "«w2»" in h.model.calls[-1].prompt.input


@pytest.mark.parametrize("field", [{}, {"complete": "yes"}, {"complete": 1}, {"complete": None}])
def test_no_field_or_one_that_is_not_a_boolean_leaves_the_marks_graces(store, field):
    h = Harness(store, grace=True)
    _reads(h, **field)
    closed = h.utter([(["w1"], 0)], terminal=True)
    _run_clock(h, closed + 9000)
    said = _say_times(h)
    assert len(said) == 1 and abs(said[0] - (closed + h.conv.cfg.terminal_grace_ms)) <= 100, said


@pytest.mark.parametrize("complete", [True, False])
def test_on_a_text_the_field_changes_nothing(store, complete):
    h = Harness(store, grace=True)
    _reads(h, complete=complete)
    h.typed("w1", 100)
    _run_clock(h, 600)
    assert _say_times(h) and _say_times(h)[0] <= 100 + h.conv.cfg.collect_ms + 100


def _silent_closes(h: Harness) -> list[int]:
    return [p["t_ms"] for k, lab, p in h.tel.events if k == "conv_close" and lab == "silent"]


def _silent_incomplete(h: Harness) -> None:
    h.model.default = lambda ids: [Command("no_reply", {"reason": "w0", "complete": False}), Done()]


def test_no_reply_read_as_incomplete_closes_silent_at_its_grace(store):
    h = Harness(store, grace=True)
    _silent_incomplete(h)
    closed = h.utter([(["w1"], 0)], terminal=True)
    _run_clock(h, closed + 2000)
    assert not _silent_closes(h)                                          # not yet: he may go on
    _run_clock(h, closed + 9000)
    assert len(_silent_closes(h)) == 1 and abs(_silent_closes(h)[0] - (closed + h.conv.cfg.incomplete_grace_ms)) <= 100


def test_no_reply_read_as_incomplete_and_he_goes_on_closes_nothing_and_both_travel(store):
    h = Harness(store, grace=True)
    _silent_incomplete(h)
    closed = h.utter([(["w1"], 0)], terminal=True)
    _run_clock(h, closed + 3000)
    _reads(h, complete=True)
    h.utter([(["w2"], 0)], terminal=True, at=closed + 3000)
    _run_clock(h, h.clock.mono + 4000)
    assert not _silent_closes(h) and len(h.mouth.orders) == 1
    assert "«w1»" in h.model.calls[-1].prompt.input and "«w2»" in h.model.calls[-1].prompt.input


# ── the review of A9: a long thought, the silent close's look, the order of the graces ──────────────────────────────

def test_a_long_thought_in_pieces_is_answered_once_and_never_stalls(store):
    """Ten pieces with no mark, 4 s apart, read as incomplete: 40 s in all, past the liveness. The budget of a request
    counts from the close of the last piece of his that travels with it, so waiting for him is never stalling."""
    h = Harness(store, grace=True)
    _reads(h, complete=False)
    t = 10
    for i in range(10):
        t = h.utter([([f"w{i}a", f"w{i}b"], 0)], terminal=False, at=t) + 4000
        _run_clock(h, t)
    _run_clock(h, h.clock.mono + 12_000)
    labels = [lab for k, lab, p in h.tel.events if k == "conv_close"]
    assert labels == ["answered"] * 10 and len(h.mouth.orders) == 1
    assert all(f"«w{i}a w{i}b»" in h.model.calls[-1].prompt.input for i in range(10))


def test_when_he_stops_the_budget_runs_from_his_last_piece(store):
    """A budget shorter than the grace, to see it fire: it runs from his last piece, never from the first one's close."""
    h = Harness(store, config=Config(liveness_ms=5000), grace=True)
    _reads(h, complete=False)                                          # the reply waits 6 s: the budget comes first
    t = 10
    for i in range(3):
        t = h.utter([([f"w{i}"], 0)], terminal=False, at=t) + 3000
        _run_clock(h, t)
    last = t - 3000
    _run_clock(h, last + 9000)
    stalled = [p["t_ms"] for k, lab, p in h.tel.events if k == "conv_close" and lab == "stalled"]
    assert stalled and min(stalled) >= last + 5000 - 100, (stalled, last)
    assert all(o.notice_key for o in h.mouth.orders)                      # never the reply: only the line he is owed


@pytest.mark.parametrize("order", ["no_reply", "reply"])
def test_a_silent_close_waiting_for_its_grace_looks_for_his_voice_as_a_reply_does(store, order):
    """His voice opened in the ear with no onset reaching the manager, still open at the end of the grace: a silent
    close holds for it exactly as a reply holds right before sealing."""
    h = Harness(store, grace=True)
    cmd = (Command("no_reply", {"reason": "w0", "complete": False}) if order == "no_reply"
           else reply("w5", complete=False))
    h.model.default = lambda ids: [cmd, Done()]
    closed = h.utter([(["w1"], 0)], terminal=True)
    _run_clock(h, closed + 3000)
    t0 = h.clock.mono + 10
    h.conv.ear.feed(S.VadEdge("d1", "rise", t0))                      # straight into the ear: no onset
    for i in range(1, 8):
        t = t0 + 500 * i
        h.conv.ear.feed(S.WordSpan("d1", 50, i, False, h.words(["w2"] * i, t0), (t0, t)))
        _run_clock(h, t)
    assert not [lab for k, lab, p in h.tel.events if k == "conv_close"] and not h.mouth.orders
    assert any(k == "conv_run" and lab == "held" and p.get("waits_for") not in (None, "grace")
               for k, lab, p in h.tel.events)


def test_the_graces_bound_each_other_in_one_order():
    assert Config().misordered() == []
    assert Config(complete_grace_ms=4000).misordered() == ["complete_grace_ms > terminal_grace_ms"]
    assert Config(incomplete_grace_ms=9000).misordered() == ["incomplete_grace_ms > resume_hold_max_ms"]
    assert Config(terminal_grace_ms=5500).misordered() == ["terminal_grace_ms > nonterminal_grace_ms"]
