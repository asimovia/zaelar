"""The ports: everything outside the package comes in through one of these seven, and only through them (§4).

Thread rule: no port may block the loop. Ports that do I/O are `async`; an adapter that is synchronous underneath
wraps itself in `asyncio.to_thread` — in the ADAPTER, never in this package. The manager times every port call and
emits `conv_run/port_slow` past `Config.port_budget_ms`.

`Store` is the ledger and the durable inbox in one (I1/N3 need ONE transaction for «dequeue + item + effect
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
    state: str                      # NOW · OPEN · TO_TELL
    conversation: tuple[Turn, ...]
    input: str                      # the batch, each entry with its id, channel and state
    steps: tuple = ()               # (ToolCall, result) pairs of this run, fed back to the next model call


@dataclass(frozen=True)
class ToolSpec:
    name: str
    schema: dict = field(default_factory=dict)
    effect_class: EffectClass = EffectClass.READ
    core: bool = False              # never filtered out (I7)
    #: which arguments are the recipient, the channel and the content — so a handle or a delegation binds an effect
    #: without the gateway naming any tool (plan §15 E2)
    binding: dict = field(default_factory=dict)
    hands_off: bool = False         # the work goes on without the run (a task started): its request is handed off


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
    """A structured order of the model: reply, no_reply, task.start/continue/answer/cancel."""
    name: str
    args: dict


@dataclass(frozen=True)
class Done:
    usage: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Failed:
    reason: str
    whose: str = "provider"   # "provider" | "ours"


ModelEvent = TextDelta | ToolCall | Command | Done | Failed


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
    presents: str | None = None       # the handle this line presents (a question that needs a yes)


class Mouth(Protocol):
    async def say(self, order: SayOrder) -> None: ...
    def duck(self, endpoint: str) -> None: ...          # reversible, immediate, cheap
    def unduck(self, endpoint: str) -> None: ...
    def stop(self, endpoint: str | None, *, reason: str) -> None: ...   # local and immediate


# Acks come back to the manager as signals (`mouth/say.py`): SayStarted, PlayoutAck, SayEnded.


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
    invariants are built on (seal vs reopen; one effect per (grant, trigger, operation))."""

    def get(self, table: str, key: str) -> dict | None: ...
    def put(self, table: str, key: str, row: dict) -> None: ...
    def cas(self, table: str, key: str, field_name: str, expect: Any, new: dict) -> bool: ...
    def insert_unique(self, table: str, key: str, row: dict, unique: str) -> tuple[dict, bool]: ...
    def scan(self, table: str) -> list[tuple[str, dict]]: ...
    def next_seq(self, name: str) -> int: ...


class Snapshot(Protocol):
    def get(self, table: str, key: str) -> dict | None: ...
    def scan(self, table: str) -> list[tuple[str, dict]]: ...


class Store(Protocol):
    def acquire(self, account: str, owner: str) -> Lease: ...           # a new epoch for this owner (fencing)
    def current(self, account: str) -> Lease | None: ...
    def tx(self, lease: Lease) -> AbstractContextManager[Tx]: ...      # raises StaleEpoch; checked again at commit
    def check(self, lease: Lease) -> None: ...                         # raises StaleEpoch; the last controllable point
    def snapshot(self, account: str) -> Snapshot: ...                  # a coherent read for the composer
    def close(self) -> None: ...
