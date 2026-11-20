"""The enrolled voice and the window stand in the manager as in the old turn (node 13.115, V2-941, plan v3.2 C8–C10).

  · C8 — with «stick to my voice» on and a voice enrolled, a turn every verdict of which said ANOTHER voice is a
    discard `voice_lock` at the ear's guards; any verdict of his, no verdict, or the switch off lets it pass; the
    verdicts are consumed by the turn that read them;
  · C9 — a run over his VOICE that the model closes with no reply gives back the window its entry renewed; a typed
    one, one cut by his barge-in, or our own failure (an empty reply) does not;
  · C10 — a cold turn let in says why the conversation began (`attention_opening`); one inside the window does not.

Disarms seen red: the voice-lock guard removed; the window not given back; the opening not noted.
"""
from __future__ import annotations

import pytest

from conversation.ports import Command, Done
from nucleo.conversation_host import guards
from tests.conversation.unit.convkit import Harness
from voice import attention, attention_opening, mic_input, voice_lock


@pytest.fixture
def judged(monkeypatch):
    state = {"reason": "active_window"}
    monkeypatch.setattr(mic_input, "blocks_turn", lambda text: False)
    monkeypatch.setattr(attention, "evaluate", lambda text, now=None: attention.Verdict(True, state["reason"]))
    monkeypatch.setattr(attention, "note_directed", lambda now=None: None)
    guards._lines.clear()
    voice_lock.set_state(False, False)
    attention_opening.reset()
    yield state
    voice_lock.set_state(False, False)
    attention_opening.reset()


def test_another_voice_is_a_discard_when_his_voice_is_enrolled(judged):
    voice_lock.set_state(True, True)
    voice_lock.note_verdict("other", now=1000.0)
    assert guards.judge("w1 w2", now=1001.0, rose=1000.2) == "voice_lock"
    voice_lock.note_verdict("other", now=1010.0)
    voice_lock.note_verdict("operator", now=1010.5)
    assert guards.judge("w1 w2", now=1011.0, rose=1010.1) is None                   # a verdict of his: it passes
    assert guards.judge("w3", now=1020.0, rose=1019.5) is None                      # no verdict: it passes
    voice_lock.set_state(False, True)
    voice_lock.note_verdict("other", now=1030.0)
    assert guards.judge("w4", now=1031.0, rose=1030.1) is None                      # the switch off: it passes


def test_a_cold_turn_let_in_says_why_the_conversation_began(judged):
    assert guards.judge("w1", now=1000.0) is None and attention_opening._state["opened_by"] is None
    judged["reason"] = "wakeword"
    assert guards.judge("w2 w3", now=1001.0) is None
    assert attention_opening._state["opened_by"]["why"] == "wakeword"


@pytest.mark.parametrize("payload, gives_back", [
    ({"outcome": "no_reply", "reason": "w0"}, True),
    ({"outcome": "no_reply", "reason": "w0", "typed_only": True}, False),
    ({"outcome": "no_reply", "reason": "w0", "barge_cut": True}, False),
    ({"outcome": "no_reply", "reason": "empty_reply"}, False),
    ({"outcome": "replied"}, False)])
def test_a_no_reply_over_his_voice_gives_the_window_back(monkeypatch, payload, gives_back):
    calls = []
    monkeypatch.setattr(attention, "retract_last_directed", lambda: calls.append(1) or True)
    guards.listen("conv_run", "ended", payload)
    assert bool(calls) is gives_back


def test_the_runs_end_says_what_the_window_reads(store, monkeypatch):
    """The real manager's `ended` over a voice entry the model would not answer carries what `listen` reads."""
    calls = []
    monkeypatch.setattr(attention, "retract_last_directed", lambda: calls.append(1) or True)
    h = Harness(store, grace=False)
    port = h.tel.emit
    h.tel.emit = lambda k, lab, p: (port(k, lab, p), guards.listen(k, lab, p))
    h.model.default = lambda ids: [Command("no_reply", {"reason": "w0"}), Done()]
    h.utter([(["w1", "w2"], 0)])
    h.settle(9000)
    ended = [p for k, lab, p in h.tel.events if k == "conv_run" and lab == "ended" and p.get("outcome") == "no_reply"]
    assert ended and ended[-1]["typed_only"] is False and ended[-1]["barge_cut"] is False
    assert calls == [1] and h.mouth.orders == []


