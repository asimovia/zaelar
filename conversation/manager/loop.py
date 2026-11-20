"""The manager of one account: ONE writer (a lease on the store, I5), ONE run at a time, the policy table applied to
everything that arrives. Three states: Idle → Running → Speaking → Idle; whether the run claimed an effect is a fact
of the run, and collecting is the inbox's window. Every wait has its deadline, and the sweep is where they expire.

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
from conversation.gateway import seal as SEAL
from conversation.gateway.outbox import Gateway
from conversation.inbox import Inbox
from conversation.ledger import Book
from conversation.ledger.book import BookTx
from conversation import guard
from conversation.manager import policy, run
from conversation.mouth import Device, Painted, PlayoutAck, SayEnded, SayStarted, Speaker
from conversation.ports import Clock, Memory, Model, Mouth, Owed, Store, Tasks, Telemetry, Tools
from conversation.telemetry import Emitter
from conversation.types import Channel, ControlOp, Coverage, EnvelopeKind, Ids, ItemKind, MgrState, Op

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
    last_entry_ms: int = 0                # the latest close among the person's entries in the batch
    last_endpoint: str | None = None      # …and the device it came from
    resumed_iv: str | None = None         # the resumed voice that stopped this run
    said: list = field(default_factory=list)


class Conversation:
    def __init__(self, *, account: str, owner: str, model: Model, tools: Tools, store: Store, memory: Memory | None,
                 clock: Clock, mouth: Mouth, telemetry: Telemetry, config: Config | None = None, prefix: str = "",
                 ids: Ids | None = None, owed: Owed | None = None, tasks: Tasks | None = None) -> None:
        self.account, self.cfg, self.prefix = account, config or Config(), prefix
        self.model, self.tools, self.memory, self.clock, self.owed, self.tasks = model, tools, memory, clock, owed, tasks
        self.lease = store.acquire(account, owner)
        self.em = Emitter(telemetry, clock, account, epoch=lambda: self.lease.epoch)
        self.store = guard.TimedStore(store, self.em, self.cfg)
        # ids unique across processes on one store (B4): the epoch of the lease names this process's id space
        self.ids = ids or Ids("" if self.lease.epoch == 1 else f"{self.lease.epoch}x")
        lease = lambda: self.lease  # noqa: E731
        self.ear = Ear(account, self.cfg, self.em, self.ids)
        # the controls this manager has a handler for; any other is refused when accepted
        handles = frozenset({ControlOp.STOP} | ({ControlOp.CANCEL_TASK} if tasks is not None else set()))
        self.inbox = Inbox(self.store, lease, account, self.cfg, self.em, self.ids, handles=handles)
        self.book = Book(self.store, lease, account, self.em, clock)
        self.gw = Gateway(self.book, account, self.cfg, self.em, clock, self.ids,
                          lambda: {t.name: t for t in tools.catalog()})
        self.speaker = Speaker(self.store, lease, mouth, self.em, clock, self.ids, on_owed=self._owed_ended, on_ended=self._line_ended, config=self.cfg)
        self.devices: dict[str, Device] = {}
        self.state = MgrState.IDLE
        self.current: Running | None = None
        self.speaking_on: set[str] = set()
        self.dirty = False                  # something was accepted since the last pump (a driver may pump only then)
        self._swept_at = -1 << 62
        self._held_iv: str | None = None     # a run gave its batch back to a resumed voice: nothing runs while it is open
        self.eligible_since = 0              # when the last held batch became eligible again (liveness counts from it)
        self.recover()

    # ── a new owner of the account ──────────────────────────────────────────────────────────────────────────────

    def recover(self) -> None:
        """What a dead process left behind: its dequeued batch back to the queue, an effect left `submitting` to
        `submission_unknown` (never resent), and a voice it was hearing — open under its epoch — ended incomplete
        (reason `restart`, with its event): the sentence the person was saying is not lost in silence, its run asks
        them to say it again, and no voice is left open for a text to wait behind."""
        now = self.clock.now_ms()
        self.inbox.recover(now)
        dispatch.recover(self.gw)
        for iv, voice in self.inbox.open_voices(self.lease.epoch):
            self._restarted(iv, voice, now)

    def _restarted(self, iv: str, voice: dict, now: int) -> None:
        endpoint = voice.get("endpoint")
        self.em.emit("conv_ear", "incomplete", owner="ear", cause={"kind": "restart"},
                     refs={"iv": iv, "endpoint": endpoint, "channel": "voice"}, text="", reason="restart")
        self.give(E.make(EnvelopeKind.USER_UTTERANCE,
                         E.UtteranceBody(iv, "", coverage=Coverage.INCOMPLETE, reason="restart"),
                         producer=f"ear:{endpoint}", producer_id=f"{iv}:{Coverage.INCOMPLETE}", account=self.account,
                         onset_ms=voice.get("onset", now), sealed_ms=now, channel=Channel.VOICE, endpoint=endpoint,
                         refs=E.Refs(intervention_id=iv)))

    # ── in ──────────────────────────────────────────────────────────────────────────────────────────────────────

    def hear(self, sig: S.Signal) -> None:
        for out in self.ear.feed(sig):
            if isinstance(out, S.Onset):
                self._onset(out)
            elif isinstance(out, S.VoiceDiscarded):
                self._discarded(out)
            else:
                self.give(out)

    def _discarded(self, d: S.VoiceDiscarded) -> None:
        """An open voice ended with nothing to answer: noted once, nothing waits behind it, it speaks no more."""
        with self.store.tx(self.lease) as tx:
            SEAL.note(tx, d.intervention_id, "discarded", d.t_ms)
        self.inbox.voice_done(d.intervention_id, self.clock.now_ms())
        self._voice_done(d.endpoint)

    def give(self, env: E.Envelope) -> None:
        now = self.clock.now_ms()
        pending: list = []
        adm = self.inbox.accept(env, now, admit=lambda tx, e: self._admit(tx, e, now, pending))
        self.dirty = True
        self.book.say(pending)
        if adm.envelope is None or adm.disposition == "unhandled":   # a duplicate, refused, or no handler here
            return
        env = adm.envelope
        self._voice_state(env)
        ops = policy.decide(env, self.state, claimed=bool(self.current and self.current.claimed))
        self._apply(env, ops)

    def _admit(self, tx, env: E.Envelope, now: int, pending: list) -> None:
        """Inside the acceptance's transaction, after the dedupe: how the intervention ended (noted once) and the
        person's request, opened with it."""
        k, b = env.kind, env.body
        if k not in REQUESTS:
            return
        whole = k is EnvelopeKind.USER_TEXT or b.coverage is Coverage.FULL
        SEAL.note(tx, b.intervention_id, "closed" if whole else "incomplete", now)
        if b.intervention_id:
            req = f"r_{b.intervention_id}"
            book = BookTx(tx, now, pending)
            book.open(ItemKind.REQUEST, req, data={"req": req, "iv": b.intervention_id, "sealed_ms": env.sealed_ms},
                      cause={"kind": "envelope", "ref": env.id})
            book.attach(req, env.id, decided_by="id", cause={"kind": "envelope", "ref": env.id})

    def _voice_state(self, env: E.Envelope) -> None:
        if env.kind is EnvelopeKind.USER_UTTERANCE and env.endpoint:
            self._voice_done(env.endpoint)          # the voice ended — whole, or incomplete

    def _onset(self, o: S.Onset) -> None:
        """The person starts speaking. While we speak, nothing here: cutting our voice is the voice's local rule."""
        self.speaking_on.add(o.endpoint)
        for op in policy.decide(o, self.state, claimed=bool(self.current and self.current.claimed)):
            if op is Op.WAIT_BEHIND_VOICE:
                self.inbox.voice_open(o.intervention_id, o.t_ms, o.endpoint)
            elif op is Op.ACTIONS_WAIT and self.current is not None:
                self.current.actions_held = True        # an act asked for while they speak is refused with that reason
            elif (op is Op.HOLD_FOR_VOICE and self.current is not None
                  and run.resumed(self, self.current, o.endpoint, o.t_ms)):
                self.current.interrupt = "resumed"      # stop it at its next checkpoint; its batch waits for that voice
                self.current.resumed_iv = o.intervention_id

    def _voice_done(self, endpoint: str) -> None:
        if endpoint in self.speaking_on:
            self.speaking_on.discard(endpoint)
        if self.current is not None and not self.speaking_on:
            self.current.actions_held = False

    def hold_for(self, iv: str) -> None:
        """A run gave its batch back to the person's resumed voice: nothing runs while that voice is open. The ear
        always ends it (its cap, on the sweep's ticks): then the continuation travels with the batch, or — a cough,
        no words — the batch runs as it was."""
        self._held_iv = iv

    def _apply(self, env: E.Envelope, ops: tuple[Op, ...]) -> None:
        for op in ops:
            if op is Op.SILENCE:
                self.speaker.stop(None, "new_input" if env.kind is not EnvelopeKind.USER_CONTROL else "stop",
                                  self.clock.mono_ms())
                if self.state is MgrState.SPEAKING:   # our voice is stopped: we are not speaking, ack or no ack
                    self.state = MgrState.IDLE
            elif op is Op.SUPERSEDE and self.current is not None and not self.current.claimed:
                if self.current.interrupt != "resumed":   # already held for this voice: the hold carries it
                    self.current.interrupt = "superseded"
            elif op is Op.CANCEL_RUN and self.current is not None:
                self.current.interrupt = "cancelled"
            elif op is Op.BY_ID:
                self._by_id(env)
            # RUN, FOLLOW_UP: the queue keeps it; the next pump with the manager free runs it.
        if env.kind is EnvelopeKind.USER_CONTROL and env.body.op is ControlOp.STOP:
            self.inbox.applied(env.id, self.clock.now_ms())

    def _by_id(self, env: E.Envelope) -> None:
        """A control by id. Only those with a handler reach here (the inbox refused the rest when it accepted them):
        in F1, cancelling one of the host's tasks. Cancelling a task is never a stop and never a run's cancel (D3)."""
        if env.body.op is ControlOp.CANCEL_TASK and self.tasks is not None:
            guard.sync(self.em, self.cfg, "tasks", lambda: self.tasks.cancel(self.account, env.body.task_id or ""))
            self.inbox.applied(env.id, self.clock.now_ms())

    def ack(self, sig: SayStarted | PlayoutAck | Painted | SayEnded) -> None:
        self.speaker.ack(sig)

    def _line_ended(self, _say_id: str) -> None:
        """A line ended — played, cut, or unknown past its deadline: we are not speaking any more."""
        if self.state is MgrState.SPEAKING:
            self.state = MgrState.IDLE

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
            if self.state is not MgrState.IDLE:
                return runs
            if self._held_iv is not None:
                if self._held_iv in self.ear.open_ids():
                    return runs
                self._held_iv, self.eligible_since = None, now
            batch = self.inbox.next_batch(self.clock.now_ms())
            if batch is None:
                await self._say_owed()
                return runs
            await run.run_batch(self, batch)
            runs += 1

    async def _say_owed(self) -> None:
        """Free, nobody speaking, no entry waiting: say the next line owed, as it is — no model — and only by voice (it
        is already on the wall). Only `pump` calls it, and only when free: the row OWED of the table, whose other cells
        leave the line in its ledger. With no device that can speak, it goes back to its ledger for its other ways."""
        if self.owed is None or self.speaking_on:
            return
        line = self.owed.next(self.account)
        if line is None:
            return
        device = next((d for d in self.devices.values() if d.voice_live and d.speaker_open and not d.blocked), None)
        if device is None:
            self.owed.release(line.key)
            return
        self.state = MgrState.SPEAKING
        await self.speaker.say(run_id=f"owed:{line.key}", request_id=line.key, text=line.text,
                               channels=frozenset({"voice"}), endpoint=device.endpoint, notice_key=line.key)

    def _owed_ended(self, key: str, sounded: bool) -> None:
        """The line owed ended: said, its ledger marks it spoken; it never sounded, it goes back for its other ways."""
        if self.owed is None:
            return
        if sounded:
            self.owed.settle(key)
        else:
            self.owed.release(key)
