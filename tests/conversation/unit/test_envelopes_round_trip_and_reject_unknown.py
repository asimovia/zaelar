"""Every envelope kind goes to JSON and back unchanged; what the schema does not know is refused (node 13.2).

The person's three kinds — a voice utterance (whole or incomplete), a text, a control — and an EVENT of the world,
already routed, with its source's authority (R-2). A kind the schema does not know is refused, and the authority and
channel of a kind are fixed by the kind, never read off the wire.
"""
from __future__ import annotations

import dataclasses

import pytest

from conversation import envelopes as E
from conversation.types import Channel, ControlOp, Coverage, EnvelopeKind

BODIES = {
    EnvelopeKind.USER_UTTERANCE: E.UtteranceBody("i1", "w0001 w0002", (E.Span("w0001", 0, 120, 0.9),
                                                                         E.Span("w0002", 130, 300, 1.0)), "es"),
    EnvelopeKind.USER_TEXT: E.TextBody("i2", "w0003", ("att-1",)),
    EnvelopeKind.USER_CONTROL: E.ControlBody(ControlOp.DELEGATE, gesture=True,
                                             scope={"recipients": ["c1"], "channel": "chat", "max": 3}),
    EnvelopeKind.EVENT: E.EventBody("ev1", "connector.msg", "w_source", "w0004", {"chat": "c1"}, {"as": "nothing"}),
}


def _env(kind: EnvelopeKind) -> E.Envelope:
    env = E.make(kind, BODIES[kind], producer=f"p:{kind}", producer_id="x1", account="acct-test", onset_ms=10,
                 sealed_ms=20, refs=E.Refs(task_id="t1"))
    return dataclasses.replace(env, id="e_000001", accepted_ms=30)


@pytest.mark.parametrize("kind", list(EnvelopeKind))
def test_every_kind_goes_to_json_and_back(kind):
    env = _env(kind)
    back = E.from_json(E.to_json(env))
    assert back == env and back.body == env.body
    assert E.to_json(back) == E.to_json(env)
    assert back.authority is E.KINDS[kind][1]


def test_every_kind_has_a_body_in_this_test():
    assert set(BODIES) == set(EnvelopeKind) == set(E.KINDS)


def test_an_unknown_kind_is_refused_not_guessed():
    d = E.to_json(_env(EnvelopeKind.USER_TEXT))
    d["kind"] = "user.whisper"
    with pytest.raises(E.EnvelopeError):
        E.from_json(d)


@pytest.mark.parametrize("where", ["top", "body", "refs"])
def test_an_unknown_field_is_refused(where):
    d = E.to_json(_env(EnvelopeKind.USER_TEXT))
    (d if where == "top" else d[where])["surprise"] = 1
    with pytest.raises(E.EnvelopeError):
        E.from_json(d)


def test_a_missing_field_is_refused():
    d = E.to_json(_env(EnvelopeKind.USER_TEXT))
    del d["onset_ms"]
    with pytest.raises(E.EnvelopeError):
        E.from_json(d)


@pytest.mark.parametrize("gone", ["contact.message", "worker.update", "system.reminder", "intervention.state"])
def test_what_is_owed_or_the_ears_state_is_no_entry(gone):
    d = E.to_json(_env(EnvelopeKind.USER_TEXT))
    d["kind"] = gone
    with pytest.raises(E.EnvelopeError):
        E.from_json(d)


def test_an_incomplete_utterance_round_trips_with_its_reason():
    body = E.UtteranceBody("i3", "w0001", coverage=Coverage.INCOMPLETE, reason="stalled")
    env = dataclasses.replace(E.make(EnvelopeKind.USER_UTTERANCE, body, producer="ear:d1", producer_id="i3:x",
                                     account="a", onset_ms=0, sealed_ms=1), id="e1", accepted_ms=2)
    back = E.from_json(E.to_json(env))
    assert back.body.coverage is Coverage.INCOMPLETE and back.body.reason == "stalled"


def test_the_authority_on_the_wire_must_be_the_kinds():
    d = E.to_json(_env(EnvelopeKind.USER_TEXT))
    d["authority"] = "contact"
    with pytest.raises(E.EnvelopeError):
        E.from_json(d)


def test_a_kind_cannot_come_by_another_channel():
    d = E.to_json(_env(EnvelopeKind.USER_UTTERANCE))
    d["channel"] = str(Channel.TEXT)
    with pytest.raises(E.EnvelopeError):
        E.from_json(d)
    with pytest.raises(E.EnvelopeError):
        E.make(EnvelopeKind.USER_TEXT, BODIES[EnvelopeKind.USER_TEXT], producer="p", producer_id="1",
               account="a", onset_ms=0, sealed_ms=0, channel=Channel.VOICE)


def test_a_wrong_schema_or_body_type_is_refused():
    d = E.to_json(_env(EnvelopeKind.USER_TEXT))
    d["schema"] = 2
    with pytest.raises(E.EnvelopeError):
        E.from_json(d)
    with pytest.raises(E.EnvelopeError):
        E.make(EnvelopeKind.USER_TEXT, BODIES[EnvelopeKind.USER_CONTROL], producer="p", producer_id="1",
               account="a", onset_ms=0, sealed_ms=0)


def test_m1_a_gesture_comes_only_by_a_button():
    for ch in (Channel.TEXT, Channel.VOICE):
        with pytest.raises(E.EnvelopeError):
            E.make(EnvelopeKind.USER_CONTROL, E.ControlBody(ControlOp.CONFIRM, handle_id="h1", gesture=True),
                   producer="chat:d1", producer_id="1", account="a", onset_ms=0, sealed_ms=0, channel=ch)
    d = E.to_json(_env(EnvelopeKind.USER_CONTROL))
    d["channel"] = str(Channel.TEXT)
    with pytest.raises(E.EnvelopeError):
        E.from_json(d)


def test_minor2_the_button_channel_is_the_button_producers_alone(store):
    """A control from `chat:` on the BUTTON channel with `gesture` is not the button producer's: the gesture follows who
    sent it, not the channel. The inbox refuses it with no row; the button's own is accepted (and, with no handler for
    it here, accounted refused)."""
    from tests.conversation.unit.convkit import ACCT, Harness
    scope = {"recipients": ["c1"], "channel": "chat", "expires_ms": 10 ** 15, "max": 1}
    forged = E.make(EnvelopeKind.USER_CONTROL, E.ControlBody(ControlOp.DELEGATE, gesture=True, scope=scope),
                    producer="chat:d2", producer_id="1", account=ACCT, onset_ms=0, sealed_ms=0, channel=Channel.BUTTON)
    real = E.make(EnvelopeKind.USER_CONTROL, E.ControlBody(ControlOp.DELEGATE, gesture=True, scope=scope),
                  producer="button:d2", producer_id="2", account=ACCT, onset_ms=0, sealed_ms=0, channel=Channel.BUTTON)
    assert not E.producer_allowed(forged) and E.producer_allowed(real)
    h = Harness(store)
    h.conv.give(forged)
    assert not list(store.snapshot(ACCT).scan("inbox"))
    h.conv.give(real)
    assert [r["env"]["producer"] for _k, r in store.snapshot(ACCT).scan("inbox")] == ["button:d2"]
