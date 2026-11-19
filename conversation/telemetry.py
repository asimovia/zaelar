"""THE observability contract of the conversation manager: every kind and label it may emit, in one place (§8).

Every event carries the common fields (`t_ms`, `mono_ms`, `account`, `epoch`, `owner`, `cause`, `refs`, `trace`) plus
its own payload. `Emitter.emit` refuses a kind or a label that is not in `KINDS` (a programming error, raised at
once), so what the code emits and what this table, the architecture map and the viewers know can never drift: node
13.24 walks every call site against this table. No event carries the person's words except the ones I4 requires
(`conv_ear/discarded`, `conv_ear/incomplete`, `conv_inbox/expired`) and `conv_run/input`; the observer scrubs those
like any transcript.

Call sites pass the kind as a literal (`emit("conv_ear", "opened", …)`) so the event names its architecture piece
from the emitting module, like every other event of the engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from conversation.ports import Clock, Telemetry

class _Labels(Enum):
    """Each kind's labels, declared as enums (the code's own vocabulary), read into `KINDS` below."""


class EarLabels(_Labels):
    OPENED, EXTENDED, TENTATIVE, CLOSED = "opened", "extended", "tentative", "closed"
    INCOMPLETE, DISCARDED, ONSET, TYPED = "incomplete", "discarded", "onset", "typed"


class InboxLabels(_Labels):
    ACCEPTED, DUPLICATE, HELD, RELEASED, REFUSED = "accepted", "duplicate", "held", "released", "refused"
    EXPIRED, COALESCED, DEQUEUED, ACCOUNTED = "expired", "coalesced", "dequeued", "accounted"


class RunLabels(_Labels):
    STARTED, INPUT, PROMPT, MODEL_FIRST_TOKEN = "started", "input", "prompt", "model_first_token"
    MODEL_DONE, COMMAND, SUPERSEDED, FENCED = "model_done", "command", "superseded", "fenced"
    CANCELLED, PORT_SLOW, ENDED, HELD = "cancelled", "port_slow", "ended", "held"


class LedgerLabels(_Labels):
    OPENED, ATTACHED, MOVED, REFUSED, STALE_EPOCH = "opened", "attached", "moved", "refused", "stale_epoch"


class EffectLabels(_Labels):
    READ, SEALED, CLAIMED, REFUSED = "read", "sealed", "claimed", "refused"
    SUBMITTED, RECEIPT, UNKNOWN, RECONCILED = "submitted", "receipt", "unknown", "reconciled"
    WRITE_DISABLED = "write_disabled"


class MouthLabels(_Labels):
    SAY, STARTED, ACK, DUCKED, UNDUCKED = "say", "started", "ack", "ducked", "unducked"
    CUT, ENDED, VOICE_UNAVAILABLE = "cut", "ended", "voice_unavailable"


class CloseLabels(_Labels):
    ANSWERED, HANDED_OFF, SILENT, RECOVERED = "answered", "handed_off", "silent", "recovered"
    FAILED, STALLED = "failed", "stalled"


class Owner(Enum):
    """The owner of each stage (the `owner` field); a worker's events say `worker:<id>`."""
    EAR, INBOX, MANAGER, LEDGER, GATEWAY, MOUTH = "ear", "inbox", "manager", "ledger", "gateway", "mouth"


class Ref(Enum):
    """The reference chain every event may carry (§8.1)."""
    CONV, IV, ENV, RUN, REQ, TASK = "conv", "iv", "env", "run", "req", "task"
    EFFECT, SAY, ENDPOINT, CHANNEL, ITEM = "effect", "say", "endpoint", "channel", "item"


KINDS: dict[str, frozenset[str]] = {
    f"conv_{cls.__name__.removesuffix('Labels').lower()}": frozenset(m.value for m in cls)
    for cls in (EarLabels, InboxLabels, RunLabels, LedgerLabels, EffectLabels, MouthLabels, CloseLabels)}
OWNERS = frozenset(m.value for m in Owner)
REF_KEYS = frozenset(m.value for m in Ref)


def root(refs: dict) -> str:
    """The trace of an event: the root intervention of its request (`r_<iv>` → `<iv>`), so `/flow/<corr_id>` follows a
    request from the ear to its close (§8.1)."""
    if refs.get("iv"):
        return str(refs["iv"])
    req = str(refs.get("req") or "")
    return req[2:] if req.startswith("r_") else ""


class UnknownEvent(ValueError):
    """A kind or label outside the contract: the code is wrong, not the event."""


@dataclass
class Emitter:
    """The package's one door to the `Telemetry` port. Stamps the common fields; refuses what the contract lacks."""
    port: Telemetry
    clock: Clock
    account: str
    epoch: Callable[[], int] = field(default=lambda: 0)

    def emit(self, kind: str, label: str, /, *, owner: str, cause: dict | None = None, refs: dict | None = None,
             trace: str | None = None, **payload) -> None:
        if label not in KINDS.get(kind, ()):
            raise UnknownEvent(f"{kind}/{label} is not in conversation.telemetry.KINDS")
        if owner not in OWNERS and not owner.startswith("worker:"):
            raise UnknownEvent(f"owner {owner!r}")
        refs = {k: v for k, v in (refs or {}).items() if v is not None}
        if set(refs) - REF_KEYS:
            raise UnknownEvent(f"refs {sorted(set(refs) - REF_KEYS)}")
        if not cause or not cause.get("kind"):
            raise UnknownEvent(f"{kind}/{label} without its cause")      # every event says what provoked it (§8.1)
        body = {"t_ms": self.clock.now_ms(), "mono_ms": self.clock.mono_ms(), "account": self.account,
                "epoch": self.epoch(), "owner": owner, "cause": cause, "refs": refs,
                "trace": trace or root(refs), **payload}
        try:
            self.port.emit(kind, label, body)
        except Exception as e:  # noqa: BLE001 — the port must never raise; if it does, the manager goes on and counts
            self.lost = getattr(self, "lost", 0) + 1
            self.last_loss = type(e).__name__
