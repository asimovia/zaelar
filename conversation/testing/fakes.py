"""Recording doubles for the ports: tools that record every effect, a mouth that acks, a clock that moves when told,
telemetry into a list, a memory that has nothing. Deterministic: no wall clock, no randomness, no I/O."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Callable

from conversation.ports import Block, OwedLine, ToolResult, ToolSpec
from conversation.types import EffectClass, Evidence


class FakeClock:
    def __init__(self, t0_ms: int = 1_800_000_000_000, zone: tuple[int, str] = (0, "UTC")) -> None:
        self.wall0, self.mono, self._zone = t0_ms, 0, zone

    def zone(self, now_ms: int) -> tuple[int, str]:
        return self._zone

    def now_ms(self) -> int:
        return self.wall0 + self.mono

    def mono_ms(self) -> int:
        return self.mono

    def advance(self, ms: int) -> None:
        self.mono += ms

    async def sleep_until(self, mono_ms: int) -> None:
        await asyncio.sleep(0)                 # yields like a real sleep: a timer task never starves the loop
        self.mono = max(self.mono, mono_ms)


class ListTelemetry:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict]] = []

    def emit(self, kind: str, label: str, payload: dict) -> None:
        self.events.append((kind, label, payload))

    def labels(self, kind: str | None = None) -> list[str]:
        return [f"{k}/{lab}" for k, lab, _ in self.events if kind is None or k == kind]


def catalog() -> list[ToolSpec]:
    """A catalogue shaped like the engine's: core reads, a write here, a send that leaves, a destructive act, the
    task tools — each with the act it declares and the class a host would derive from it (tokens, not the engine's
    names)."""
    read = EffectClass.READ
    return [ToolSpec("search", effect_class=read, core=True), ToolSpec("market_data", effect_class=read, core=True),
            ToolSpec("discover_tools", effect_class=read, core=True),
            ToolSpec("agenda_add", act="a1.add", effect_class=EffectClass.WRITE),
            ToolSpec("send_message", act="a2.send", effect_class=EffectClass.LEAVES),
            ToolSpec("delete_all", act="a3.delete", effect_class=EffectClass.WRITE),
            ToolSpec("task.start", act="a4.start", effect_class=EffectClass.WRITE),
            ToolSpec("task.cancel", act="a4.cancel", effect_class=EffectClass.WRITE)]


@dataclass
class RecordingTools:
    specs: list[ToolSpec] = field(default_factory=catalog)
    answers: dict[str, ToolResult] = field(default_factory=dict)
    calls: list[tuple[str, dict, str | None]] = field(default_factory=list)
    before: Callable[[str], None] | None = None
    delay_s: float = 0.0                       # real time a call takes (deadlines are wall clock)
    raises: dict = field(default_factory=dict)  # tool name → exception the adapter raises

    def catalog(self) -> list[ToolSpec]:
        return list(self.specs)

    async def call(self, name, args, *, effect_id, idempotency_key, deadline_mono_ms) -> ToolResult:
        if self.before is not None:
            self.before(name)
        self.calls.append((name, dict(args), effect_id))
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        if name in self.raises:
            raise self.raises[name]
        return self.answers.get(name, ToolResult("ok", data={"tool": name},
                                                 receipt={"delivered": True} if effect_id else None))


@dataclass
class FakeTasks:
    """The host's tasks, by id: records what a button cancelled."""
    cancelled: list = field(default_factory=list)

    def cancel(self, account: str, task_id: str) -> bool:
        self.cancelled.append(task_id)
        return True


def evidence(eid: str, entity: str, period: str, metric: str, direction: str, value: float) -> Evidence:
    return Evidence(eid, "market", entity, period, metric, direction, value)


@dataclass
class AckingMouth:
    """Says at once; `ack` (set by the harness) receives the acks; `heard_all` decides whether the voice process
    counted what it spoke (`agent_estimate`) or the count was lost (`unknown`)."""
    ack: Callable | None = None
    playback: Callable | None = None           # (endpoint, t) → the device reports it is playing our line
    heard_all: bool = True
    orders: list = field(default_factory=list)
    calls: list = field(default_factory=list)

    async def say(self, order) -> None:
        from conversation.mouth import SayEnded, SayStarted
        self.orders.append(order)
        if self.playback is not None and order.endpoint and "voice" in order.channels:
            self.playback(order.endpoint)
        if self.ack is not None:
            self.ack(SayStarted(order.say_id, 0))
            heard = self.heard_all and bool(order.endpoint)
            self.ack(SayEnded(order.say_id, "played", len(order.text) if heard else None, 0, order.endpoint,
                              "agent_estimate" if heard else "unknown"))

    def stop(self, endpoint, *, reason: str) -> None:
        self.calls.append(("stop", endpoint, reason))


class NoMemory:
    async def state_blocks(self, account, *, budget_tokens):
        return []

    async def screen(self, account, endpoint):
        return Block("", "")

    async def recall(self, account, query, *, k):
        return []


class FakeOwed:
    """The ledger of what is owed, as the host's `notices` keeps it: a row is `owed`, `claimed` for the voice (with a
    deadline), `spoken`, or gone its other ways. `add` puts a line held for the voice; `next` hands each claimed line
    to ONE consumer at a time; a claim past its deadline goes back to `owed` (`expire`, the pulse's job)."""

    def __init__(self, claim_ms: int = 60_000) -> None:
        self.rows: dict[str, dict] = {}
        self.claim_ms = claim_ms
        self.handed: list[str] = []

    def add(self, key: str, text: str, now: int = 0, task_id: str | None = None) -> None:
        self.rows.setdefault(key, {"state": "claimed", "text": text, "task_id": task_id, "due": now + self.claim_ms,
                                   "out": False})

    def next(self, account: str) -> OwedLine | None:
        for key, r in self.rows.items():
            if r["state"] == "claimed" and not r["out"]:
                r["out"] = True
                self.handed.append(key)
                return OwedLine(key, r["text"], r["task_id"])
        return None

    def settle(self, key: str) -> None:
        if self.rows.get(key, {}).get("state") == "claimed":
            self.rows[key].update(state="spoken", out=False)

    def release(self, key: str) -> None:
        if self.rows.get(key, {}).get("state") == "claimed":
            self.rows[key].update(state="owed", out=False)

    def owe(self, account: str, key: str, reason: str) -> None:
        self.add(key, reason)

    def expire(self, now: int) -> list[str]:
        gone = [k for k, r in self.rows.items() if r["state"] == "claimed" and now >= r["due"]]
        for k in gone:
            self.rows[k].update(state="owed", out=False)
        return gone


class FixedWords:
    """The host's fixed lines, as tokens: a test sees which one was said, never a language's words."""
    LINES = (("mute_lines", "w_lost"), ("unverified_fact", "w_unverified"))

    def line(self, key: str, near: str = "") -> str:
        return next((text for k, text in self.LINES if k == key), "")
