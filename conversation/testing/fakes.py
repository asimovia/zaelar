"""Recording doubles for the ports: tools that record every effect, a mouth that acks, a clock that moves when told,
telemetry into a list, a memory that has nothing. Deterministic: no wall clock, no randomness, no I/O."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Callable

from conversation.ports import Block, ToolResult, ToolSpec
from conversation.types import EffectClass, Evidence


class FakeClock:
    def __init__(self, t0_ms: int = 1_800_000_000_000) -> None:
        self.wall0, self.mono = t0_ms, 0

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
    """A catalogue shaped like the engine's: core reads, a local write, a send, a destructive act, the task tools."""
    send = {"recipient": "to", "channel": "via", "content": "text"}
    return [ToolSpec("search", core=True), ToolSpec("market_data", core=True), ToolSpec("discover_tools", core=True),
            ToolSpec("agenda_add", effect_class=EffectClass.LOCAL_WRITE),
            ToolSpec("send_message", effect_class=EffectClass.EGRESS, binding=send),
            ToolSpec("delete_all", effect_class=EffectClass.DESTRUCTIVE),
            ToolSpec("task.start", effect_class=EffectClass.LOCAL_WRITE, hands_off=True),
            ToolSpec("task.cancel", effect_class=EffectClass.LOCAL_WRITE)]


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


def evidence(eid: str, entity: str, period: str, metric: str, direction: str, value: float) -> Evidence:
    return Evidence(eid, "market", entity, period, metric, direction, value)


@dataclass
class AckingMouth:
    """Says at once; `ack` (set by the harness) receives the acks, `played` decides how much was heard."""
    ack: Callable | None = None
    playback: Callable | None = None           # (endpoint, t) → the device reports it is playing our line
    heard_all: bool = True
    orders: list = field(default_factory=list)
    calls: list = field(default_factory=list)

    async def say(self, order) -> None:
        from conversation.mouth import PlayoutAck, SayEnded, SayStarted
        self.orders.append(order)
        if self.playback is not None and order.endpoint and "voice" in order.channels:
            self.playback(order.endpoint)
        if self.ack is not None:
            self.ack(SayStarted(order.say_id, 0))
            if self.heard_all and order.endpoint:
                self.ack(PlayoutAck(order.say_id, order.endpoint, len(order.text), 0))
            self.ack(SayEnded(order.say_id, "played", None, 0, order.endpoint))

    def duck(self, endpoint: str) -> None:
        self.calls.append(("duck", endpoint))

    def unduck(self, endpoint: str) -> None:
        self.calls.append(("unduck", endpoint))

    def stop(self, endpoint, *, reason: str) -> None:
        self.calls.append(("stop", endpoint, reason))


class NoMemory:
    async def state_blocks(self, account, *, budget_tokens):
        return []

    async def screen(self, account, endpoint):
        return Block("", "")

    async def recall(self, account, query, *, k):
        return []
