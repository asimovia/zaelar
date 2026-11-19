"""Every envelope kind goes to JSON and back unchanged; what the schema does not know is refused (node 13.2).

The authority of an envelope is fixed by its KIND, never read off the wire: a contact's message that claims to be the
user's is refused, and so is a worker update that claims to be a system reminder's channel. That is the first wall
of I8 — only an envelope of the person can grant anything, and nothing becomes one by saying so.
"""
from __future__ import annotations

import dataclasses

import pytest

from conversation import envelopes as E
from conversation.types import (Authority, Channel, ControlOp, EnvelopeKind, Evidence, IvState, Surfacing,
                                WorkerUpdate)

BODIES = {
    EnvelopeKind.USER_UTTERANCE: E.UtteranceBody("i1", 2, "w0001 w0002", (E.Span("w0001", 0, 120, 0.9),
                                                                         E.Span("w0002", 130, 300, 1.0)), "es"),
    EnvelopeKind.USER_TEXT: E.TextBody("i2", "w0003", ("att-1",)),
    EnvelopeKind.USER_CONTROL: E.ControlBody(ControlOp.DELEGATE, gesture=True,
                                             scope={"recipients": ["c1"], "channel": "chat", "max": 3}),
    EnvelopeKind.INTERVENTION_STATE: E.InterventionStateBody("i1", IvState.OPEN, 1),
    EnvelopeKind.SYSTEM_REMINDER: E.ReminderBody("r1", "w0004", 1_000),
    EnvelopeKind.CONTACT_MESSAGE: E.ContactBody("th1", "contact-ref-1", "w0005", reply_to="m9"),
    EnvelopeKind.WORKER_UPDATE: E.WorkerBody("t1", WorkerUpdate.RESULT, "w0006",
                                             evidence=(Evidence("ev1", "market", "ACME", "2026-W46", "close", "up",
                                                                1.5),)),
}


def _env(kind: EnvelopeKind) -> E.Envelope:
    env = E.make(kind, BODIES[kind], producer=f"p:{kind}", producer_id="x1", account="acct-test", onset_ms=10,
                 sealed_ms=20, refs=E.Refs(task_id="t1"), surfacing=Surfacing.WHEN_IDLE, must_tell=True)
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


@pytest.mark.parametrize("kind", [EnvelopeKind.CONTACT_MESSAGE, EnvelopeKind.WORKER_UPDATE,
                                  EnvelopeKind.SYSTEM_REMINDER])
def test_authority_is_never_elevated_to_the_user(kind):
    d = E.to_json(_env(kind))
    d["authority"] = str(Authority.USER)
    with pytest.raises(E.EnvelopeError):
        E.from_json(d)


def test_a_user_kind_cannot_be_lowered_either():
    d = E.to_json(_env(EnvelopeKind.USER_TEXT))
    d["authority"] = str(Authority.TOOL)
    with pytest.raises(E.EnvelopeError):
        E.from_json(d)


def test_a_kind_cannot_come_by_another_channel():
    d = E.to_json(_env(EnvelopeKind.CONTACT_MESSAGE))
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
