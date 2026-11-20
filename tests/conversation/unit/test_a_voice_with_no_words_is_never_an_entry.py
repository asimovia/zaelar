"""A voice with no words is never an entry, and a second session hears him whole (node 13.97, V2-941, v3.1 B8e).

The voice smoke (3b) on B8d found:
  · every batch carrying an EMPTY entry after his sentence (the successor voice the ear opened ended with no words, as
    an incomplete entry); in one case the model read «empty and cut off: nothing to answer» and closed SILENT over a
    whole question in the same batch — now a voice that ends with no words is a discard with its reason
    (`no_words`, I4), the composer never writes an empty item, and a batch with nothing said in it runs no model: it
    fails with the language's line, owed;
  · a SECOND session in the same voice process losing everything: each session's tap counted its epochs from 1
    again — the epochs are the process's now; proven on the real recordings, two sessions in one body's life;
  · a close per request of a batch, each with its `req`: `ended` says how many it closed.
"""
from __future__ import annotations

from conversation import envelopes as E
from conversation.composer import blocks
from conversation.ear import signals as S
from conversation.ports import Done
from conversation.testing.scripted_model import reply
from conversation.types import Channel, Coverage, EnvelopeKind
from nucleo.conversation_host import ear_in
from tests.conversation.unit.convkit import Harness
from tests.conversation.unit.test_every_word_flux_gave_reaches_one_intervention import FLUX, T0
from voice.engine.pipeline import ear_tap

import json


def test_a_voice_that_ends_with_no_words_is_a_discard_never_an_entry(store):
    h = Harness(store, grace=False)
    h.model.default = lambda ids: [reply("w9"), Done()]
    h.hear(S.VadEdge("d1", "rise", 10))
    h.hear(S.LinkGap("d1", 900))                                              # it ends incomplete, wordless
    h.settle(10_000)
    utterances = [r for _k, r in h.store.snapshot(h.conv.account).scan("inbox") if r["kind"] == "user.utterance"]
    assert utterances == [] and h.model.calls == []
    discarded = [p for k, lab, p in h.tel.events if k == "conv_ear" and lab == "discarded"]
    assert discarded and discarded[-1]["reason"] == "no_words"


def _utterance(iv, text, coverage=Coverage.FULL):
    return E.make(EnvelopeKind.USER_UTTERANCE, E.UtteranceBody(iv, text, coverage=coverage), producer="ear:d1",
                  producer_id=f"{iv}:x", account="a", onset_ms=0, sealed_ms=0, channel=Channel.VOICE, endpoint="d1",
                  refs=E.Refs(intervention_id=iv))


def test_the_composer_never_writes_an_empty_item():
    got = blocks.input_block((_utterance("iv1", "w1 w2"), _utterance("iv2", "", Coverage.INCOMPLETE)))
    assert "iv2" not in got and "«»" not in got and "iv1" in got


def test_a_batch_with_nothing_said_runs_no_model_and_owes_the_line(store):
    h = Harness(store, grace=False)
    h.model.default = lambda ids: [reply("w9"), Done()]
    h.conv.give(E.make(EnvelopeKind.USER_UTTERANCE, E.UtteranceBody("iv_x", "", coverage=Coverage.INCOMPLETE),
                       producer="ear:d1", producer_id="iv_x:i", account=h.conv.account, onset_ms=10, sealed_ms=10,
                       channel=Channel.VOICE, endpoint="d1", refs=E.Refs(intervention_id="iv_x")))
    h.settle(3000)
    assert h.model.calls == [] and [(lab, p["reason"]) for lab, p in h.closes()] == [("recovered", "no_words")]
    assert "conv:failed:r_iv_x" in h.owed.rows


def test_ended_says_how_many_requests_it_closed(store):
    h = Harness(store, grace=False, config=None)
    h.model.default = lambda ids: [reply("w9"), Done()]
    h.typed("w1", 10)
    h.settle(1000)
    ended = [p for k, lab, p in h.tel.events if k == "conv_run" and lab == "ended" and p.get("outcome") == "answered"]
    assert ended and ended[-1]["requests"] == len([1 for lab, p in h.closes() if lab == "answered"])
    assert all(p["refs"].get("req") for _lab, p in h.closes())


def _session(h, name: str, seq0: int) -> tuple[list, int]:
    """One voice SESSION of the same process: a tap of its own, its stream from 0 — the boot unchanged."""
    facts: list = []
    tap = ear_tap.Tap("d1", facts.append)
    tap.new_stream()
    finals, seq, start = [], seq0, None
    for line in (FLUX / f"{name}.jsonl").read_text(encoding="utf-8").splitlines():
        msg = json.loads(line)["msg"]
        if msg.get("type") != "TurnInfo":
            continue
        if start is None:
            start = h.clock.mono + 3000
            tap.clock.t0_wall_ms = start
        if msg["event"] == "EndOfTurn":
            finals += [w["word"] for w in msg.get("words") or ()]
        tap.on_message(msg)
        for fact in facts:
            seq += 1
            ear_in.receive({**fact, "boot": "b1", "seq": seq}, h.hear)
        facts.clear()
    h.settle(12_000)
    return finals, seq


def test_a_second_session_of_the_same_process_hears_him_whole(store):
    ear_in._reset_for_tests()
    h = Harness(store, grace=False)
    h.model.default = lambda ids: [reply("w_ok"), Done()]
    h.at(T0)
    first, seq = _session(h, "en-clean-03-g9", 0)
    second, _ = _session(h, "mix-pauses1500-00-g9u1", seq)
    rows = sorted((r for _k, r in h.store.snapshot(h.conv.account).scan("inbox") if r["kind"] == "user.utterance"),
                  key=lambda r: r["accepted"])
    heard = [w for r in rows for w in r["env"]["body"]["text"].split()]
    assert heard == first + second, (len(first + second), len(heard))
    ear_in._reset_for_tests()
