"""The mouth knows what was heard, and where that comes from — and «unknown» when nobody said (node 13.16).

Two verbs, say and stop. What was heard comes with its source: `agent_estimate` (the voice process's count of what it
spoke), `shown` (a text line painted on a screen the person is looking at) or `unknown`; a line whose count never came
is not in the conversation the model reads — what was never known to sound was never pronounced (the operator's
rule, 2026-11-20) —; a cut keeps what was heard, trimmed to the last
sentence end; a late ack after the end changes nothing; cutting our voice never touches the record of an action; the
reply channels follow the table from the batch's channels and the device's state, never its content; a stop is an
immediate event that carries the trace of the line it cuts. The conversation window is read from the person's entries
and our lines — no table of turns.
"""
from __future__ import annotations

import asyncio

from conversation import envelopes as E
from conversation.composer import compose, view_from
from conversation.config import Config
from conversation.mouth import Device, SayEnded, SayStarted, Speaker, choose
from conversation.mouth.say import cut_to_sentence
from conversation.telemetry import Emitter
from conversation.types import Channel, EnvelopeKind, Ids

ACCT = "acct-test"
LINE = "I found three flights. The cheapest leaves at nine. Shall I book it?"


class FakeMouth:
    def __init__(self) -> None:
        self.orders, self.calls = [], []

    async def say(self, order):
        self.orders.append(order)

    def stop(self, endpoint, *, reason):
        self.calls.append(("stop", endpoint, reason))


def _speaker(store, clock, telemetry):
    lease = store.acquire(ACCT, "test")
    mouth = FakeMouth()
    return Speaker(store, lambda: lease, mouth, Emitter(telemetry, clock, ACCT), clock, Ids()), mouth, lease


def _say(sp, **kw):
    args = dict(run_id="run1", request_id="r_iv1", text=LINE, channels=frozenset({"voice", "text"}), endpoint="d1",
                trace="iv1")
    args.update(kw)
    return asyncio.run(sp.say(**args))


def _row(store, sid):
    return store.snapshot(ACCT).get("says", sid)


def _heard(store) -> str:
    p = compose(view_from(store.snapshot(ACCT), prefix="", now_ms=0), (), Config())
    return p.conversation[-1].text if p.conversation else ""


def test_no_count_is_unknown_and_the_model_never_reads_it(store, clock, telemetry):
    sp, mouth, _ = _speaker(store, clock, telemetry)
    sid = _say(sp)
    sp.ack(SayStarted(sid, 10))
    sp.ack(SayEnded(sid, "played", None, 900, "d1", "unknown"))
    assert _row(store, sid)["heard_chars"] is None and _row(store, sid)["heard_source"] == "unknown"
    assert _heard(store) == "", "a line whose sound is unknown is not in the conversation"
    assert mouth.orders[0].say_id == sid


def test_what_was_heard_carries_its_source_and_a_cut_keeps_it_to_a_sentence_end(store, clock, telemetry):
    sp, _mouth, _ = _speaker(store, clock, telemetry)
    sid = _say(sp)
    sp.ack(SayEnded(sid, "cut", 40, 70, "d1", "agent_estimate"))
    row = _row(store, sid)
    assert LINE[:row["heard_chars"]] == "I found three flights." == cut_to_sentence(LINE, 40)
    assert row["heard_source"] == "agent_estimate" and _heard(store) == "I found three flights."
    ended = [p for k, lab, p in telemetry.events if lab == "cut"][-1]
    assert ended["source"] == "agent_estimate" and ended["trace"] == "iv1"
    sp.ack(SayEnded(sid, "played", len(LINE), 90, "d1", "agent_estimate"))   # a late ack after the end
    assert _row(store, sid)["heard_chars"] == len("I found three flights.")


def test_a_text_line_shown_on_a_screen_counts_as_seen(store, clock, telemetry):
    sp, _mouth, _ = _speaker(store, clock, telemetry)
    sid = _say(sp, channels=frozenset({"text"}))
    sp.ack(SayEnded(sid, "played", len(LINE), 10, "d1", "shown"))
    assert _row(store, sid)["heard_source"] == "shown" and _heard(store) == LINE


