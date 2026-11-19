"""A gateway over a real store, with a small tool catalogue and a recording `Tools` double. Names are tokens."""
from __future__ import annotations

from conversation import envelopes as E
from conversation.config import Config
from conversation.gateway.authority import RunCtx
from conversation.gateway import seal as S
from conversation.gateway.outbox import Gateway
from conversation.inbox import Inbox
from conversation.ledger import Book
from conversation.ports import ToolCall, ToolResult, ToolSpec
from conversation.telemetry import Emitter
from conversation.types import Channel, ControlOp, EffectClass, EnvelopeKind, Ids, WorkerUpdate

ACCT = "acct-test"
SEND = {"recipient": "to", "channel": "via", "content": "text"}
SPECS = {
    "search": ToolSpec("search", core=True),
    "agenda_add": ToolSpec("agenda_add", effect_class=EffectClass.LOCAL_WRITE),
    "send_message": ToolSpec("send_message", effect_class=EffectClass.EGRESS, binding=SEND),
    "delete_all": ToolSpec("delete_all", effect_class=EffectClass.DESTRUCTIVE),
    "pay": ToolSpec("pay", effect_class=EffectClass.PAYMENT, binding={"recipient": "to"}),
}


class RecordingTools:
    def __init__(self, status: str = "ok", raise_exc: Exception | None = None) -> None:
        self.calls: list[tuple[str, dict, str | None]] = []
        self.status, self.raise_exc = status, raise_exc

    def catalog(self):
        return list(SPECS.values())

    async def call(self, name, args, *, effect_id, idempotency_key, deadline_mono_ms):
        self.calls.append((name, dict(args), effect_id))
        if self.raise_exc is not None:
            raise self.raise_exc
        return ToolResult(self.status, receipt={"delivered": True} if self.status == "ok" else None)


class Kit:
    def __init__(self, store, clock, telemetry, config: Config | None = None, owner: str = "test") -> None:
        self.store, self.clock, self.tel = store, clock, telemetry
        self.cfg = config or Config()
        self.lease = store.acquire(ACCT, owner)
        em = Emitter(telemetry, clock, ACCT)
        self.ids = Ids(owner[:1])
        self.book = Book(store, lambda: self.lease, ACCT, em, clock)
        self.gw = Gateway(self.book, ACCT, self.cfg, em, clock, self.ids, lambda: SPECS)
        self.inbox = Inbox(store, lambda: self.lease, ACCT, self.cfg, em, self.ids)
        self.n = 0

    def utterance(self, iv: str, text: str = "w0001", t: int = 0, closed: bool = True) -> E.Envelope:
        env = E.make(EnvelopeKind.USER_UTTERANCE, E.UtteranceBody(iv, text), producer="ear:d1",
                     producer_id=f"{iv}:closed", account=ACCT, onset_ms=t, sealed_ms=t + 500, endpoint="d1",
                     refs=E.Refs(intervention_id=iv))
        env = self._accept(env)
        if closed:
            with self.store.tx(self.lease) as tx:
                S.note(tx, iv, "closed", t + 500)
        return env

    def text(self, iv: str, text: str = "w0002", t: int = 0) -> E.Envelope:
        env = E.make(EnvelopeKind.USER_TEXT, E.TextBody(iv, text), producer="chat:d2", producer_id=iv, account=ACCT,
                     onset_ms=t, sealed_ms=t, channel=Channel.TEXT, endpoint="d2",
                     refs=E.Refs(intervention_id=iv))
        env = self._accept(env)
        with self.store.tx(self.lease) as tx:
            S.note(tx, iv, "closed", t)
        return env

    def contact(self, t: int = 0) -> E.Envelope:
        self.n += 1
        return self._accept(E.make(EnvelopeKind.CONTACT_MESSAGE, E.ContactBody("th1", "c-ref-1", "w0009"),
                                   producer="connector:chat", producer_id=f"m{self.n}", account=ACCT, onset_ms=t,
                                   sealed_ms=t))

    def worker(self, t: int = 0) -> E.Envelope:
        self.n += 1
        return self._accept(E.make(EnvelopeKind.WORKER_UPDATE, E.WorkerBody("t1", WorkerUpdate.RESULT, "w0010"),
                                   producer="worker:t1", producer_id=f"r{self.n}", account=ACCT, onset_ms=t,
                                   sealed_ms=t))

    def control(self, op: ControlOp, *, handle: str | None = None, gesture: bool = True, scope: dict | None = None,
                endpoint: str = "d1", channel: Channel = Channel.BUTTON) -> E.Envelope:
        self.n += 1
        return self._accept(E.make(EnvelopeKind.USER_CONTROL, E.ControlBody(op, handle_id=handle, gesture=gesture,
                                                                           scope=scope),
                                   producer=f"button:{endpoint}", producer_id=f"k{self.n}", account=ACCT,
                                   onset_ms=0, sealed_ms=0, channel=channel, endpoint=endpoint))

    def _accept(self, env: E.Envelope) -> E.Envelope:
        return self.inbox.accept(env, self.clock.mono_ms()).envelope

    def ctx(self, *envs: E.Envelope, run: str = "run1", endpoint: str = "d1") -> RunCtx:
        return RunCtx(run, f"req-{run}", {e.id: e for e in envs}, endpoint)

    @staticmethod
    def send(to: str = "c1", via: str = "chat", text: str = "w0100", **kw) -> ToolCall:
        return ToolCall("call-1", "send_message", {"to": to, "via": via, "text": text, **kw})

    def items(self, kind: str | None = None) -> list[dict]:
        return [r for _k, r in self.store.snapshot(ACCT).scan("items") if kind is None or r["kind"] == kind]

    def flags(self) -> dict:
        return self.store.snapshot(ACCT).get("flags", "write_disabled") or {}
