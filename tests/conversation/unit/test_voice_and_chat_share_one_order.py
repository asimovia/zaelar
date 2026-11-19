"""Voice and chat are two channels of ONE inbox with ONE order — by onset (node 13.7, §7.1).

The cross-channel cases X1–X10 at the inbox, over both stores (the parts of X2, X3 and X5 that belong to the policy
and the focus are proved again by nodes 13.8 and 13.16): a correction typed while the person speaks waits and goes in ONE
batch after the voice, in the order they were begun; a control never waits; the same words on both channels are two
entries; a text waits behind an incomplete voice only until it ends; two texts in the collect window are one batch;
past the hold cap the text runs alone, with its event and its text, and the voice comes later on its own.
"""
from __future__ import annotations

from conversation.ear import signals as S
from conversation.inbox.accounting import audit
from conversation.types import ControlOp, EnvelopeKind
from tests.conversation.unit.earkit import beats, span, words
from tests.conversation.unit.inboxkit import ACCT, Pipe, control, kinds

UTT, TEXT, STATE = str(EnvelopeKind.USER_UTTERANCE), str(EnvelopeKind.USER_TEXT), str(EnvelopeKind.INTERVENTION_STATE)


def _voice_open(p: Pipe, t0: int = 0, lang_tok=("w1", "w2")):
    p.signal(S.VadEdge("d1", "rise", t0), span(1, 1, False, words(*lang_tok, t0=t0), stream="d1"))


def _voice_close(p: Pipe, t: int, toks=("w1", "w2", "w3")):
    p.signal(span(1, 2, True, words(*toks, t0=0), stream="d1"), S.VadEdge("d1", "fall", t - 300),
             beats(t - 300, t, stream="d1"), S.EotHint("d1", "flux", "end", .9, t))


def test_x1_a_correction_typed_while_he_speaks_is_one_batch_in_the_order_he_began(store, clock, telemetry):
    p = Pipe(store, clock, telemetry)
    _voice_open(p, 0)
    held = p.signal(S.TypedSubmit("d2", "c1", "w9", 500))           # accepted FIRST, begun after the voice
    assert held[0].disposition == "held" and p.at(600).batch() is None
    _voice_close(p, 1500)
    b = p.at(1500).batch()
    assert kinds(b) == [UTT, TEXT] and b.reason == "cross_channel"
    assert b.envelopes[0].accepted_ms > b.envelopes[1].accepted_ms   # ordered by onset, not by arrival
    assert "conv_inbox/held" in telemetry.labels() and "conv_inbox/released" in telemetry.labels()


def test_x2_a_text_then_voice_are_two_inputs_in_the_order_he_began(store, clock, telemetry):
    p = Pipe(store, clock, telemetry)
    p.signal(S.TypedSubmit("d2", "c1", "w9", 0))
    first = p.at(400).batch()
    assert kinds(first) == [TEXT]
    _voice_open(p, 600)
    _voice_close(p, 1800)
    assert kinds(p.at(1800).batch()) == [UTT]


def test_x3_a_text_while_the_agent_speaks_is_ready_at_once(store, clock, telemetry):
    p = Pipe(store, clock, telemetry)
    p.signal(S.PlaybackState("d1", True, 0), S.TypedSubmit("d1", "c1", "w9", 100))
    assert kinds(p.at(450).batch(idle=False)) == [TEXT]


def test_x4_a_typed_stop_or_a_button_with_the_voice_open_is_applied_at_once(store, clock, telemetry):
    p = Pipe(store, clock, telemetry)
    _voice_open(p, 0)
    for n, ch in (("k1", "text"), ("k2", "button")):
        from conversation.types import Channel
        adm = p.give(control(ControlOp.STOP, 300, n, endpoint="d2", channel=Channel(ch)))
        assert adm.disposition == "control"
    assert p.ear.open_intervention() is not None                    # the voice stays open
    _voice_close(p, 1500)
    assert kinds(p.at(1500).batch()) == [UTT]


def test_x6_the_same_words_on_both_channels_are_two_entries(store, clock, telemetry):
    p = Pipe(store, clock, telemetry)
    _voice_open(p, 0)
    p.signal(S.TypedSubmit("d2", "c1", "w1 w2 w3", 400))
    _voice_close(p, 1500)
    b = p.at(1500).batch()
    assert kinds(b) == [UTT, TEXT] and b.envelopes[0].body.text == b.envelopes[1].body.text


def test_x7_a_confirm_button_with_the_voice_open_does_not_wait(store, clock, telemetry):
    p = Pipe(store, clock, telemetry)
    _voice_open(p, 0)
    adm = p.give(control(ControlOp.CONFIRM, 300, "k1", gesture=True, handle="h1"))
    assert adm.disposition == "control" and adm.envelope.body.gesture


def test_x8_a_voice_that_ends_incomplete_releases_the_text_and_asks_for_the_end(store, clock, telemetry):
    p = Pipe(store, clock, telemetry)
    _voice_open(p, 0)
    p.signal(beats(240, 400, stream="d1"), S.TypedSubmit("d2", "c1", "w9", 400))
    p.signal(S.Tick(400 + 1500))                                     # the stream stopped beating
    b = p.at(1900).batch()
    assert kinds(b) == [STATE, TEXT] and str(b.envelopes[0].body.state) == "incomplete"


def test_x9_two_texts_under_350_ms_are_one_batch(store, clock, telemetry):
    p = Pipe(store, clock, telemetry)
    p.signal(S.TypedSubmit("d1", "c1", "w1", 0), S.TypedSubmit("d2", "c2", "w2", 349))
    assert p.at(600).batch() is None
    assert kinds(p.at(700).batch()) == [TEXT, TEXT]


def test_x10_past_the_hold_cap_the_text_runs_alone_and_the_voice_comes_later(store, clock, telemetry):
    p = Pipe(store, clock, telemetry)
    _voice_open(p, 0)
    p.signal(beats(240, 480, stream="d1"), S.TypedSubmit("d2", "c1", "w9", 500))
    p.signal(beats(720, 8400, stream="d1"))                           # alive and still open
    assert p.at(8499).batch() is None
    b = p.at(8500).batch()
    assert kinds(b) == [TEXT]
    expired = [pl for k, lab, pl in telemetry.events if k == "conv_inbox" and lab == "expired"]
    assert expired and expired[0]["text"] == "w9"
    p.inbox.account([e.id for e in b.envelopes], "told", 8500)
    p.signal(beats(8640, 9200, stream="d1"))
    _voice_close(p, 9500)
    assert kinds(p.at(9500).batch()) == [UTT]
    assert audit(store.snapshot(ACCT), 9500, p.cfg) == []


def test_x5_a_yes_on_a_device_where_the_question_was_not_presented_has_no_focus():
    from conversation.manager.focus import Focus
    f = Focus()
    f.presented("h1", "desk", 100)                      # painted / played on the desktop only
    assert f.onset("phone") is None                     # «yes» said to the phone: nothing to answer
    assert f.onset("desk") == "h1"
    f.presented("q9", "desk", 200)                      # a worker's question appears while the person speaks…
    assert f.of("desk") == "h1"                          # …and does not steal the pinned focus
    f.done_speaking("desk")
    assert f.onset("desk") is None                      # two candidates now: ambiguous, nothing authorises
    f.done_speaking("desk")
    f.closed("q9")
    assert f.onset("desk") == "h1"
