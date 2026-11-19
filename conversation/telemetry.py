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
from typing import Callable

from conversation.ports import Clock, Telemetry

KINDS: dict[str, frozenset[str]] = {
    "conv_ear": frozenset({"opened", "extended", "tentative", "closed", "reopened", "incomplete", "discarded",
                           "onset", "typed"}),
    "conv_inbox": frozenset({"accepted", "duplicate", "held", "released", "expired", "coalesced", "dequeued",
                             "accounted"}),
    "conv_run": frozenset({"started", "input", "prompt", "model_first_token", "model_done", "command", "superseded",
                           "fenced", "cancelled", "port_slow", "ended"}),
    "conv_ledger": frozenset({"opened", "attached", "moved", "refused", "stale_epoch"}),
    "conv_effect": frozenset({"read", "sealed", "claimed", "held", "released", "refused", "submitted", "receipt",
                              "unknown", "reconciled", "write_disabled"}),
    "conv_mouth": frozenset({"say", "started", "ack", "ducked", "unducked", "cut", "ended", "voice_unavailable"}),
    "conv_close": frozenset({"answered", "handed_off", "silent", "recovered", "failed", "stalled"}),
}

#: the owner of each stage (the `owner` field); a worker's events say `worker:<id>`.
OWNERS = frozenset({"ear", "inbox", "manager", "ledger", "gateway", "mouth"})

#: the reference chain every event may carry (§8.1).
REF_KEYS = frozenset({"conv", "iv", "rev", "env", "run", "req", "task", "effect", "say", "endpoint", "channel",
                      "item"})


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
        body = {"t_ms": self.clock.now_ms(), "mono_ms": self.clock.mono_ms(), "account": self.account,
                "epoch": self.epoch(), "owner": owner, "cause": cause or {}, "refs": refs,
                "trace": trace or refs.get("iv") or "", **payload}
        self.port.emit(kind, label, body)
