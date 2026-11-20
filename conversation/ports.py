"""The ports: everything outside the package comes in through one of these seven, and only through them (§4).

Thread rule: no port may block the loop. Ports that do I/O are `async`; an adapter that is synchronous underneath
wraps itself in `asyncio.to_thread` — in the ADAPTER, never in this package. The manager times every port call and
emits `conv_run/port_slow` past `Config.port_budget_ms`.

`Store` is the ledger and the durable inbox in one (I1 and the one-row-per-operation reservation need ONE transaction for «dequeue + item + effect
reservation + spent handle»). It is synchronous on purpose: a local transaction, measured like the rest.
Workers are not a port: they come in as `worker.update` envelopes and go out as one more tool (`task.start`).
"""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Protocol

from conversation.types import EffectClass, Evidence

# ── the clock ────────────────────────────────────────────────────────────────────────────────────────────────────


class Clock(Protocol):
    def now_ms(self) -> int: ...                        # wall clock
    def mono_ms(self) -> int: ...                       # monotonic, for deadlines
    async def sleep_until(self, mono_ms: int) -> None: ...
    # optional: `zone(now_ms) -> (offset_min, name)`, the person's local time at that instant; without it, UTC


class Telemetry(Protocol):
    def emit(self, kind: str, label: str, payload: dict) -> None: ...   # never raises, never blocks


# ── the model ────────────────────────────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Turn:
    """One line of the conversation as the model sees it. Ours is cut to what was heard."""
    role: str            # "user" | "agent"
    channel: str
    text: str
    ref: str = ""        # intervention id (theirs) or say id (ours)


@dataclass(frozen=True)
class PromptParts:
    prefix: str                     # stable between turns (cache)
    state: str                      # NOW · OPEN · the host's blocks
    conversation: tuple[Turn, ...]
    input: str                      # the batch, each entry with its id, channel and state
    steps: tuple = ()               # (ToolCall, result) pairs of this run, fed back to the next model call
    channel: str = ""               # the batch's: "voice" when it holds his voice, else "text" (the host sizes the reply)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    schema: dict = field(default_factory=dict)
    #: the event type the tool's act is, in the host's vocabulary — opaque here; the host derives `effect_class` from
    #: it (a tool with no act is a read only if all it declares is reading). Undeclared, the gateway refuses the tool:
    #: the one door out is never open by default.
    act: str = ""
    effect_class: EffectClass | None = None
    core: bool = False              # never filtered out (I7)
    about: str = ""                 # what it is FOR, in the host's words: the model reads it, the package never does


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    args: dict


@dataclass(frozen=True)
class Command:
    """A structured order of the model: reply, no_reply, task.start/continue/answer/cancel. The host's adapter may
    attach `unclaimed_figures` (how many figures of the text carry no claim, counted over OUR output): a measure the
    `command` event carries, never read for a decision."""
    name: str
    args: dict


UNCLAIMED = "unclaimed_figures"


@dataclass(frozen=True)
class Done:
    usage: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Failed:
    reason: str
    whose: str = "provider"   # "provider" | "ours"


ModelEvent = TextDelta | ToolCall | Command | Done | Failed


#: the `model_id` that asks the port for its stand-in: a provider other than the one the account's runs use. A run
#: asks for it once, when its deadline passed before the model said anything (nothing to undo, nothing fired).
RELAY = "relay"


class Model(Protocol):
    def stream(self, prompt: PromptParts, tools: list[ToolSpec], *, run_id: str,
               model_id: str) -> AsyncIterator[ModelEvent]: ...


# ── tools ────────────────────────────────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ToolResult:
    status: str                         # "ok" | "rejected" | "failed" | "unknown"
    data: Any = None
    evidence: tuple[Evidence, ...] = ()
    receipt: dict | None = None


class Tools(Protocol):
    def catalog(self) -> list[ToolSpec]: ...            # the ONE list of tools
    async def call(self, name: str, args: dict, *, effect_id: str | None, idempotency_key: str | None,
                   deadline_mono_ms: int) -> ToolResult: ...


class Tasks(Protocol):
    """The host's tasks, by id. A button that cancels one is handled here; the task's row and its writer are the
    host's. Without this port a `cancel_task` control has no handler and is refused when accepted."""
    def cancel(self, account: str, task_id: str) -> bool: ...


class Route(Protocol):
    """The host's doors that already decide whose his words are when something of his is OPEN — a process running or
    waiting on his answer (plan F2 §3), in their own order. `take` answers the line to say when one took them (""
    for a take with nothing to say), or None when nobody did and the model answers. With nothing open it costs nothing."""
    async def take(self, account: str, text: str) -> str | None: ...


class Shortcut(Protocol):
    """A phrase of his the host already KNOWS, verbatim (V2-942 A2): one exact whole-utterance hit runs its direct act
    before any model, in under a millisecond. `take` answers the line to say when it ran ("" for none), or None — no
    exact hit, or the act could not run with certainty — and the batch goes on as if it did not exist."""
    async def take(self, account: str, text: str) -> str | None: ...


class Stops(Protocol):
    """The host's hands for a stop the MODEL ordered (plan v3.2 §3): what each scope stops beyond our voice — what is
    playing (`media`, `all`), his tasks (`all`, cancelled and resumable), the attention window. Local and immediate;
    it writes nothing outside and deletes nothing."""
    def stop(self, scope: str, endpoint: str | None) -> None: ...


