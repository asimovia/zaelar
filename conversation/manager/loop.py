"""The manager of one account: ONE writer (a lease on the store, I5), ONE run at a time, the policy table applied to
everything that arrives (§6.3). Idle → Collecting → Running (unclaimed | claimed) → Speaking → Idle.

`hear(signal)` feeds the ear; `give(envelope)` takes what other producers send (workers, connectors, reminders,
buttons); `ack(...)` takes the mouth's acknowledgements; `pump()` runs what is ready until nothing is. The control lane
(onset, stop, acks) never waits for a run. A new input during a run is applied at the run's next checkpoint:
SUPERSEDE replaces the RUN (never the request, N1), FOLLOW_UP queues, CANCEL_RUN drops it, SILENCE stops our voice.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from conversation import envelopes as E
from conversation.config import Config
from conversation.ear import Ear
from conversation.ear import signals as S
from conversation.gateway import RunCtx, dispatch
from conversation.gateway import seal as SEAL
from conversation.gateway.outbox import Gateway
from conversation.inbox import Inbox
from conversation.inbox.mailbox import apply_control
from conversation.ledger import Book
from conversation.manager import policy, run
from conversation.manager.focus import Focus
from conversation.mouth import Device, Painted, PlayoutAck, SayEnded, SayStarted, Speaker
from conversation.ports import Clock, Memory, Model, Mouth, Store, Telemetry, Tools
from conversation.telemetry import Emitter
from conversation.types import ControlOp, EnvelopeKind, Ids, IvState, MgrState, Op


@dataclass
class Running:
    run_id: str
    batch_ids: tuple[str, ...]
    requests: tuple[str, ...]
    ctx: RunCtx
    claimed: bool = False
    interrupt: str | None = None          # superseded · cancelled
    actions_held: bool = False
    presents: str | None = None
    said: list = field(default_factory=list)


class Conversation:
    def __init__(self, *, account: str, owner: str, model: Model, tools: Tools, store: Store, memory: Memory | None,
                 clock: Clock, mouth: Mouth, telemetry: Telemetry, config: Config | None = None, prefix: str = "",
                 ids: Ids | None = None) -> None:
        self.account, self.cfg, self.prefix = account, config or Config(), prefix
        self.model, self.tools, self.store, self.memory, self.clock = model, tools, store, memory, clock
        self.lease = store.acquire(account, owner)
        self.em = Emitter(telemetry, clock, account, epoch=lambda: self.lease.epoch)
        self.ids = ids or Ids()
        lease = lambda: self.lease  # noqa: E731
        self.ear = Ear(account, self.cfg, self.em, self.ids)
        self.inbox = Inbox(store, lease, account, self.cfg, self.em, self.ids)
        self.book = Book(store, lease, account, self.em, clock)
        self.gw = Gateway(self.book, account, self.cfg, self.em, clock, self.ids,
                          lambda: {t.name: t for t in tools.catalog()})
        self.focus = Focus()
        self.speaker = Speaker(store, lease, mouth, self.em, clock, self.ids, on_presented=self._presented)
        self.devices: dict[str, Device] = {}
        self.state = MgrState.IDLE
        self.current: Running | None = None
        self.speaking_on: set[str] = set()

    # ── in ──────────────────────────────────────────────────────────────────────────────────────────────────────

    def hear(self, sig: S.Signal) -> None:
        for out in self.ear.feed(sig):
            if isinstance(out, S.Onset):
                self._onset(out)
            else:
                self.give(out)

    def give(self, env: E.Envelope) -> None:
        now = self.clock.now_ms()
        lost = self._note_voice(env, now)
        adm = self.inbox.accept(env, now)
        if adm.envelope is None or lost:          # a reopen that lost to the seal is an amendment, not a reopen
            return
        env = adm.envelope
        ops = policy.decide(env, self.state, claimed=bool(self.current and self.current.claimed),
                            person_speaking=bool(self.speaking_on))
        self._apply(env, ops)

    def _note_voice(self, env: E.Envelope, now: int) -> bool:
        """The intervention's phase in the store: what the gateway's seal and the reopen race on."""
        k, b = env.kind, env.body
        lost_to_seal = False
        with self.store.tx(self.lease) as tx:
            if k is EnvelopeKind.USER_UTTERANCE:
                SEAL.note(tx, b.intervention_id, b.revision, "closed", now)
            elif k is EnvelopeKind.USER_TEXT:
                SEAL.note(tx, b.intervention_id, 1, "closed", now)
            elif k is EnvelopeKind.INTERVENTION_STATE and b.state is IvState.INCOMPLETE:
                SEAL.note(tx, b.intervention_id, b.revision, "incomplete", now)
            elif E.is_reopen(env):
                lost_to_seal = not SEAL.reopen(tx, b.intervention_id, b.revision - 1, now)
        if lost_to_seal:            # the seal won the race: what was heard since becomes an amendment (I3)
            for out in self.ear.feed(S.Sealed(b.intervention_id, b.revision - 1)):
                if isinstance(out, E.Envelope):
                    self.inbox.accept(out, now)
        if k in (EnvelopeKind.USER_UTTERANCE, EnvelopeKind.INTERVENTION_STATE) and env.endpoint:
            if k is EnvelopeKind.USER_UTTERANCE or b.state in (IvState.INCOMPLETE, IvState.DISCARDED):
                self._voice_done(env.endpoint)
        return lost_to_seal

    def _onset(self, o: S.Onset) -> None:
        self.speaking_on.add(o.endpoint)
        self.gw.note_onset(o.endpoint, o.t_ms)
        for op in policy.decide(o, self.state, claimed=bool(self.current and self.current.claimed)):
            if op is Op.FIX_FOCUS:
                self.focus.onset(o.endpoint)
            elif op is Op.DUCK:
                self.speaker.duck(o.endpoint)
            elif op is Op.HOLD_ACTIONS and self.current is not None:
                self.current.actions_held = True
                dispatch.hold(self.gw, self.ids.new("hold"), o.endpoint, o.t_ms, "onset")

    def _voice_done(self, endpoint: str) -> None:
        if endpoint in self.speaking_on:
            self.speaking_on.discard(endpoint)
            self.focus.done_speaking(endpoint)
            if self.state is MgrState.SPEAKING:
                self.speaker.unduck(endpoint)
        if self.current is not None and not self.speaking_on:
            self.current.actions_held = False

    def _apply(self, env: E.Envelope, ops: tuple[Op, ...]) -> None:
        for op in ops:
            if op is Op.SILENCE:
                self.speaker.stop(None, "new_input" if env.kind is not EnvelopeKind.USER_CONTROL else "stop",
                                  self.clock.mono_ms())
            elif op in (Op.SUPERSEDE, Op.AT_CHECKPOINT) and self.current is not None and not self.current.claimed:
                self.current.interrupt = "superseded"
            elif op is Op.CANCEL_RUN and self.current is not None:
                self.current.interrupt = "cancelled"
            elif op is Op.BY_ID:
                self._by_id(env)
        if env.kind is EnvelopeKind.USER_CONTROL and env.body.op is ControlOp.STOP:
            self.inbox.applied(env.id, self.clock.now_ms())

    def _by_id(self, env: E.Envelope) -> None:
        op = env.body.op
        if op is ControlOp.CONFIRM:
            self.gw.confirm(env)
        elif op is ControlOp.DECLINE:
            self.gw.decline(env)
        elif op is ControlOp.DELEGATE:
            self.gw.delegate(env)
        elif op is ControlOp.CANCEL_TASK:
            with self.book.tx() as b:
                apply_control(b.tx, env.id, b.now)
                task = b.get(env.body.task_id or "")
                if task is not None and task["state"] in ("started", "running", "waiting"):
                    b.move(task["id"], "cancelled", cause={"kind": "envelope", "ref": env.id})

    def ack(self, sig: SayStarted | PlayoutAck | Painted | SayEnded) -> None:
        self.speaker.ack(sig)
        if isinstance(sig, SayEnded) and self.state is MgrState.SPEAKING:
            self.state = MgrState.IDLE

    def sealed(self, iv: str, rev: int) -> None:
        """Tell the ear a revision is sealed: voice that follows amends it, never reopens it (I3)."""
        for out in self.ear.feed(S.Sealed(iv, rev)):
            if isinstance(out, E.Envelope):
                self.give(out)

    def _presented(self, handle: str, endpoint: str | None) -> None:
        if handle:
            self.gw.present(handle, endpoint)
            self.focus.presented(handle, endpoint, self.clock.now_ms())

    def device(self, endpoint: str, **state) -> None:
        self.devices[endpoint] = Device(endpoint, **state)

    # ── run what is ready ───────────────────────────────────────────────────────────────────────────────────────

    async def pump(self) -> int:
        """Run every ready batch, one at a time; returns how many runs ran."""
        runs = 0
        while True:
            now = self.clock.now_ms()
            self.inbox.sweep(now)
            run.sweep_liveness(self, now)
            if self.state not in (MgrState.IDLE, MgrState.COLLECTING):
                return runs
            batch = self.inbox.next_batch(now, idle=self.state is MgrState.IDLE)
            if batch is None:
                return runs
            await run.run_batch(self, batch)
            runs += 1
