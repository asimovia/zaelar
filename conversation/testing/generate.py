"""P3: a seeded generator of random conversations, and the invariants I1–I9 checked on what each one left behind.

`run_case(seed)` builds a manager over an audited in-memory store and drives it with a random interleaving: voice cut
at random (eager / resumed / an end of turn mid-sentence / a stream that stops), typed texts on another device, stops
from a button or the text field, confirmations with and without a gesture, workers' progress, questions and results,
contacts' messages, reminders, jumps of the clock, and a TAKEOVER (another process acquires the account, the old one
keeps being fed). The model is scripted at random — reads, local writes, sends, replies with and without numeric
claims, silences, failures — and injects new input between its own events, so checkpoints are exercised. At the end
time runs out (every hold, deferral and liveness budget expires) and `check(...)` returns the violations, as text.

Deterministic: one seed, one case. No wall clock, no I/O, standard library only (PA-6: no Hypothesis).
"""
from __future__ import annotations

import asyncio
import random
from contextlib import contextmanager

from conversation import envelopes as E
from conversation.config import Config
from conversation.ear import signals as S
from conversation.inbox.accounting import audit
from conversation.manager import Conversation
from conversation.ports import Command, Done, Failed, StaleEpoch, ToolCall, ToolResult
from conversation.store.memory import MemoryStore
from conversation.store.sqlite import SqliteStore
from conversation.testing.fakes import AckingMouth, FakeClock, ListTelemetry, NoMemory, RecordingTools, evidence
from conversation.testing.scripted_model import ScriptedModel, reply
from conversation.types import Channel, ControlOp, EnvelopeKind, ItemKind, WorkerUpdate

ACCT = "acct-p3"


class _Audited:
    """Records every COMMITTED transaction with the epoch it ran under (I5 is checked on this log)."""

    def __init__(self, *a, **kw) -> None:
        super().__init__(*a, **kw)
        self.commits: list[tuple[int, int]] = []        # (commit index, epoch)
        self.takeovers: list[tuple[int, int]] = []      # (commit index at the takeover, new epoch)

    def acquire(self, account, owner):
        lease = super().acquire(account, owner)
        self.takeovers.append((len(self.commits), lease.epoch))
        return lease

    @contextmanager
    def tx(self, lease):
        with super().tx(lease) as t:
            yield t
        self.commits.append((len(self.commits), lease.epoch))


class AuditedStore(_Audited, MemoryStore):
    """The audited store in memory: most cases."""


class AuditedSqliteStore(_Audited, SqliteStore):
    """The audited store on sqlite: one case in ten, so its own paths (`json_extract` in `cas`, `BEGIN IMMEDIATE`, the
    archive's move) are bombarded too (review 2, MINOR 6)."""