class Prefs(Protocol):
    """The operator's standing preferences, read when a decision needs one — so a change applies to the next one, with
    no restart. The host reads its rules; without this port every preference is its default."""
    def __call__(self, key: str, default: Any) -> Any: ...


class Words(Protocol):
    """The host's fixed lines in the person's language, for the few facts the manager says itself, as they are (a
    figure it could not confirm). `near`: what the line answers (his words in the batch) — the host says it in THAT
    language when it can tell. An empty line means the host has none: the manager then says nothing."""
    def line(self, key: str, near: str = "") -> str: ...


class Record(Protocol):
    """The host's record of the conversation («what did I tell you yesterday»): one pair per answered batch, handed
    over at least once (`ref` names the run, so a repeat can be told apart; `channel`, how his words came: `voice` or
    `typed`)."""
    def pair(self, account: str, said: str, answered: str, *, ref: str, channel: str = "voice") -> None: ...


# ── memory (read only) ───────────────────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Block:
    title: str
    text: str
    ref: str = ""


class Memory(Protocol):
    async def state_blocks(self, account: str, *, budget_tokens: int) -> list[Block]: ...
    async def screen(self, account: str, endpoint: str | None) -> Block: ...
    async def recall(self, account: str, query: str, *, k: int) -> list[Block]: ...


# ── the mouth ────────────────────────────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SayOrder:
    say_id: str
    run_id: str
    request_id: str
    text: str
    channels: frozenset[str]          # {"voice", "text"}
    endpoint: str | None
    lang: str = ""
    notice_key: str | None = None     # this line says a line owed (`Owed`): its outcome goes back to that ledger


@dataclass(frozen=True)
class OwedLine:
    """A line the engine owes the person, already worded for them (a worker's result, a contact's message, a
    reminder, the line that says a run failed), held for the voice by its own ledger."""
    key: str
    text: str
    task_id: str | None = None


class Owed(Protocol):
    """What the engine owes the person lives in ITS ledger, never copied into the inbox: the manager asks for the next
    line held for the voice when it is free and nobody speaks, says it as it is (no model), and reports back. A claim
    has a deadline in that ledger: a line never said goes back to `owed`, and from there to its other ways (a push,
    the next screen). One consumer at a time."""
    def next(self, account: str) -> OwedLine | None: ...          # a line held for the voice, if any
    def settle(self, key: str) -> None: ...                      # it sounded: spoken
    def release(self, key: str) -> None: ...                     # it did not: back to owed, for its other ways
    def owe(self, account: str, key: str, reason: str, *, voice: bool = True) -> None: ...   # the manager owes a
    # line (a failure): the host words it in the person's language; `voice` False: on the screen only, never said


class Mouth(Protocol):
    """Two verbs: say a line, stop our voice. Cutting our voice when the person talks over it is the voice process's
    own local rule, not an order of this package."""
    async def say(self, order: SayOrder) -> None: ...
    def stop(self, endpoint: str | None, *, reason: str) -> None: ...   # local and immediate


# Acks come back to the manager as signals (`mouth/say.py`): SayStarted, SayEnded (with what was heard and its source).


# ── the store: the ledger + the durable inbox, ONE writer per account ────────────────────────────────────────────


class StaleEpoch(RuntimeError):
    """The lease is not the account's current one: another writer took over. Nothing was written."""


class Conflict(RuntimeError):
    """A conditional write found another value than the one expected: someone else moved the row first."""


@dataclass(frozen=True)
class Lease:
    account: str
    owner: str
    epoch: int


class Tx(Protocol):
    """One transaction. Every write is idempotent by id; `cas` and `insert_unique` are the two atomic primitives the
    invariants are built on (a seal against a substitution; one effect per (mandate, trigger, operation)). A
    transaction inside another is refused at once, loudly: the inner one would be lost at the outer commit.

    `scan(table, states)` reads only the rows whose `state` is one of `states` — what is in course — so a reader that
    sweeps pays for what is live, not for the account's history. Nothing is moved or archived to keep a table small:
    what is done stays, and the host's hygiene deletes it by age."""

    def get(self, table: str, key: str) -> dict | None: ...
    def put(self, table: str, key: str, row: dict) -> None: ...
    def cas(self, table: str, key: str, field_name: str, expect: Any, new: dict) -> bool: ...
    def insert_unique(self, table: str, key: str, row: dict, unique: str) -> tuple[dict, bool]: ...
    def scan(self, table: str, states: tuple[str, ...] | None = None) -> list[tuple[str, dict]]: ...
    def next_seq(self, name: str) -> int: ...


class Snapshot(Protocol):
    def get(self, table: str, key: str) -> dict | None: ...
    def scan(self, table: str, states: tuple[str, ...] | None = None) -> list[tuple[str, dict]]: ...
    def recent(self, table: str, n: int) -> list[tuple[str, dict]]: ...   # the newest n, newest first


class Store(Protocol):
    def acquire(self, account: str, owner: str) -> Lease: ...           # a new epoch for this owner (fencing)
    def current(self, account: str) -> Lease | None: ...
    def tx(self, lease: Lease) -> AbstractContextManager[Tx]: ...      # raises StaleEpoch; checked again at commit
    def check(self, lease: Lease) -> None: ...                         # raises StaleEpoch; the last controllable point
    def snapshot(self, account: str) -> Snapshot: ...                  # every row: audits, recovery, tests
    #: what a run reads — by state and by the newest rows, each read bounded: its cost follows what is in course and
    #: the window of the conversation, never the account's history
    def view(self, account: str) -> Snapshot: ...
    def close(self) -> None: ...
