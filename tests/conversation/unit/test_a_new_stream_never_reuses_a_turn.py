"""A new stream on the same device never reuses a turn (node 13.93, V2-941, v3.1 B8d — the audit's TH-1).

The provider numbers its turns from 0 on EVERY stream: a second voice session in the body's life, a reconnect of the
provider, a restart of the voice process. The tap names every stream by the device, so a second stream's turn 0 met
the first one's, finished: with fewer words it «brought nothing» and was dropped, with more only the extra words
passed. Now:
  · the tap gives each stream an EPOCH, on every fact, and a new stream declares the gap of the one before it;
  · the body numbers each turn by (stream, the voice process's boot, epoch, the provider's turn) — the ear's own
    number, never the provider's — and a new boot of the voice process is a gap;
  · so two sentences on two streams of one device, the second with fewer words and with more, are both answered
    whole.
"""
from __future__ import annotations

import pytest

from conversation.ear import signals as S
from conversation.ports import Done
from conversation.testing.scripted_model import reply
from nucleo.conversation_host import ear_in
from tests.conversation.unit.convkit import Harness
from voice.engine.pipeline import ear_tap


@pytest.fixture(autouse=True)
def clean():
    ear_in._reset_for_tests()
    yield
    ear_in._reset_for_tests()


def _through_the_body(h, epoch):
    """The harness's signals as the body hands them: each provider turn numbered by the ear (`ear_in._turn_of`)."""
    hear = h.conv.hear

    def mapped(sig):
        if isinstance(sig, S.WordSpan):
            seq = ear_in._turn_of({"stream": sig.stream, "boot": "b1", "epoch": epoch["n"], "turn": sig.seq})
            sig = S.WordSpan(sig.stream, seq, sig.revision, sig.final, sig.words, sig.window)
        return hear(sig)
    h.conv.hear = mapped


@pytest.mark.parametrize("second", [["w5", "w6"], ["w5", "w6", "w7", "w8", "w9", "w10", "w11"]])
def test_two_streams_on_one_device_are_both_answered_whole(store, second):
    h = Harness(store, grace=False)
    h.model.default = lambda ids: [reply("w_ok"), Done()]
    epoch = {"n": 1}
    _through_the_body(h, epoch)
    h._seq = 0
    h.utter([(["w1", "w2", "w3", "w4"], 0)], at=10)
    h.settle(3000)
    epoch["n"] = 2                                                            # the provider's stream again: turn 0
    h._seq = 0
    h.utter([(second, 0)], at=h.clock.mono + 2000)
    h.settle(4000)
    inputs = [c.prompt.input for c in h.model.calls]
    assert len(inputs) == 2 and all(w in inputs[1] for w in second)          # the second sentence, whole
    assert [lab for lab, _ in h.closes()] == ["answered", "answered"]


def test_the_tap_gives_each_stream_its_epoch_and_declares_the_gap_of_the_one_before():
    facts = []
    tap = ear_tap.Tap("holder", facts.append)
    tap.new_stream()
    tap.edges.frame(True, 0)
    tap.new_stream()
    tap.edges.frame(False, 500)
    (k0, e0), (k1, e1), (k2, e2) = [(f["t"], f["epoch"]) for f in facts]
    assert (k0, k1, k2) == ("vad", "gap", "vad") and e1 == e0 and e2 > e0     # the process's epochs: a new one each


def test_the_body_numbers_turns_by_boot_and_epoch_and_a_new_boot_is_a_gap():
    def words(boot, epoch, turn, seq):
        return {"t": "words", "stream": "holder", "turn": turn, "rev": 1, "final": True, "boot": boot, "seq": seq,
                "epoch": epoch, "words": [["w1", 0, 10, 0.9]], "window": [0, 10]}
    got = []
    for ev in (words("b1", 1, 0, 1), words("b1", 2, 0, 2), words("b1", 2, 0, 3), words("b2", 1, 0, 1)):
        ear_in.receive(ev, got.append)
    spans = [s for s in got if isinstance(s, S.WordSpan)]
    assert len({s.seq for s in spans[:2]}) == 2 and spans[1].seq == spans[2].seq     # same stream, same turn: one
    assert spans[3].seq not in {s.seq for s in spans[:3]}
    assert [type(s).__name__ for s in got].count("LinkGap") == 1                       # the voice process restarted