def test_the_bodys_conversation_is_opened_with_the_window_listener(monkeypatch):
    from nucleo.conversation_host import boot, entry, sessions
    monkeypatch.setattr(sessions, "get", lambda acct: None)
    monkeypatch.setattr(sessions, "open_", lambda acct, owner, make: make)
    monkeypatch.setattr(boot, "make", lambda listeners, said=None: listeners)
    assert guards.listen in entry.runtime()


def test_a_no_reply_after_his_voice_cut_us_keeps_the_window(store, monkeypatch):
    """The review's C9 minor: through the real manager, his voice rises over our line, our line ends cut, the model
    says nothing — a barge-in, so the window he kept open by speaking is not given back."""
    from conversation.ear import signals as S
    from conversation.mouth import SayEnded
    from tests.conversation.unit.test_a_wordless_barge_in_gives_the_line_back import _speaking
    calls = []
    monkeypatch.setattr(attention, "retract_last_directed", lambda: calls.append(1) or True)
    h = Harness(store, grace=False)
    port = h.tel.emit
    h.tel.emit = lambda k, lab, p: (port(k, lab, p), guards.listen(k, lab, p))
    sid = _speaking(h)
    start = next(row for _k, row in h.store.view(h.conv.account).recent("says", 2))["t_ms"]
    h.model.default = lambda ids: [Command("no_reply", {"reason": "w0"}), Done()]
    h.hear(S.VadEdge("d1", "rise", start + 50))
    h.conv.ack(SayEnded(sid, "cut", 4, start + 600, "d1", "agent_estimate"))
    h.utter([(["w1", "w2"], 0)], at=start + 40)
    h.settle(3000)
    ended = [p for k, lab, p in h.tel.events if k == "conv_run" and lab == "ended" and p.get("outcome") == "no_reply"]
    assert ended and ended[-1]["barge_cut"] is True and calls == []


# ── E6: a voice the enrolled voice's verdicts judged another person's holds nothing ─────────────────────────────────

@pytest.mark.parametrize("case, foreign", [
    ("another voice on the holder", True),
    ("one verdict his among them", False),
    ("no verdict yet", False),
    ("a verdict from before that voice rose", False),
    ("another device", False),
    ("switch off", False),
    ("no voice enrolled", False),
    ("onset unknown", False),
])
def test_only_another_voice_judged_on_the_holder_since_it_rose_holds_nothing(judged, case, foreign):
    """E6 (`guards.foreign_voice`, `voice_lock.judged_other`): an open voice holds our line unless the switch is on, a
    voice is enrolled, the device is the holder whose browser sends the verdicts, and at least one verdict since that
    voice rose says another voice with none of his. Nothing is read twice wrong: the verdicts stay for the close."""
    import time

    from nucleo.conversation_host import voice_session
    now = time.time()
    onset = int((now - 2) * 1000)
    voice_lock.set_state(case != "switch off", case != "no voice enrolled")
    if case == "a verdict from before that voice rose":
        voice_lock.note_verdict("other", now=now - 5)
    elif case != "no verdict yet":
        voice_lock.note_verdict("other", now=now - 1)
    if case == "one verdict his among them":
        voice_lock.note_verdict("operator", now=now - 0.5)
    ep = "d2" if case == "another device" else voice_session.ENDPOINT
    at = 0 if case == "onset unknown" else onset
    assert guards.foreign_voice(ep, at) is foreign
    assert guards.foreign_voice(ep, at) is foreign                       # read, never consumed


def test_reading_the_verdicts_for_our_line_leaves_them_to_the_close(judged):
    """The close of that voice is still judged by its own verdicts: asking whether it holds our line consumed nothing."""
    import time

    from nucleo.conversation_host import voice_session
    now = time.time()
    voice_lock.set_state(True, True)
    voice_lock.note_verdict("other", now=now - 1)
    assert guards.foreign_voice(voice_session.ENDPOINT, int((now - 2) * 1000))
    assert voice_lock.admit_now(onset=now - 2, now=now) == (False, "other_voice")
