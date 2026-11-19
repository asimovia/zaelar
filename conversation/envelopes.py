"""The envelope: the ONLY thing that enters the inbox (§5.1), with a typed body per kind.

`from_json` is strict: an unknown kind, an unknown field or a missing one is refused (`EnvelopeError`), and the
authority and channel of a kind are FIXED here — an envelope that claims `user` authority for a contact's message is
refused, never read as the person (I8). The authority of an envelope is what its producer is, not what it says.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any

from conversation.types import (Authority, Channel, ControlOp, EnvelopeKind, Evidence, IvState, Surfacing,
                                WorkerUpdate)

SCHEMA = 1


class EnvelopeError(ValueError):
    """The envelope is not one this schema knows: refused, never guessed."""


@dataclass(frozen=True)
class Refs:
    task_id: str | None = None
    question_id: str | None = None
    thread_id: str | None = None
    reply_to: str | None = None
    reminder_id: str | None = None
    handle_id: str | None = None
    intervention_id: str | None = None
    revision: int | None = None


@dataclass(frozen=True)
class Span:
    """One final word of the speech-to-text, with its audio times."""
    word: str
    t0_ms: int
    t1_ms: int
    conf: float = 1.0


@dataclass(frozen=True)
class UtteranceBody:
    intervention_id: str
    revision: int
    text: str
    spans: tuple[Span, ...] = ()
    lang: str = ""
    coverage: str = "full"
    amends: str | None = None


@dataclass(frozen=True)
class TextBody:
    intervention_id: str
    text: str
    attachments: tuple[str, ...] = ()
    amends: str | None = None


@dataclass(frozen=True)
class ControlBody:
    op: ControlOp
    handle_id: str | None = None
    task_id: str | None = None
    gesture: bool = False
    scope: dict | None = None   # a delegation's scope: recipients, channel, expires_ms, max


@dataclass(frozen=True)
class InterventionStateBody:
    intervention_id: str
    state: IvState
    revision: int = 1
    text: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class ReminderBody:
    reminder_id: str
    text: str
    due_ms: int


@dataclass(frozen=True)
class ContactBody:
    thread_id: str
    sender_ref: str
    text: str
    reply_to: str | None = None


@dataclass(frozen=True)
class WorkerBody:
    task_id: str
    type: WorkerUpdate
    text: str
    question_id: str | None = None
    evidence: tuple[Evidence, ...] = ()


Body = UtteranceBody | TextBody | ControlBody | InterventionStateBody | ReminderBody | ContactBody | WorkerBody

#: kind → (body class, the authority it carries, the channels it may come by, the producers that may send it).
#: Fixed: never read off the wire. The inbox refuses an envelope whose producer is not one of its kind's (M1): a
#: connector cannot hand in «the person's text», whatever kind it writes on the envelope.
KINDS: dict[EnvelopeKind, tuple[type, Authority, frozenset[Channel], tuple[str, ...]]] = {
    EnvelopeKind.USER_UTTERANCE: (UtteranceBody, Authority.USER, frozenset({Channel.VOICE}), ("ear:",)),
    EnvelopeKind.USER_TEXT: (TextBody, Authority.USER, frozenset({Channel.TEXT}), ("chat:",)),
    EnvelopeKind.USER_CONTROL: (ControlBody, Authority.USER,
                                frozenset({Channel.VOICE, Channel.TEXT, Channel.BUTTON}),
                                ("button:", "chat:", "ear:", "guard:")),
    EnvelopeKind.INTERVENTION_STATE: (InterventionStateBody, Authority.USER, frozenset({Channel.VOICE}), ("ear:",)),
    EnvelopeKind.SYSTEM_REMINDER: (ReminderBody, Authority.SYSTEM, frozenset({Channel.SYSTEM}),
                                   ("pulse:", "system:", "manager:")),
    EnvelopeKind.CONTACT_MESSAGE: (ContactBody, Authority.CONTACT, frozenset({Channel.CONNECTOR}), ("connector:",)),
    EnvelopeKind.WORKER_UPDATE: (WorkerBody, Authority.WORKER, frozenset({Channel.WORKER}), ("worker:",)),
}


def producer_allowed(env: "Envelope") -> bool:
    """Is the producer one that may send this kind (the authority follows the producer, not the label)? A gesture —
    and anything on the button channel — is the button producer's alone (review 2, MINOR 2: a `chat:` control on the
    BUTTON channel created a delegation)."""
    if env.kind is EnvelopeKind.USER_CONTROL and (env.channel is Channel.BUTTON or env.body.gesture):
        return env.producer.startswith("button:")
    return env.producer.startswith(KINDS[env.kind][3])


def _gesture_by_button(kind: EnvelopeKind, body: Body, channel: Channel) -> None:
    """A gesture is a button on the device (PA-10): a text or a voice control is never one."""
    if kind is EnvelopeKind.USER_CONTROL and body.gesture and channel is not Channel.BUTTON:
        raise EnvelopeError(f"a gesture comes by a button, not by {channel}")


@dataclass(frozen=True)
class Envelope:
    schema: int
    id: str
    producer: str
    producer_id: str
    account: str
    session: str | None
    endpoint: str | None
    kind: EnvelopeKind
    channel: Channel
    authority: Authority
    cause: str | None
    refs: Refs
    onset_ms: int
    sealed_ms: int
    accepted_ms: int
    surfacing: Surfacing
    must_tell: bool
    expires_ms: int | None
    body: Body = field(compare=False)

    @property
    def is_user(self) -> bool:
        return self.authority is Authority.USER


def make(kind: EnvelopeKind, body: Body, *, producer: str, producer_id: str, account: str, onset_ms: int,
         sealed_ms: int, channel: Channel | None = None, endpoint: str | None = None, session: str | None = None,
         cause: str | None = None, refs: Refs | None = None, surfacing: Surfacing = Surfacing.NOW,
         must_tell: bool = False, expires_ms: int | None = None) -> Envelope:
    """An envelope as a producer hands it over: no id and no `accepted_ms` yet (the inbox sets both)."""
    cls, authority, channels, _producers = KINDS[kind]
    if not isinstance(body, cls):
        raise EnvelopeError(f"{kind}: body must be {cls.__name__}")
    channel = channel or next(iter(sorted(channels, key=str)))
    if channel not in channels:
        raise EnvelopeError(f"{kind} cannot come by {channel}")
    _gesture_by_button(kind, body, channel)
    return Envelope(SCHEMA, "", producer, producer_id, account, session, endpoint, kind, channel, authority, cause,
                    refs or Refs(), onset_ms, sealed_ms, 0, surfacing, must_tell, expires_ms, body)


# ── JSON ─────────────────────────────────────────────────────────────────────────────────────────────────────────

def _plain(v: Any) -> Any:
    if isinstance(v, Evidence):
        return v.to_json()
    if isinstance(v, Span):
        return [v.word, v.t0_ms, v.t1_ms, v.conf]
    if isinstance(v, tuple):
        return [_plain(x) for x in v]
    if hasattr(v, "value") and isinstance(v, str):
        return str(v)
    return v


def to_json(env: Envelope) -> dict:
    out = {f.name: _plain(getattr(env, f.name)) for f in fields(env) if f.name not in ("refs", "body")}
    out["refs"] = {f.name: getattr(env.refs, f.name) for f in fields(Refs)}
    out["body"] = {f.name: _plain(getattr(env.body, f.name)) for f in fields(env.body)}
    return out


def _strict(cls: type, d: dict, where: str) -> dict:
    if not isinstance(d, dict):
        raise EnvelopeError(f"{where}: not an object")
    names = {f.name for f in fields(cls)}
    unknown = set(d) - names
    if unknown:
        raise EnvelopeError(f"{where}: unknown fields {sorted(unknown)}")
    return d


def _body(kind: EnvelopeKind, d: dict) -> Body:
    cls = KINDS[kind][0]
    d = dict(_strict(cls, d, f"{kind} body"))
    try:
        if cls is UtteranceBody:
            d["spans"] = tuple(Span(str(w), int(a), int(b), float(c)) for w, a, b, c in d.get("spans", ()))
        if cls is TextBody:
            d["attachments"] = tuple(d.get("attachments", ()))
        if cls is ControlBody:
            d["op"] = ControlOp(d["op"])
        if cls is InterventionStateBody:
            d["state"] = IvState(d["state"])
        if cls is WorkerBody:
            d["type"] = WorkerUpdate(d["type"])
            d["evidence"] = tuple(Evidence.from_json(e) for e in d.get("evidence", ()))
        return cls(**d)
    except (TypeError, ValueError, KeyError) as e:
        raise EnvelopeError(f"{kind} body: {e}") from e


def from_json(d: dict) -> Envelope:
    d = dict(_strict(Envelope, d, "envelope"))
    missing = {f.name for f in fields(Envelope)} - set(d)
    if missing:
        raise EnvelopeError(f"envelope: missing {sorted(missing)}")
    if d["schema"] != SCHEMA:
        raise EnvelopeError(f"schema {d['schema']} is not {SCHEMA}")
    try:
        kind = EnvelopeKind(d["kind"])
    except ValueError as e:
        raise EnvelopeError(f"unknown kind {d['kind']!r}") from e
    _cls, authority, channels, _producers = KINDS[kind]
    try:
        channel, claimed = Channel(d["channel"]), Authority(d["authority"])
        surfacing = Surfacing(d["surfacing"])
    except ValueError as e:
        raise EnvelopeError(str(e)) from e
    if claimed is not authority:
        raise EnvelopeError(f"{kind} carries {authority} authority, not {claimed}")
    if channel not in channels:
        raise EnvelopeError(f"{kind} cannot come by {channel}")
    d.update(kind=kind, channel=channel, authority=authority, surfacing=surfacing,
             refs=Refs(**_strict(Refs, d["refs"], "refs")), body=_body(kind, d["body"]))
    _gesture_by_button(kind, d["body"], channel)
    return Envelope(**d)


#: the reason an `intervention.state(open)` carries when it is a REOPEN (a new revision), not an extension
REOPENED = "reopened"


def is_reopen(env: Envelope) -> bool:
    """THE one reading of «this intervention was reopened»: a voice intervention back to open at a NEW revision —
    said by the ear in the envelope's reason, never inferred from the revision number (an extension of revision 2 is
    open at revision 2 too). Policy row 6 (supersede only while nothing is sealed) keys on this and nothing else."""
    return (env.kind is EnvelopeKind.INTERVENTION_STATE and env.body.state is IvState.OPEN
            and env.body.reason == REOPENED)