class Case:
    def __init__(self, seed: int, cfg: Config | None = None) -> None:
        self.rng = random.Random(seed)
        self.seed = seed
        self.cfg = cfg or Config(liveness_ms=60_000, model_first_ms=40, model_gap_ms=40, tool_ms=40,
                                 say_end_ms=8000)
        self.on_sqlite = seed % 10 == 3                       # chosen by the seed, not the rng: seeds stay seeds
        self.store = AuditedSqliteStore(":memory:") if self.on_sqlite else AuditedStore()
        self.clock, self.tel = FakeClock(), ListTelemetry()
        self.tools = RecordingTools()
        if self.rng.random() < 0.1:
            self.tools.raises["market_data"] = ValueError("p3: the adapter broke")    # B6
        self.tools.answers["market_data"] = ToolResult("ok", evidence=(evidence("ev1", "ACME", "q3", "up_days",
                                                                                 "up", 18),))
        self.model = ScriptedModel(default=self._behave)
        self.issued_calls = 0
        self.mouth = AckingMouth(heard_all=self.rng.random() < 0.7)
        self.conv = self._manager("p1")
        self.old: Conversation | None = None
        self.seq, self.n = 0, 0
        self.crashes: list[str] = []
        self.race_seals: list[tuple[str, int]] = []
        self.draining = False
        self.fenced = 0
        self.loop = asyncio.new_event_loop()

    def _manager(self, owner: str) -> Conversation:
        c = Conversation(account=ACCT, owner=owner, model=self.model, tools=self.tools, store=self.store,
                         memory=NoMemory(), clock=self.clock, mouth=self.mouth, telemetry=self.tel, config=self.cfg,
                         prefix="P3", ids=None)
        self.mouth.ack = self._lossy_ack(c)                                 # B2: acks get lost
        for ep in ("d1", "d2"):
            c.device(ep, voice_live=self.rng.random() < 0.8, speaker_open=self.rng.random() < 0.8)
        return c

    @staticmethod
    def _hang():
        class _Hang:                                   # an event the scripted model awaits: past every deadline
            def __await__(self):
                return asyncio.sleep(0.045).__await__()
        return _Hang()

    def _lossy_ack(self, conv: Conversation):
        loss = self.rng.choice([0.0, 0.0, 0.3, 1.0])

        def ack(sig):
            if self.rng.random() >= loss:
                conv.ack(sig)
        return ack

    # ── the model, at random ───────────────────────────────────────────────────────────────────────────────────

    def _behave(self, ids: list[str]) -> list:
        r, out = self.rng.random(), []
        if len(self.model.calls) > 300:
            self.crashes.append("loop: more than 300 model calls in one case — a run is re-run in a loop")
            raise RuntimeError("a run is re-run in a loop")
        if not self.draining and self.rng.random() < 0.25:
            out.append(lambda: self._safe(self._random_action))           # new input between two model events
        elif not self.draining and self.rng.random() < 0.08:
            out.append(lambda: self._safe(self._reopen_mid_run))           # B1/B5: he goes on while it runs
        if r < 0.15:
            self.issued_calls += 1
            out += [ToolCall("c", "market_data", {"q": "w1"}), Done()]
        elif r < 0.30:
            self.issued_calls += 1
            out += [ToolCall("c", "agenda_add", {"what": f"w{self.rng.randint(1, 3)}"}), Done()]
        elif r < 0.42:
            call = ToolCall("c", "send_message", {"to": "c1", "via": "chat", "text": "w5"})
            twice = self.rng.random() < 0.3                                     # M2: the same call again
            self.issued_calls += 2 if twice else 1
            out += [call, call, Done()] if twice else [call, Done()]
        elif r < 0.52:
            claim = {"entity": "ACME", "period": "q3", "metric": "up_days", "value": 18, "evidence_id": "ev1",
                     "direction": self.rng.choice(["up", "down"])}
            if self.rng.random() < 0.2:
                claim.pop("value")                                                 # M3: a number with no value
            out += [reply("w8nv" if "value" not in claim else "w8", [claim]), Done()]
        elif r < 0.60:
            out += [Command("no_reply", {"reason": "p3"}), Done()]
        elif r < 0.65:
            out += [Failed("p3", "provider")]
        elif r < 0.654:
            out += [self._hang(), reply("w0"), Done()]                       # B3: a provider that hangs
        else:
            out += [reply(f"w{self.rng.randint(10, 99)}. w{self.rng.randint(10, 99)}?"), Done()]
        return out

    # ── input, at random ───────────────────────────────────────────────────────────────────────────────────────

    def _safe(self, fn) -> None:
        try:
            fn()
        except StaleEpoch:
            self.fenced += 1                                                 # the old process, fenced: expected
        except Exception as e:  # noqa: BLE001 — a crash is a finding of the bombardment, recorded by name
            self.crashes.append(f"{type(e).__name__}: {e}")

    def _feed(self, conv: Conversation, *sigs) -> None:
        for s in sigs:
            for one in (s if isinstance(s, list) else [s]):
                t = getattr(one, "t_ms", None) or getattr(one, "processed_through_ms", None) or (
                    one.window[1] if isinstance(one, S.WordSpan) else None)
                if t is not None:
                    self.clock.mono = max(self.clock.mono, t - self.clock.wall0)
                conv.hear(one)
                if conv.current is None and (conv.dirty or isinstance(one, S.Tick)):
                    self.loop.run_until_complete(conv.pump())

    def _now(self) -> int:
        return self.clock.now_ms()

    def _speak(self, conv: Conversation) -> None:
        ep = self.rng.choice(["d1", "d1", "d2"])
        t = self._now() + 10
        self.seq += 1
        seq, rev, said = self.seq, 0, []
        self._feed(conv, S.VadEdge(ep, "rise", t, echo_safe=self.rng.random() < 0.9))
        for part in range(self.rng.randint(1, 3)):
            ws = tuple((f"w{self.rng.randint(1, 60)}", t + i * 180, t + (i + 1) * 180 - 20, 1.0)
                       for i in range(self.rng.randint(1, 4)))
            said += ws
            rev += 1
            t = ws[-1][2]
            last = part == 2 or self.rng.random() < 0.4
            self._feed(conv, S.WordSpan(ep, seq, rev, last, tuple(said), (said[0][1], t)), S.Watermark(ep, t + 60))
            if last:
                break
            gap = self.rng.choice([300, 700, 900, 1500])
            how = self.rng.random()
            if how < 0.25:                                                   # the provider closes at the pause
                self._feed(conv, S.VadEdge(ep, "fall", t + 10), S.Watermark(ep, t + 280),
                           S.EotHint(ep, "flux", "end", .7, t + 300))
                self.seq += 1
                seq, rev, said = self.seq, 0, []
            elif how < 0.95:
                self._feed(conv, S.EotHint(ep, "flux", "eager", .55, t + 250))
                self._feed(conv, *[S.Watermark(ep, x) for x in range(t + 250, t + gap, 240)])
                self._feed(conv, S.EotHint(ep, "flux", "resumed", .1, t + gap))
            else:
                self._feed(conv, S.Tick(t + 5000))                         # the stream stops: incomplete
                return
            t += gap
        if self.rng.random() < 0.05:
            self._feed(conv, S.Discard(ep, "w0", "echo", t + 20))
            return
        self._feed(conv, S.VadEdge(ep, "fall", t + 10), *[S.Watermark(ep, x) for x in range(t + 60, t + 400, 240)],
                   S.EotHint(ep, "flux", "end", .9, t + 400))

    def _envelope(self, conv: Conversation, kind: EnvelopeKind, body, *, channel=None, endpoint=None,
                  must_tell=False, surfacing=None) -> None:
        self.n += 1
        kw = {"surfacing": surfacing} if surfacing is not None else {}
        conv.give(E.make(kind, body, producer=f"{E.KINDS[kind][3][0]}p3", producer_id=f"{self.n}", account=ACCT,
                         onset_ms=self._now(), sealed_ms=self._now(), channel=channel, endpoint=endpoint,
                         must_tell=must_tell, refs=E.Refs(task_id=getattr(body, "task_id", None)), **kw))
        if conv.current is None:
            self.loop.run_until_complete(conv.pump())

    def _random_action(self, conv: Conversation | None = None) -> None:
        conv = conv or self.conv
        a = self.rng.random()
        if a < 0.30:
            self._speak(conv)
        elif a < 0.45:
            self.n += 1
            self._feed(conv, S.TypedSubmit(self.rng.choice(["d1", "d2"]), f"t{self.n}",
                                           f"w{self.rng.randint(1, 60)}", self._now() + 1))
        elif a < 0.52:
            self._envelope(conv, EnvelopeKind.USER_CONTROL, E.ControlBody(ControlOp.STOP),
                           channel=self.rng.choice([Channel.BUTTON, Channel.TEXT]), endpoint="d1")
        elif a < 0.62:
            handles = [r["id"] for _k, r in self.store.snapshot(ACCT).scan("items") if r["kind"] == "handle"]
            self._envelope(conv, EnvelopeKind.USER_CONTROL,
                           E.ControlBody(ControlOp.CONFIRM, handle_id=self.rng.choice(handles or ["h_none"]),
                                         gesture=self.rng.random() < 0.6), channel=Channel.BUTTON, endpoint="d1")
        elif a < 0.75:
            kind = self.rng.choice(list(WorkerUpdate))
            self._envelope(conv, EnvelopeKind.WORKER_UPDATE,
                           E.WorkerBody("t1", kind, "w7", question_id="q1" if kind is WorkerUpdate.QUESTION else None),
                           must_tell=kind is WorkerUpdate.RESULT)
        elif a < 0.82:
            self._envelope(conv, EnvelopeKind.CONTACT_MESSAGE, E.ContactBody("th1", "c-ref", "w6"))
        elif a < 0.86:
            self._envelope(conv, EnvelopeKind.SYSTEM_REMINDER, E.ReminderBody("rm1", "w4", self._now()),
                           must_tell=True)
        elif a < 0.91:
            self._race_seal(conv)
        elif a < 0.94:
            self._redeliver(conv)                                                # B5: an adapter re-delivers
        elif a < 0.955:
            self._go_on_unfinished(conv)                                         # B1: a reopen left open
        elif a < 0.965:
            self._forge(conv)                                                    # M1: a forged producer / account
        elif a < 0.975:
            self._envelope(conv, EnvelopeKind.USER_CONTROL, E.ControlBody(         # M4: a hands-free scope
                ControlOp.DELEGATE, gesture=True, scope={"recipients": ["c1"], "channel": "chat",
                                                         "expires_ms": self._now() + 10 ** 7, "max": 3}),
                channel=Channel.BUTTON, endpoint="d1")
        else:
            self.clock.advance(self.rng.choice([100, 2000, 9000, 40_000]))
            self._feed(conv, S.Tick(self._now()))

    def _forge(self, conv: Conversation) -> None:
        self.n += 1
        if self.rng.random() < 0.5:
            env = E.make(EnvelopeKind.USER_TEXT, E.TextBody(f"ivf{self.n}", "w1"), producer="connector:p3",
                         producer_id=f"f{self.n}", account=ACCT, onset_ms=self._now(), sealed_ms=self._now(),
                         channel=Channel.TEXT)
        else:
            env = E.make(EnvelopeKind.USER_TEXT, E.TextBody(f"ivf{self.n}", "w1"), producer="chat:d9",
                         producer_id=f"f{self.n}", account="another-account", onset_ms=self._now(),
                         sealed_ms=self._now(), channel=Channel.TEXT)
        conv.give(env)

    def _reopen_mid_run(self) -> None:
        """While the model runs on a closed intervention, the person goes on (a word, no end yet) and an adapter
        re-delivers the closed one."""
        conv = self.conv
        rows = [r for _k, r in self.store.snapshot(ACCT).scan("inbox") if r["kind"] == "user.utterance"]
        self._go_on_unfinished(conv)
        if rows and self.rng.random() < 0.5:
            conv.give(E.from_json({**rows[-1]["env"], "id": "", "accepted_ms": 0}))

    def _redeliver(self, conv: Conversation) -> None:
        rows = [r for _k, r in self.store.snapshot(ACCT).scan("inbox") if r["kind"] in ("user.utterance",
                                                                                         "user.text")]
        if rows:
            row = self.rng.choice(rows)
            conv.give(E.from_json({**row["env"], "id": "", "accepted_ms": 0}))

    def _go_on_unfinished(self, conv: Conversation) -> None:
        """The person goes on after a close with a word and no end yet, and the provider keeps beating."""
        ep, t = "d1", self._now() + 20
        self.seq += 1
        ws = ((f"w{self.rng.randint(1, 60)}", t, t + 160, 1.0),)
        self._feed(conv, S.VadEdge(ep, "rise", t), S.WordSpan(ep, self.seq, 1, False, ws, (t, t + 160)),
                   *[S.Watermark(ep, x) for x in range(t + 200, t + 2500, 240)])

    def _race_seal(self, conv: Conversation) -> None:
        """Another writer of the account (a confirmation, the other process's gateway) seals a closed intervention the
        manager has not published — and the person goes on speaking: what follows is another intervention (I3)."""
        from conversation.gateway import seal as SEAL
        closed = [iv for iv, r in self.store.snapshot(ACCT).scan("interventions") if r["phase"] == "closed"]
        if not closed:
            return
        iv = self.rng.choice(closed)
        with self.store.tx(conv.lease) as tx:
            if SEAL.seal(tx, iv, self._now()):
                self.race_seals.append(iv)
        self._speak(conv)

    def play(self, actions: int) -> None:
        for i in range(actions):
            if i == actions // 2 and self.rng.random() < 0.2:
                self.old, self.conv = self.conv, self._manager("p2")          # another process takes the account
            target = self.old if (self.old is not None and self.rng.random() < 0.2) else self.conv
            self._safe(lambda: self._random_action(target))
        self._safe(self._drain)

    def _drain(self) -> None:
        """Time runs out: no new input; every hold, deferral and budget expires; whatever is ready runs."""
        self.draining = True
        for _ in range(4):
            self.clock.advance(max(self.cfg.must_tell_max_defer_ms, self.cfg.liveness_ms,
                                   self.cfg.cross_channel_hold_ms) + 1)
            # no device signal any more — not even a tick for the ear: only the manager's own clock (N2)
            self.loop.run_until_complete(self.conv.pump())


