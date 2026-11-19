"""The closed vocabularies of the conversation manager: channels, authorities, envelope kinds, policy operations,
ledger item kinds, states — and the id factory.

Every name here is a value the code switches on; none of them is read from what the person said. A new value is a
change of contract: it lands here, in the policy table (`manager/policy.py`) and in its tests at once.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class _Str(str, Enum):
    def __str__(self) -> str:   # the value, in logs and in JSON
        return self.value


class Channel(_Str):
    VOICE = "voice"
    TEXT = "text"
    BUTTON = "button"


class Authority(_Str):
    """Who an envelope speaks for: only the person enters the inbox. What the engine owes the person (a worker's
    result, a contact's message, a reminder) is a line it says, never an entry (I8)."""
    USER = "user"


class EnvelopeKind(_Str):
    USER_UTTERANCE = "user.utterance"
    USER_TEXT = "user.text"
    USER_CONTROL = "user.control"


class Coverage(_Str):
    """How much of an utterance the ear heard: all of it, or it ended without its final words (the run asks)."""
    FULL = "full"
    INCOMPLETE = "incomplete"


class ControlOp(_Str):
    STOP = "stop"
    CONFIRM = "confirm"
    DECLINE = "decline"
    CANCEL_TASK = "cancel_task"
    DELEGATE = "delegate"


class IvState(_Str):
    """An intervention of the person: what they said (or typed) between two of our turns. Once ended it never changes:
    what follows is another intervention that amends it."""
    OPEN = "open"
    TENTATIVE = "tentative"
    CLOSED = "closed"
    INCOMPLETE = "incomplete"
    SEALED = "sealed"
    FINAL = "final"
    DISCARDED = "discarded"


class MgrState(_Str):
    IDLE = "idle"
    COLLECTING = "collecting"
    RUNNING_UNCLAIMED = "running_unclaimed"
    RUNNING_CLAIMED = "running_claimed"
    SPEAKING = "speaking"


class Op(_Str):
    """The operations of the policy table (§7). Each is something the manager DOES, never a reading of content."""
    FIX_FOCUS = "fix_focus"          # pin the device's focus at the onset of their speech
    DUCK = "duck"                    # lower our voice, reversible
    SILENCE = "silence"              # stop our voice, local and immediate
    HOLD_ACTIONS = "hold_actions"    # unclaimed actions wait
    RUN_NOW = "run_now"
    JOIN = "join"                    # joins the batch being collected
    SUPERSEDE = "supersede"          # replace the RUN at a checkpoint (the request stays open)
    FOLLOW_UP = "follow_up"          # queue as a follow-up that references the run
    CANCEL_RUN = "cancel_run"
    BY_ID = "by_id"                  # goes to its ledger item by id
    SURFACE_NOW = "surface_now"
    WHEN_IDLE = "when_idle"
    COALESCE = "coalesce"
    SILENT = "silent"
    WAIT_FOCUS = "wait_focus"        # does not take the focus while they speak
    HOLD_BEHIND = "hold_behind"      # waits for the open voice intervention that began earlier
    AT_CHECKPOINT = "at_checkpoint"  # enters the running turn at its next checkpoint
    WAIT_AGAIN = "wait_again"        # the batch waits for the reopened intervention to close
    IMPOSSIBLE = "impossible"        # the state cannot hold this input
    NONE = "none"


class ItemKind(_Str):
    REQUEST = "request"
    TASK = "task"
    QUESTION = "question"
    GRANT = "grant"
    HANDLE = "handle"
    DELEGATION = "delegation"
    EFFECT = "effect"
    FOLLOWUP = "followup"
    TO_TELL = "to_tell"


class EffectClass(_Str):
    """What a tool does to the world (plan §15 E2). Everything but `read` is an effect; `egress`, `destructive` and
    `payment` need a gesture (a presented handle) or, for `egress` only, a delegation."""
    READ = "read"
    LOCAL_WRITE = "local_write"
    EGRESS = "egress"
    DESTRUCTIVE = "destructive"
    PAYMENT = "payment"


@dataclass(frozen=True)
class Evidence:
    """One fact a tool returned, structured enough for a numeric claim to be matched against it (D9)."""
    id: str
    source: str
    entity: str = ""
    period: str = ""
    metric: str = ""
    direction: str = ""
    value: float | None = None

    def to_json(self) -> dict:
        return {k: getattr(self, k) for k in ("id", "source", "entity", "period", "metric", "direction", "value")}

    @classmethod
    def from_json(cls, d: dict) -> "Evidence":
        return cls(**{k: d.get(k, "" if k != "value" else None) for k in
                      ("id", "source", "entity", "period", "metric", "direction", "value")})


class Ids:
    """Ids with a prefix and a counter: deterministic (a replay mints the same ids), unique within one manager.
    The `space` keeps two managers (two processes, two tests) from colliding when they share a store."""

    def __init__(self, space: str = "") -> None:
        self._n = 0
        self._space = space

    def new(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}_{self._space}{self._n:06d}"
