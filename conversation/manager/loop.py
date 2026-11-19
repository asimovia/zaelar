"""The manager of one account: ONE writer (a lease on the store, I5), ONE run at a time, the policy table applied to
everything that arrives (§6.3). Idle → Collecting → Running (unclaimed | claimed) → Speaking → Idle.

`hear(signal)` feeds the ear; `give(envelope)` takes what other producers send (workers, connectors, reminders,
buttons); `ack(...)` takes the mouth's acknowledgements; `pump()` runs what is ready until nothing is; `sweep(now)`
is the clock's turn — holds, deferrals, lines nobody acknowledged, voices nobody ends, requests past their
liveness budget — and runs on its own timer (`keep_time`), never only inside `pump`. The control lane (onset, stop,
acks) never waits for a run. A new input during a run is applied at the run's next checkpoint: SUPERSEDE replaces the
RUN (never the request, N1), FOLLOW_UP queues, CANCEL_RUN drops it, SILENCE stops our voice. A person's entry opens
its request in the SAME transaction that accepts it, so liveness counts from the moment it was accepted.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from conversation import envelopes as E
from conversation.config import Config
from conversation.ear import Ear
from conversation.ear import signals as S
from conversation.gateway import dispatch
from conversation.gateway.authority import RunCtx
from conversation.gateway.outbox import Claimed
from conversation.gateway import seal as SEAL
from conversation.gateway.outbox import Gateway
from conversation.inbox import Inbox
from conversation.inbox.mailbox import apply_control
from conversation.ledger import Book
from conversation.ledger.book import BookTx
from conversation.ledger.items import final
from conversation import guard
from conversation.manager import policy, run
from conversation.manager.focus import Focus
from conversation.mouth import Device, Painted, PlayoutAck, SayEnded, SayStarted, Speaker
from conversation.ports import Clock, Memory, Model, Mouth, Store, Telemetry, Tools
from conversation.telemetry import Emitter
from conversation.types import ControlOp, EnvelopeKind, Ids, IvState, ItemKind, MgrState, Op

REQUESTS = (EnvelopeKind.USER_UTTERANCE, EnvelopeKind.USER_TEXT)


@dataclass
class Running:
    run_id: str
    batch_ids: tuple[str, ...]
    requests: tuple[str, ...]
    ctx: RunCtx
    batch_seq: int = 0
    claimed: bool = False
    interrupt: str | None = None          # superseded · cancelled · stalled
    actions_held: bool = False
    presents: str | None = None
    said: list = field(default_factory=list)


class Conversation:
    def __init__(self, *, account: str, owner: str, model: Model, tools: Tools, store: Store, memory: Memory | None,
                 clock: Clock, mouth: Mouth, telemetry: Telemetry, config: Config | None = None, prefix: str = "",
                 ids: Ids | None = None) -> None:
        self.account, self.cfg, self.prefix = account, config or Config(), prefix
        self.model, self.tools, self.memory, self.clock = model, tools, memory, clock
        self.lease = store.acquire(account, owner)
        self.em = Emitter(telemetry, clock, account, epoch=lambda: self.lease.epoch)
        self.store = guard.TimedStore(store, self.em, self.cfg)
        # ids unique across processes on one store (B4): the epoch of the lease names this process's id space
        self.ids = ids or Ids("" if self.lease.epoch == 1 else f"{self.lease.epoch}x")
        lease = lambda: self.lease  # noqa: E731
        self.ear = Ear(account, self.cfg, self.em, self.ids)
        self.inbox = Inbox(self.store, lease, account, self.cfg, self.em, self.ids)
        self.book = Book(self.store, lease, account, self.em, clock)
        self.gw = Gateway(self.book, account, self.cfg, self.em, clock, self.ids,
                          lambda: {t.name: t for t in tools.catalog()})
        self.focus = Focus()
        self.speaker = Speaker(self.store, lease, mouth, self.em, clock, self.ids, on_presented=self._presented,
                               config=self.cfg)
        self.devices: dict[str, Device] = {}
        self.state = MgrState.IDLE
        self.current: Running | None = None
        self.speaking_on: set[str] = set()
        self.to_submit: list[str] = []      # effects a gesture committed outside a run, sent by the next pump
        self.dirty = False                  # something was accepted since the last pump (a driver may pump only then)
        self._swept_at = -1 << 62
        self._pruned_at = -1 << 62
        self._voice_wait: int | None = None  # a run gave its batch back on a held act: nothing runs until that voice ends
        self.recover()

    # ── a new owner of the account ──────────────────────────────────────────────────────────────────────────────

    def recover(self) -> None:
        """What a dead process left behind: its dequeued batch back to the queue, an effect left `submitting` to
        `submission_unknown` (never resent)."""
        self.inbox.recover(self.clock.now_ms())
        dispatch.recover(self.gw)

    # ── in ──────────────────────────────────────────────────────────────────────────────────────────────────────

    def hear(self, sig: S.Signal) -> None:
        for out in self.ear.feed(sig):
            if isinstance(out, S.Onset):
                self._onset(out)
            else:
                self.give(out)

    def give(self, env: E.Envelope) -> None:
        now = self.clock.now_ms()
        pending: list = []
        adm = self.inbox.accept(env, now, admit=lambda tx, e: self._admit(tx, e, now, pending))
        self.dirty = True
        self.book.say(pending)
        if adm.envelope is None:
            return
        env = adm.envelope
        self._voice_state(env)
        ops = policy.decide(env, self.state, claimed=bool(self.current and self.current.claimed),
                            person_speaking=bool(self.speaking_on))
        self._apply(env, ops)

    def _admit(self, tx, env: E.Envelope, now: int, pending: list) -> None:
        """Inside the acceptance's transaction, after the dedupe: how the intervention ended (noted once) and the
        person's request, opened with it."""
        k, b = env.kind, env.body
        if k in REQUESTS:
            SEAL.note(tx, b.intervention_id, "closed", now)
        elif k is EnvelopeKind.INTERVENTION_STATE and b.state in (IvState.INCOMPLETE, IvState.DISCARDED):
            SEAL.note(tx, b.intervention_id, str(b.state), now)
        opens = k in REQUESTS or (k is EnvelopeKind.INTERVENTION_STATE and b.state is IvState.INCOMPLETE)
        if opens and b.intervention_id:
            req = f"r_{b.intervention_id}"
            book = BookTx(tx, now, pending)
            book.open(ItemKind.REQUEST, req, data={"req": req, "iv": b.intervention_id, "sealed_ms": env.sealed_ms},
                      cause={"kind": "envelope", "ref": env.id})
            book.attach(req, env.id, decided_by="id", cause={"kind": "envelope", "ref": env.id})

    def _voice_state(self, env: E.Envelope) -> None:
        if env.kind not in (EnvelopeKind.USER_UTTERANCE, EnvelopeKind.INTERVENTION_STATE) or not env.endpoint:
            return
        if env.kind is EnvelopeKind.USER_UTTERANCE or env.body.state in (IvState.INCOMPLETE, IvState.DISCARDED):
            self._voice_done(env.endpoint)

    def _onset(self, o: S.Onset) -> None:
        self.speaking_on.add(o.endpoint)
        self.gw.note_onset(o.endpoint, o.t_ms)
        for op in policy.decide(o, self.state, claimed=bool(self.current and self.current.claimed)):
            if op is Op.FIX_FOCUS:
                self.focus.onset(o.endpoint)
            elif op is Op.DUCK:
                self.speaker.duck(o.endpoint)
            elif op is Op.HOLD_ACTIONS and self.current is not None:
                self.current.actions_held = True        # unclaimed actions wait: the gateway answers Held (M5)
                dispatch.hold(self.gw, self.ids.new("hold"), o.endpoint, self.clock.now_ms(), "onset")

    def _voice_done(self, endpoint: str) -> None:
        if endpoint in self.speaking_on:
            self.speaking_on.discard(endpoint)
            self.focus.done_speaking(endpoint)
            if self.state is MgrState.SPEAKING:
                self.speaker.unduck(endpoint)
        if self.current is not None and not self.speaking_on:
            self.current.actions_held = False
        if not self.speaking_on:
            self._voice_wait = None

    def wait_for_voice(self) -> None:
        """A run met a held act (NM1): the batch is back in the queue and runs again when the person has finished —
        the voice that held it closes (a new sentence supersedes it) or ends with no words (it runs as it was). Bounded
        by `cross_channel_hold_ms` whatever the voice does."""
        self._voice_wait = self.clock.now_ms()

    def _apply(self, env: E.Envelope, ops: tuple[Op, ...]) -> None:
        for op in ops:
            if op is Op.SILENCE:
                self.speaker.stop(None, "new_input" if env.kind is not EnvelopeKind.USER_CONTROL else "stop",
                                  self.clock.mono_ms())
                if self.state is MgrState.SPEAKING:   # our voice is stopped: we are not speaking, ack or no ack
                    self.state = MgrState.IDLE
            elif op in (Op.SUPERSEDE, Op.AT_CHECKPOINT) and self.current is not None and not self.current.claimed:
                self.current.interrupt = "superseded"
            elif op is Op.CANCEL_RUN and self.current is not None:
                self.current.interrupt = "cancelled"
            elif op is Op.BY_ID:
                self._by_id(env)
            # FOLLOW_UP, JOIN, WHEN_IDLE: the queue keeps it.
        if env.kind is EnvelopeKind.USER_CONTROL and env.body.op is ControlOp.STOP:
            self.inbox.applied(env.id, self.clock.now_ms())

    def _by_id(self, env: E.Envelope) -> None:
        op = env.body.op
        if op is ControlOp.CONFIRM:
            got = self.gw.confirm(env)
            if isinstance(got, Claimed):            # the gesture committed it: the next pump sends it
                self.to_submit.append(got.effect_id)
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

    def release(self, effect_id: str, endpoint: str | None, gesture: bool) -> bool:
        """A gesture on the initiating device commits a held effect: the next pump sends it."""
        ok = dispatch.release(self.gw, effect_id, endpoint, gesture)
        if ok:
            self.to_submit.append(effect_id)
        return ok

    def ack(self, sig: SayStarted | PlayoutAck | Painted | SayEnded) -> None:
        self.speaker.ack(sig)
        if isinstance(sig, SayEnded) and self.state is MgrState.SPEAKING:
            self.state = MgrState.IDLE

    def _presented(self, handle: str, endpoint: str | None) -> None:
        if handle:
            self.gw.present(handle, endpoint)
            self.focus.presented(handle, endpoint, self.clock.now_ms())

    def device(self, endpoint: str, **state) -> None:
        self.devices[endpoint] = Device(endpoint, **state)

    # ── the clock's turn ────────────────────────────────────────────────────────────────────────────────────────

    def sweep(self, now: int | None = None) -> None:
        now = self.clock.now_ms() if now is None else now
        self.hear(S.Tick(now))                          # the ear lives on the sweep's time too, not only on signals (N2)
        self.inbox.sweep(now)
        for say_id in self.speaker.overdue(now):        # a line nobody acknowledged ended «unknown» (B2)
            self.ack(SayEnded(say_id, "unknown", None, now))
        run.sweep_liveness(self, now)
        if now - self._pruned_at >= self.cfg.prune_every_ms:
            self._pruned_at = now
            self.prune(now)

    def prune(self, now: int) -> int:
        """What is done and older than `retain_ms` leaves the live tables (NM2). Returns how many rows moved."""
        old = now - self.cfg.retain_ms
        done = {
            "inbox": lambda r: r["state"] == "accounted" and r.get("accounted_ms", now) <= old,
            "says": lambda r: r["state"] == "ended" and r["t_ms"] <= old,
            SEAL.T: lambda r: r["phase"] in ("sealed", "final") and r.get("updated_ms", now) <= old,
            "items": lambda r: final(ItemKind(r["kind"]), r["state"]) and r["updated_ms"] <= old,
        }
        moved = 0
        with self.store.tx(self.lease) as tx:
            for table, is_done in done.items():
                for key, row in tx.scan(table):
                    if is_done(row):
                        tx.archive(table, key)
                        moved += 1
            turns = tx.scan("turns")
            for key, _row in turns[:max(0, len(turns) - 4 * self.cfg.conversation_turns)]:
                tx.archive("turns", key)
                moved += 1
        return moved

    async def keep_time(self, every_ms: int = 1000) -> None:
        """The sweep on its own timer, for the adapter to run beside the loop: a hung run cannot stop it (B3)."""
        while True:
            await self.clock.sleep_until(self.clock.mono_ms() + every_ms)
            self.sweep()

    # ── run what is ready ───────────────────────────────────────────────────────────────────────────────────────

    async def pump(self) -> int:
        """Run every ready batch, one at a time; returns how many runs ran."""
        runs, self.dirty = 0, False
        while True:
            now = self.clock.now_ms()
            if now - self._swept_at >= 100:      # the clock's turn is about time: once per 100 ms is every time
                self._swept_at = now
                self.sweep(now)
            while self.to_submit:
                eid = self.to_submit.pop(0)
                await dispatch.submit(self.gw, self.tools, eid, self.clock.mono_ms() + self.cfg.tool_ms)
            if self.state not in (MgrState.IDLE, MgrState.COLLECTING):
                return runs
            if self._voice_wait is not None:
                if self.speaking_on and now - self._voice_wait < self.cfg.cross_channel_hold_ms:
                    return runs
                self._voice_wait = None
            batch = self.inbox.next_batch(self.clock.now_ms(), idle=self.state is MgrState.IDLE)
            if batch is None:
                return runs
            await run.run_batch(self, batch)
            runs += 1