class _WithArchive:
    """A snapshot that reads each table together with its archive (`<table>.done`)."""

    def __init__(self, snap) -> None:
        self._s = snap

    def get(self, table: str, key: str):
        return self._s.get(table, key) or self._s.get(f"{table}.done", key)

    def scan(self, table: str):
        return sorted(self._s.scan(table) + self._s.scan(f"{table}.done"))


def check(case: Case) -> list[str]:
    """I1–I9 over what the case left behind. Each violation is one sentence."""
    out = [f"crash: {c}" for c in case.crashes]
    live = case.store.snapshot(getattr(case, "account", ACCT))
    snap = _WithArchive(live)                      # what the sweep archived is still what the case left behind (NM2)
    items = {k: r for k, r in snap.scan("items")}
    phases = {k: r["phase"] for k, r in snap.scan("interventions")}
    for eid, row in items.items():
        if row["kind"] != str(ItemKind.EFFECT):
            continue
        for iv in row["data"].get("ivs", []):                                        # I1
            if phases.get(iv) not in ("sealed", "final"):
                out.append(f"I1: effect {eid} rests on {iv} in phase {phases.get(iv)}")
        mandate = items.get(row["data"]["mandate"])                                    # I8
        if mandate is None and row["data"]["tool"] == "send_message":
            out.append(f"I8: send {eid} without a handle, delegation or grant")
    owners: dict = {}                                       # I2: a word is identified by its provider turn and place
    for c in ((case.conv,) if case.old is None else ()):
        for iv, word_id in c.ear.spans.final_word_ids():
            owners.setdefault(word_id, set()).add(iv)
    if any(len(ivs) > 1 for ivs in owners.values()):
        out.append("I2: a final word in two interventions")
    sealed = set(case.race_seals) | {p["refs"]["iv"] for k, lab, p in case.tel.events
                                     if k == "conv_effect" and lab == "sealed"}
    for iv in sorted(sealed):                                         # I3: a seal is forever (final keeps it)
        if phases.get(iv) not in ("sealed", "final"):
            out.append(f"I3: {iv} sealed and now {phases.get(iv)}")
    inbox_rows = [r for _k, r in snap.scan("inbox")]
    content = [r for r in inbox_rows if r["kind"] in ("user.utterance", "user.text")]
    per_iv: dict = {}
    for r in content:                                       # I3: one accepted entry per intervention, never a second
        iv = r["env"]["refs"]["intervention_id"]
        per_iv[iv] = per_iv.get(iv, 0) + 1
    out += [f"I3: {iv} accepted {n} entries" for iv, n in per_iv.items() if n > 1]
    for k, lab, p in case.tel.events:                                                  # I4
        if k == "conv_ear" and lab == "discarded" and ("reason" not in p or "text" not in p):
            out.append("I4: a discard without its text and reason")
    for idx, epoch in case.store.commits:                                              # I5
        newer = [e for at, e in case.store.takeovers if at <= idx]
        if newer and epoch < max(newer):
            out.append(f"I5: commit {idx} under epoch {epoch} after the takeover to {max(newer)}")
            break
    out += [f"I6: {v}" for v in audit(snap, case.clock.now_ms(), case.cfg, drained=True)]  # I6
    core = {t.name for t in case.tools.catalog() if t.core}
    if any(not core <= {t.name for t in c.tools} for c in case.model.calls):          # I7
        out.append("I7: a model call without the core tools")
    if len(case.tools.calls) > case.issued_calls:
        out.append("I7: a tool ran that the model did not ask for")
    closes: dict[str, int] = {}
    closed_at: dict[str, int] = {}
    for k, lab, p in case.tel.events:
        if k == "conv_close":
            closes[p["refs"]["req"]] = closes.get(p["refs"]["req"], 0) + 1
            closed_at.setdefault(p["refs"]["req"], p["t_ms"])
    for r in inbox_rows:                                                               # I8/M1
        if not r["env"]["producer"].startswith(E.KINDS[EnvelopeKind(r["kind"])][3]) or \
                r["env"]["account"] != getattr(case, "account", ACCT):
            out.append(f"I8: {r['id']} accepted from {r['env']['producer']} for {r['env']['account']}")
    for rid, row in items.items():
        if row["kind"] == str(ItemKind.DELEGATION) and row["data"].get("used", 0) > len(
                [e for e in items.values() if e["kind"] == "effect" and e["data"].get("mandate") == rid]):
            out.append(f"N3: delegation {rid} spent more times than it has effects")        # M2
    runs_batch = {p["refs"]["run"]: set(p["batch_envs"]) for k, lab, p in case.tel.events
                  if k == "conv_run" and lab == "started"}
    kind_of = {r["id"]: r["kind"] for r in inbox_rows}
    for rid, row in items.items():                                                     # M4
        m = items.get(row["data"].get("mandate", "")) if row["kind"] == "effect" else None
        if m is not None and m["kind"] in ("delegation", "grant"):
            envs = runs_batch.get(row["data"].get("run"), set())
            if not any(kind_of.get(e) in ("user.utterance", "user.text") for e in envs):
                out.append(f"I8: effect {rid} under a {m['kind']} in a run with no content of the person")
    if any(o.text == "w8nv" for o in case.mouth.orders):                              # D9/M3
        out.append("D9: a reply published with a numeric claim that has no value")
    holds = list(snap.scan("holds"))
    for rid, row in items.items():                                                     # M5
        if row["kind"] == "effect" and row["state"] == "claimed" and not any(
                h["t_ms"] >= row["created_ms"] and rid not in h["released"] for _k, h in holds):
            out.append(f"M5: effect {rid} claimed and left: never sent, never withdrawn")
    batch_of, fenced = {}, set()                            # a FENCED batch never runs again unchanged (B1)
    for k, lab, p in case.tel.events:
        if k == "conv_run" and lab == "started":
            b = tuple(p["batch_envs"])
            if b in fenced:
                out.append("I1: a fenced batch ran again unchanged")
                break
            batch_of[p["refs"]["run"]] = b
        elif k == "conv_run" and lab == "fenced":
            fenced.add(batch_of.get(p["refs"]["run"]))
    for r in inbox_rows:                                    # I9: every entry of the person is a request at once
        req = f"r_{r['env']['refs'].get('intervention_id')}"
        if r["kind"] in ("user.utterance", "user.text") and req not in items:
            out.append(f"I9: {r['id']} was accepted and is no request")
        elif r["kind"] in ("user.utterance", "user.text") and r["state"] != "duplicate" and \
                closed_at.get(req, r["accepted"]) < r["accepted"]:
            out.append(f"I9: {r['id']} was accepted after its request {req} had closed (N1)")
    for rid, row in items.items():                                                     # I9
        if row["kind"] == str(ItemKind.REQUEST):
            if row["state"] == "open":
                out.append(f"I9: request {rid} still open")
            if closes.get(rid, 0) != 1:
                out.append(f"I9: request {rid} closed {closes.get(rid, 0)} times")
    return out


def run_case(seed: int, actions: int = 14) -> list[str]:
    case = Case(seed)
    try:
        case.play(actions)
        return check(case)
    finally:
        case.loop.close()
        if case.on_sqlite:
            case.store.close()