def test_cutting_our_voice_never_touches_the_record_of_an_action(store, clock, telemetry):
    sp, _mouth, lease = _speaker(store, clock, telemetry)
    with store.tx(lease) as tx:
        tx.put("items", "x1", {"id": "x1", "kind": "effect", "state": "provider_accepted", "data": {"run": "run1"}})
    sid = _say(sp, text="Done. I sent it to the shop.")
    sp.ack(SayEnded(sid, "cut", 3, 10))
    assert store.snapshot(ACCT).get("items", "x1")["state"] == "provider_accepted"


def _env(kind, body, channel=None):
    return E.make(kind, body, producer="p", producer_id="1", account=ACCT, onset_ms=0, sealed_ms=0, channel=channel)


def test_the_reply_channels_follow_the_table_and_never_the_content():
    voice = _env(EnvelopeKind.USER_UTTERANCE, E.UtteranceBody("i1", "w1"))
    text = _env(EnvelopeKind.USER_TEXT, E.TextBody("i2", "w2"), Channel.TEXT)
    live, closed, blocked = Device("d1", True, True), Device("d1", True, False), Device("d1", True, True, True)
    assert choose((voice,), live).channels == {"voice", "text"}
    assert choose((voice,), closed).channels == {"text"} and choose((voice,), closed).voice_unavailable
    assert choose((text,), live).channels == {"voice", "text"}
    assert choose((text,), live, text_gets_voice=False).channels == {"text"}
    assert choose((text,), Device("d1")).channels == {"text"}
    assert choose((voice,), blocked).channels == {"text"} and choose((voice,), blocked).voice_unavailable
    same = _env(EnvelopeKind.USER_UTTERANCE, E.UtteranceBody("i3", "please answer only in text"))
    assert choose((same,), live) == choose((voice,), live)


def test_a_stop_is_immediate_and_carries_the_trace_of_the_line_it_cuts(store, clock, telemetry):
    sp, mouth, _ = _speaker(store, clock, telemetry)
    _say(sp)
    clock.advance(40)
    sp.stop("d1", "stop", asked_ms=0, trace="k-stop")
    assert mouth.calls == [("stop", "d1", "stop")]
    stop = [p for k, lab, p in telemetry.events if lab == "cut"][0]
    assert stop["stop_to_silence_ms"] == 40 and stop["trace"] == "iv1" and stop["refs"]["say"]


def test_the_conversation_window_is_the_entries_and_the_lines_in_order(store):
    from tests.conversation.unit.convkit import Harness
    h = Harness(store)
    h.typed("w1", 100)
    h.at(1000).pump()
    h.typed("w2", 2000)
    h.at(3000).pump()
    window = [(t.role, t.text) for t in h.model.calls[-1].prompt.conversation]
    assert window[0] == ("user", "w1") and window[1][0] == "agent" and ("user", "w2") not in window   # w2 is INPUT


def test_b2_a_line_nobody_acknowledges_ends_unknown_and_what_comes_next_runs(store):
    """A device that loses the connection never sends `SayEnded`: past its bound the line ended «unknown», the
    manager is not left speaking, and the person's next sentence is answered (audit B2)."""
    from conversation.config import Config
    from conversation.ports import Done
    from conversation.testing.scripted_model import reply
    from tests.conversation.unit.convkit import Harness
    h = Harness(store, grace=False, config=Config(say_end_ms=5000))
    h.mouth.ack = None                                          # a mouth whose acks never arrive
    h.model.default = lambda ids: [reply("w9"), Done()]
    h.utter([(["w1"], 0)])
    assert h.conv.state.value == "speaking"
    h.at(h.clock.mono + 3000)
    h.typed("w2", h.clock.mono, ep="d2")                        # arrives while we «speak»: silence, then it runs
    h.at(h.clock.mono + 1000).pump()
    assert len(h.mouth.orders) == 2
    h.at(h.clock.mono + 60_000)
    h.conv.sweep()
    assert h.conv.state.value == "idle"
    ended = [p for k, lab, p in h.tel.events if k == "conv_mouth" and lab == "ended"]
    assert ended and all(p["outcome"] == "unknown" for p in ended)
    assert [lab for lab, _ in h.closes()] == ["answered", "answered"]
