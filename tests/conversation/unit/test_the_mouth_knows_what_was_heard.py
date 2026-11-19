"""The mouth knows what was heard — per device, and «unknown» when nobody said (node 13.16, B4).

Acks are per device; a line with no ack is «heard: unknown» in the conversation the model reads, never «heard»; a cut
keeps what was heard, trimmed to the last sentence end; cutting our voice never touches the record of an action; a
question counts as presented only once played, or painted on a device's text channel; the reply channels follow the
§7.1 table from the batch's channels and the device's state, never its content; duck and stop are immediate events.
"""
from __future__ import annotations

import asyncio

from conversation import envelopes as E
from conversation.composer import compose, view_from
from conversation.config import Config
from conversation.mouth import Device, Painted, PlayoutAck, SayEnded, SayStarted, Speaker, choose
from conversation.mouth.say import cut_to_sentence
from conversation.telemetry import Emitter
from conversation.types import Channel, EnvelopeKind, Ids, WorkerUpdate

ACCT = "acct-test"
LINE = "I found three flights. The cheapest leaves at nine. Shall I book it?"


class FakeMouth:
    def __init__(self) -> None:
        self.orders, self.calls = [], []

    async def say(self, order):
        self.orders.append(order)

    def duck(self, endpoint):
        self.calls.append(("duck", endpoint))

    def unduck(self, endpoint):
        self.calls.append(("unduck", endpoint))

    def stop(self, endpoint, *, reason):
        self.calls.append(("stop", endpoint, reason))


def _speaker(store, clock, telemetry, presented=None):
    lease = store.acquire(ACCT, "test")
    mouth = FakeMouth()
    sp = Speaker(store, lambda: lease, mouth, Emitter(telemetry, clock, ACCT), clock, Ids(),
                 on_presented=(lambda h, ep: presented.append((h, ep))) if presented is not None else None)
    return sp, mouth, lease


def _say(sp, **kw):
    args = dict(run_id="run1", request_id="r1", text=LINE, channels=frozenset({"voice", "text"}), endpoint="d1")
    args.update(kw)
    return asyncio.run(sp.say(**args))


def _turn(store):
    return [t for _k, t in store.snapshot(ACCT).scan("turns")][-1]


def test_no_ack_is_unknown_and_the_model_reads_it_so(store, clock, telemetry):
    sp, mouth, _ = _speaker(store, clock, telemetry)
    sid = _say(sp)
    sp.ack(SayStarted(sid, 10))
    sp.ack(SayEnded(sid, "played", None, 900))
    assert _turn(store)["heard_chars"] is None
    p = compose(view_from(store.snapshot(ACCT), prefix="", now_ms=0), (), Config())
    assert p.conversation[-1].text.endswith("[heard: unknown]")
    assert mouth.orders[0].say_id == sid


def test_acks_are_per_device_and_a_cut_keeps_what_was_heard_to_a_sentence_end(store, clock, telemetry):
    sp, _mouth, _ = _speaker(store, clock, telemetry)
    sid = _say(sp)
    sp.ack(PlayoutAck(sid, "d2", 70, 50))                                   # another device heard it all
    sp.ack(PlayoutAck(sid, "d1", 40, 60))                                   # this one, 40 characters
    sp.ack(SayEnded(sid, "cut", None, 70, endpoint="d1"))
    kept = LINE[:_turn(store)["heard_chars"]]
    assert kept == "I found three flights." == cut_to_sentence(LINE, 40)
    assert "conv_mouth/cut" in telemetry.labels()


def test_cutting_our_voice_never_touches_the_record_of_an_action(store, clock, telemetry):
    sp, _mouth, lease = _speaker(store, clock, telemetry)
    with store.tx(lease) as tx:
        tx.put("items", "x1", {"id": "x1", "kind": "effect", "state": "provider_accepted", "data": {"run": "run1"}})
    sid = _say(sp, text="Done. I sent it to the shop.")
    sp.ack(SayEnded(sid, "cut", 3, 10))
    assert store.snapshot(ACCT).get("items", "x1")["state"] == "provider_accepted"


def test_a_question_is_presented_only_once_played_or_painted(store, clock, telemetry):
    seen: list = []
    sp, _mouth, _ = _speaker(store, clock, telemetry, presented=seen)
    a = _say(sp, presents="h1", channels=frozenset({"voice"}))
    sp.ack(SayEnded(a, "cut", 10, 5))
    assert seen == []                                                       # cut before the question: not presented
    b = _say(sp, presents="h2")
    sp.ack(Painted(b, "d1", 6))
    sp.ack(SayEnded(b, "played", None, 9))
    c = _say(sp, presents="h3", channels=frozenset({"voice"}))
    sp.ack(SayEnded(c, "played", None, 12))
    assert seen == [("h2", "d1"), ("h3", "d1")]                             # painted; played — once each


def _env(kind, body, channel=None):
    return E.make(kind, body, producer="p", producer_id="1", account=ACCT, onset_ms=0, sealed_ms=0, channel=channel)


def test_the_reply_channels_follow_the_table_and_never_the_content():
    voice = _env(EnvelopeKind.USER_UTTERANCE, E.UtteranceBody("i1", "w1"))
    text = _env(EnvelopeKind.USER_TEXT, E.TextBody("i2", "w2"), Channel.TEXT)
    result = _env(EnvelopeKind.WORKER_UPDATE, E.WorkerBody("t1", WorkerUpdate.RESULT, "w3"))
    live, closed, blocked = Device("d1", True, True), Device("d1", True, False), Device("d1", True, True, True)
    assert choose((voice,), live).channels == {"voice", "text"}
    assert choose((voice,), closed).channels == {"text"} and choose((voice,), closed).voice_unavailable
    assert choose((text,), live).channels == {"voice", "text"}
    assert choose((text,), live, text_gets_voice=False).channels == {"text"}
    assert choose((text,), Device("d1")).channels == {"text"}
    assert choose((result,), blocked).channels == {"text"} and choose((result,), live).channels == {"voice", "text"}
    same = _env(EnvelopeKind.USER_UTTERANCE, E.UtteranceBody("i3", "please answer only in text"))
    assert choose((same,), live) == choose((voice,), live)


def test_duck_and_stop_are_immediate_events_on_the_control_lane(store, clock, telemetry):
    sp, mouth, _ = _speaker(store, clock, telemetry)
    sp.duck("d1")
    sp.unduck("d1")
    clock.advance(40)
    sp.stop("d1", "stop", asked_ms=0)
    assert mouth.calls == [("duck", "d1"), ("unduck", "d1"), ("stop", "d1", "stop")]
    stop = [p for k, lab, p in telemetry.events if lab == "cut"][0]
    assert stop["stop_to_silence_ms"] == 40


def test_b2_a_line_nobody_acknowledges_ends_unknown_and_what_comes_next_runs(store):
    """A device that loses the connection never sends `SayEnded`: past its bound the line ended «unknown», the
    manager is not left speaking, and the person's next sentence is answered (audit B2)."""
    from conversation.config import Config
    from conversation.ports import Done
    from conversation.testing.scripted_model import reply
    from tests.conversation.unit.convkit import Harness
    h = Harness(store, config=Config(say_end_ms=5000))
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
