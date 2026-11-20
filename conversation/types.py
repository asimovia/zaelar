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
    """The controls a device may send. In F1 only `stop` and, when the host gives a `Tasks` port, `cancel_task` have a
    handler; the others (the confirmation and the delegation of F2) are refused when accepted, with their event."""
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
    """Three states. Whether the run already claimed an effect is a fact of the run, not a state; collecting is the
    inbox's window, not a state."""
    IDLE = "idle"
    RUNNING = "running"
    SPEAKING = "speaking"


class Op(_Str):
    """The ten operations of the policy table. Each is something the manager DOES, never a reading of content."""
    RUN = "run"                              # the batch runs (when the manager is free)
    SUPERSEDE = "supersede"                  # replace the RUN at its next checkpoint (the request stays open)
    FOLLOW_UP = "follow_up"                  # queued: the next batch, after this run or this line
    HOLD_FOR_VOICE = "hold_for_voice"        # stop the run and wait for that voice (same device, inside the window)
    ACTIONS_WAIT = "actions_wait"            # the run's actions wait while the person speaks
    SILENCE = "silence"                      # stop our voice, local and immediate
    CANCEL_RUN = "cancel_run"                # drop the run (never a task)
    BY_ID = "by_id"                          # goes to its ledger item by id
    SAY_OWED = "say_owed"                    # say the next line owed, as it is, by voice
    WAIT_BEHIND_VOICE = "wait_behind_voice"  # note the open voice: a text that arrives after it waits behind it
    RESUME_LINE = "resume_line"              # a barge-in with no word: say the rest of the line it cut, once


class ItemKind(_Str):
    """The two items the ledger keeps. Tasks, their questions, what is owed, mandates and receipts have their own rows
    and their own writer outside this package: the conversation refers to them by id."""
    REQUEST = "request"
    EFFECT = "effect"


class EffectClass(_Str):
    """What a tool does to the world, as the host derives it from the tool's declared act (`ToolSpec.act`, an event
    type of the host's vocabulary): only reads, writes here, or something that leaves. The package names no act."""
    READ = "read"
    WRITE = "write"
    LEAVES = "leaves"


@dataclass(frozen=True)
class Evidence:
    """One fact a tool returned, structured enough for a numeric claim to be matched against it."""
    id: str
    source: str
    entity: str = ""
    period: str = ""
    metric: str = ""
    direction: str = ""
    value: float | None = None
    #: a TEXT evidence (a read with no structure): the figures its text carries, read by the host's adapter
    numbers: tuple[float, ...] = ()

    def to_json(self) -> dict:
        return {**{k: getattr(self, k) for k in ("id", "source", "entity", "period", "metric", "direction", "value")},
                "numbers": list(self.numbers)}

    @classmethod
    def from_json(cls, d: dict) -> "Evidence":
        return cls(**{k: d.get(k, "" if k != "value" else None) for k in
                      ("id", "source", "entity", "period", "metric", "direction", "value")},
                   numbers=tuple(float(n) for n in d.get("numbers") or ()))


class Ids:
    """Ids with a prefix and a counter: deterministic (a replay mints the same ids), unique within one manager.
    The `space` keeps two managers (two processes, two tests) from colliding when they share a store."""

    def __init__(self, space: str = "") -> None:
        self._n = 0
        self._space = space

    def new(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}_{self._space}{self._n:06d}"
