"""V2-886 D4 — CRIT-C5's second half at the worker's exit: a send whose recipient the WORKER chose, from an errand
whose reading asks for nothing to be sent in his name, is dropped with an event — never turned into a question.

Measured 2026-11-11: a worker launched to «close absolutely everything» prepared a WhatsApp draft and the exit asked
him «the process wants to send_draft to <raw id> in your name — shall I?». Backed sends keep their path (asked once
when the recipient is not his word); a held row, his word for the recipient, a mandate or no reading at all are
never dropped here."""
from types import SimpleNamespace

import pytest

from nucleo.workers import exit_slots as exit_gate


def _got(src="agent", released=False):
    return SimpleNamespace(sources={"recipient": src} if src else {}, released=released)


@pytest.fixture
def reading(monkeypatch):
    from nucleo.turn import verdicts
    v = {}

    def read(h, k, fb, min_confidence=None):
        t = v.get(k)
        floor = verdicts.LICENCE if min_confidence is None else min_confidence
        return (t[0], {"confidence": t[1]}) if t and t[1] >= floor else (fb, None)
    monkeypatch.setattr(verdicts, "read", read)
    return v


REC = SimpleNamespace(task_id="t1", mandate=None)


@pytest.mark.parametrize("cls", ["none", "acts_on_screen"])
def test_a_workers_own_recipient_with_no_send_in_the_reading_is_dropped(reading, cls):
    reading.update(errand_class=(cls, 0.9), message_channel=("none", 0.9))
    assert exit_gate.unbacked_send(REC, object(), _got("agent"))
    assert exit_gate.unbacked_send(REC, object(), _got("none"))


@pytest.mark.parametrize("backing", [{"errand_class": ("sends_for_him", 0.8)},
                                     {"message_channel": ("whatsapp", 0.7)},
                                     {"message_channel": ("email", 0.6)}])
def test_a_reading_that_sends_keeps_the_send(reading, backing):
    reading.update(errand_class=("none", 0.9), message_channel=("none", 0.9))
    reading.update(backing)
    assert exit_gate.unbacked_send(REC, object(), _got("agent")) == ""


def test_his_word_a_held_row_a_mandate_or_no_reading_are_never_dropped(reading, monkeypatch):
    reading.update(errand_class=("none", 0.9), message_channel=("none", 0.9))
    assert exit_gate.unbacked_send(REC, object(), _got("his")) == ""
    assert exit_gate.unbacked_send(REC, object(), _got("reading")) == ""
    assert exit_gate.unbacked_send(REC, object(), _got("agent", released=True)) == ""
    assert exit_gate.unbacked_send(REC, None, _got("agent")) == ""
    assert exit_gate.unbacked_send(REC, object(), _got("agent"), mandated=True) == ""
