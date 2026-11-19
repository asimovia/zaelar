"""One arbiter decides when the person finished (node 13.4, D1, A6).

An intervention CLOSES on the provider's end of turn with full coverage and the watermark past the voice's last
fall — never on an eager hint, never because two detectors agree. Eager + resumed extends it. Past the cap after
the fall it closes with coverage, or ends `incomplete` without; a stream that stops beating ends it `incomplete`; a
declared expectation (a number) gives more patience; voice with no words is discarded with its reason; a guard's
discard is an event with its text. Voice that resumes before the seal reopens; after it, amends. Typed input is
closed on send.
"""
from __future__ import annotations

from conversation.ear import signals as S
from conversation.types import EnvelopeKind
from tests.conversation.unit.earkit import (D, DISCARDED, INCOMPLETE, OPEN, TENTATIVE, beats, feed, onsets, span,
                                            states, utterances, words)


def test_eager_then_resumed_then_end_closes_once_with_the_whole_sentence(ear, telemetry):
    out = feed(ear, S.VadEdge(D, "rise", 0), span(1, 1, False, words("w1", "w2")),
               S.EotHint(D, "flux", "eager", .55, 450), beats(500, 3000),
               S.Tick(3000))                                             # an eager hint alone: still tentative
    assert not utterances(out) and states(out)[-1][0] == TENTATIVE
    out += feed(ear, S.EotHint(D, "flux", "resumed", .1, 3100), span(1, 2, False, words("w1", "w2", "w3")),
                span(1, 3, True, words("w1", "w2", "w3", "w4")), S.VadEdge(D, "fall", 800),
                S.Watermark(D, 900), S.EotHint(D, "flux", "end", .8, 3200))
    closed = utterances(out)
    assert len(closed) == 1 and closed[0].body.text == "w1 w2 w3 w4"
    assert [s for s, _ in states(out)] == [OPEN, TENTATIVE, OPEN]
    assert "conv_ear/closed" in telemetry.labels() and len(onsets(out)) == 1
    closed_ev = [p for k, lab, p in telemetry.events if lab == "closed"][0]
    assert closed_ev["closed_by"] == "eot" and closed_ev["refs"]["iv"] == closed[0].body.intervention_id


def test_the_end_waits_for_the_watermark_to_pass_the_voice_fall(ear):
    out = feed(ear, S.VadEdge(D, "rise", 0), span(1, 1, True, words("w1", "w2")), beats(400, 1700),
               S.VadEdge(D, "fall", 2000), S.EotHint(D, "flux", "end", .9, 2050))
    assert not utterances(out), "closed before the audio up to the fall was processed"
    out = feed(ear, S.Watermark(D, 2010))
    assert len(utterances(out)) == 1


def test_at_the_cap_coverage_closes_and_its_absence_is_incomplete(ear, telemetry):
    out = feed(ear, S.VadEdge(D, "rise", 0), span(1, 1, True, words("w1")), S.VadEdge(D, "fall", 300),
               beats(400, 2799), S.Tick(300 + 2499))
    assert not utterances(out)
    out = feed(ear, S.Watermark(D, 2800))
    assert len(utterances(out)) == 1
    assert [p["closed_by"] for _k, lab, p in telemetry.events if lab == "closed"] == ["cap"]


def test_a_stream_that_stops_beating_ends_incomplete_with_its_words(ear, telemetry):
    out = feed(ear, S.VadEdge(D, "rise", 0), span(1, 1, False, words("w1", "w2")), S.Watermark(D, 400),
               S.Tick(1399))
    assert not states(out)[1:]
    out = feed(ear, S.Tick(1400))
    assert states(out) == [(INCOMPLETE, 1)] and out[0].body.reason == "stalled" and out[0].body.text == "w1 w2"
    assert any(lab == "incomplete" and p["text"] == "w1 w2" for _k, lab, p in telemetry.events)


def test_a_declared_number_gives_more_patience(ear):
    feed(ear, S.ContextHint(D, "number"), S.VadEdge(D, "rise", 0), span(1, 1, True, words("w1")),
         S.VadEdge(D, "fall", 300))
    assert not utterances(feed(ear, beats(300, 300 + 2500 + 1199)))
    assert len(utterances(feed(ear, S.Watermark(D, 300 + 2500 + 1200)))) == 1


def test_voice_with_no_words_is_discarded_and_a_guards_discard_keeps_its_text(ear, telemetry):
    out = feed(ear, S.VadEdge(D, "rise", 0), S.VadEdge(D, "fall", 200), S.Tick(3000))
    assert states(out)[-1] == (DISCARDED, 1) and out[-1].body.reason == "no_words"
    out = feed(ear, S.VadEdge(D, "rise", 4000), span(1, 1, False, words("w9", t0=4000)),
               S.Discard(D, "w9", "echo", 4300))
    assert states(out)[-1][0] == DISCARDED and out[-1].body.text == "w9" and out[-1].body.reason == "echo"
    discards = [p for _k, lab, p in telemetry.events if lab == "discarded"]
    assert [(p["reason"], p["text"]) for p in discards] == [("no_words", ""), ("echo", "w9")]


def test_an_unechoed_rise_is_no_onset_but_a_word_is(ear):
    out = feed(ear, S.VadEdge(D, "rise", 0, echo_safe=False))
    assert not onsets(out)
    out = feed(ear, span(1, 1, False, words("w1", t0=100)))
    assert [o.t_ms for o in onsets(out)] == [100]


def test_after_the_seal_new_voice_amends_and_after_our_reply_it_is_new(ear):
    first = utterances(feed(ear, span(1, 1, True, words("w1")), S.EotHint(D, "flux", "end", .9, 300)))[0]
    feed(ear, S.Sealed(first.body.intervention_id, 1))
    out = feed(ear, span(2, 1, True, words("w2", t0=1000)), S.EotHint(D, "flux", "end", .9, 1300))
    second = utterances(out)[0]
    assert second.body.intervention_id != first.body.intervention_id and second.body.amends == first.body.intervention_id
    feed(ear, S.Sealed(second.body.intervention_id, 1), S.PlaybackState(D, True, 1400),
         S.PlaybackState(D, False, 2000))
    third = utterances(feed(ear, span(3, 1, True, words("w3", t0=3000)), S.EotHint(D, "flux", "end", .9, 3300)))[0]
    assert third.body.amends is None


def test_typed_input_is_closed_on_send(ear, telemetry):
    out = feed(ear, S.TypedSubmit("d2", "c-1", "w5 w6", 777))
    (env,) = out
    assert env.kind is EnvelopeKind.USER_TEXT and env.onset_ms == env.sealed_ms == 777
    assert env.body.text == "w5 w6" and env.producer == "chat:d2" and env.producer_id == "c-1"
    assert telemetry.labels() == ["conv_ear/typed"]


def test_an_eager_hint_over_final_words_never_closes(ear):
    out = feed(ear, S.VadEdge(D, "rise", 0), span(1, 1, True, words("w1", "w2")), S.VadEdge(D, "fall", 400),
               beats(400, 1500), S.EotHint(D, "flux", "eager", .6, 1500), beats(1500, 2800))
    assert not utterances(out) and states(out)[-1][0] == TENTATIVE
