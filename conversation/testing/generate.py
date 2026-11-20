"""P3: a seeded generator of random conversations, and the invariants I1–I9 checked on what each one left behind.

`run_case(seed)` builds a manager over an audited in-memory store and drives it with a random interleaving: voice cut
at random (eager / resumed / an end of turn mid-sentence / a stream that stops), typed texts on another device, stops
from a button or the text field, controls by id nobody here handles, lines owed to the person (a worker's result,
a contact's message, a reminder — held for the voice in their own ledger), jumps of the clock, and a TAKEOVER (another
process acquires the account, the old one keeps being fed). The voice comes with the orders a real provider sends:
its end before the watermark passes the fall, and the person going on right then; a voice that does not fall between
two pieces; a close with the voice still up and its fall an instant later; a background with words and no end. The
model is scripted at random — reads, writes, sends, replies with and without numeric claims, silences, failures — and
injects new input between its own events, so checkpoints are exercised. At the end the signals stop and time runs
out on the manager's own timer (every hold and liveness budget expires) and `check(...)` returns the violations.

Deterministic: one seed, one case. No wall clock, no I/O, standard library only (no Hypothesis).
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
from conversation.testing.fakes import (AckingMouth, FakeClock, FakeOwed, FixedWords, ListTelemetry, NoMemory, RecordingTools,
                                        evidence)
from conversation.testing.scripted_model import ScriptedModel, reply
from conversation.types import Channel, ControlOp, EffectClass, EnvelopeKind, ItemKind

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


def audited(store_class: type) -> type:
    """The same audit over another `Store` (the host's, on sqlite): one case in ten runs on it, so its own paths —
    `BEGIN IMMEDIATE`, a scan by state, the lease — are bombarded too."""
    return type(f"Audited{store_class.__name__}", (_Audited, store_class), {})


#: the numbers the design writes (v3.1 §1.6 bis, §1.6 ter), frozen here: the properties judge against THESE, never
#: against the configuration the case runs with — a value raised out of design must turn a property red
SPEC = {"intervention_max_ms": 30_000, "resume_hold_max_ms": 8000, "resume_window_ms": 20_000,
        "terminal_grace_ms": 3000, "nonterminal_grace_ms": 5000, "nonterminal_start_ms": 1500, "liveness_ms": 30_000,
        "complete_grace_ms": 1000, "incomplete_grace_ms": 6000}


class Case:
    def __init__(self, seed: int, cfg: Config | None = None, sql_store=None) -> None:
        self.rng = random.Random(seed)
        self.seed = seed
        self.cfg = cfg or Config(liveness_ms=SPEC["liveness_ms"], model_first_ms=40, model_gap_ms=40, tool_ms=40,
                                 say_end_ms=8000)
        self.on_sqlite = sql_store is not None and seed % 10 == 3   # chosen by the seed, not the rng
        self.store = sql_store() if self.on_sqlite else AuditedStore()
        self.clock, self.tel = FakeClock(), ListTelemetry()
        self.tools = RecordingTools()
        if self.rng.random() < 0.1:
            self.tools.raises["market_data"] = ValueError("p3: the adapter broke")    # a tool that raises
        self.tools.answers["market_data"] = ToolResult("ok", evidence=(evidence("ev1", "ACME", "q3", "up_days",
                                                                                 "up", 18),))
        self.model = ScriptedModel(default=self._behave)
        self.issued_calls = 0
        self.mouth = AckingMouth(heard_all=self.rng.random() < 0.7)
        self.owed = FakeOwed()
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
                         prefix="P3", ids=None, owed=self.owed, words=FixedWords())
        self.mouth.ack = self._lossy_ack(c)                                 # acks get lost
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
            out.append(lambda: self._safe(self._reopen_mid_run))           # he goes on while it runs
        if r < 0.15:
            self.issued_calls += 1
            out += [ToolCall("c", "market_data", {"q": "w1"}), Done()]
        elif r < 0.30:
            self.issued_calls += 1
            out += [ToolCall("c", "agenda_add", {"what": f"w{self.rng.randint(1, 3)}"}), Done()]
        elif r < 0.42:
            call = ToolCall("c", "send_message", {"to": "c1", "via": "chat", "text": "w5"})
            twice = self.rng.random() < 0.3                                     # the same call again
            self.issued_calls += 2 if twice else 1
            out += [call, call, Done()] if twice else [call, Done()]
        elif r < 0.52:
            claim = {"entity": "ACME", "period": "q3", "metric": "up_days", "value": 18, "evidence_id": "ev1",
                     "direction": self.rng.choice(["up", "down"])}
            if self.rng.random() < 0.2:
                claim.pop("value")                                                 # a number with no value
            out += [reply("w8nv" if "value" not in claim else "w8", [claim], **self._reading()), Done()]
        elif r < 0.60:
            out += [Command("no_reply", {"reason": "p3", **self._reading()}), Done()]
        elif r < 0.65:
            out += [Failed("p3", "provider")]
        elif r < 0.654:
            out += [self._hang(), reply("w0"), Done()]                       # a provider that hangs
        else:
            out += [reply(f"w{self.rng.randint(10, 99)}. w{self.rng.randint(10, 99)}?", **self._reading()), Done()]
        return out

    def _reading(self) -> dict:
        """The model's reading of the thought (§1.6 quater): answerable, something missing, no field, or a value that
        is not a boolean."""
        return self.rng.choice([{"complete": True}, {"complete": False}, {}, {"complete": "w"}])

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
                if conv.pumpable and (conv.dirty or isinstance(one, S.Tick)):
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
                if self.rng.random() < 0.5:                                  # …with the voice falling there
                    self._feed(conv, S.VadEdge(ep, "fall", t + 10), S.Watermark(ep, t + 280),
                               S.EotHint(ep, "flux", "end", .7, t + 300))
                else:                                                        # …or another voice keeps it up
                    self._feed(conv, S.Watermark(ep, t + 280), S.EotHint(ep, "flux", "end", .7, t + 300))
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
        end = self.rng.random()
        mark = self.rng.choice([True, True, False, None])   # how the provider closed it: a sentence end, none, unknown
        if end < 0.2:                       # the end lands before the watermark passes the fall; he may go on at once
            self._feed(conv, S.VadEdge(ep, "fall", t + 250), S.EotHint(ep, "flux", "end", .9, t + 200, mark))
            if self.rng.random() < 0.5:
                self._feed(conv, S.VadEdge(ep, "rise", t + 228))
                self._go_on_unfinished(conv, ep=ep, rose=True)
            self._feed(conv, *[S.Watermark(ep, x) for x in range(t + 300, t + 700, 240)])
        elif end < 0.35:                    # the end with the voice still up, its fall an instant later
            self._feed(conv, S.Watermark(ep, t + 100), S.EotHint(ep, "flux", "end", .9, t + 200, mark),
                       S.VadEdge(ep, "fall", t + 200 + self.rng.choice([5, 30, 120, 400])),
                       *[S.Watermark(ep, x) for x in range(t + 340, t + 900, 240)])
        else:
            self._feed(conv, S.VadEdge(ep, "fall", t + 10), *[S.Watermark(ep, x) for x in range(t + 60, t + 400, 240)],
                       S.EotHint(ep, "flux", "end", .9, t + 400, mark))

    def _envelope(self, conv: Conversation, kind: EnvelopeKind, body, *, channel=None, endpoint=None) -> None:
        self.n += 1
        conv.give(E.make(kind, body, producer=f"{E.KINDS[kind][3][0]}p3", producer_id=f"{self.n}", account=ACCT,
                         onset_ms=self._now(), sealed_ms=self._now(), channel=channel, endpoint=endpoint,
                         refs=E.Refs(task_id=getattr(body, "task_id", None))))
        if conv.current is None or conv.pumpable:
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
        elif a < 0.62:                                   # a control by id this manager has no handler for
            op = self.rng.choice([ControlOp.CONFIRM, ControlOp.DECLINE, ControlOp.DELEGATE, ControlOp.CANCEL_TASK])
            self._envelope(conv, EnvelopeKind.USER_CONTROL,
                           E.ControlBody(op, handle_id="h_none", task_id="t_none", gesture=self.rng.random() < 0.6),
                           channel=Channel.BUTTON, endpoint="d1")
        elif a < 0.86:                                   # a line owed: a worker's result, a contact, a reminder
            self.n += 1
            self.owed.add(f"n{self.n}", f"w{self.rng.randint(1, 60)}", self._now())
            if conv.current is None or conv.pumpable:
                self.loop.run_until_complete(conv.pump())
        elif a < 0.91:
            self._race_seal(conv)
        elif a < 0.94:
            self._redeliver(conv)                                                # an adapter re-delivers
        elif a < 0.955:
            self._go_on_unfinished(conv)                                         # he goes on, unfinished
        elif a < 0.965:
            self._forge(conv)                                                    # a forged producer / account
        elif a < 0.975:
            self._background(conv)                                               # a TV that never stops
        elif a < 0.98:
            self._late_turn(conv)                    # the same final delivered again, or the turn grown after a cap
        elif a < 0.985:
            self._two_devices(conv)                  # two voices close at once; he goes on on one of them
        elif a < 0.99:
            self._fan(conv)                          # a noise that keeps rising with no word, cutting our lines
        elif a < 0.994:
            self._monologue(conv)                    # a long thought in pieces with no mark, past the liveness
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

    def _go_on_unfinished(self, conv: Conversation, ep: str = "d1", rose: bool = False) -> None:
        """The person goes on after a close with a word and no end yet, and the provider keeps beating."""
        t = self._now() + 20
        self.seq += 1
        ws = ((f"w{self.rng.randint(1, 60)}", t, t + 160, 1.0),)
        self._feed(conv, *([] if rose else [S.VadEdge(ep, "rise", t)]),
                   S.WordSpan(ep, self.seq, 1, False, ws, (t, t + 160)),
                   *[S.Watermark(ep, x) for x in range(t + 200, t + 2500, 240)])

    def _late_turn(self, conv: Conversation) -> None:
        """A provider turn whose intervention already ended comes back: the same final again (nothing new), or grown
        by a word after the ear closed it at its cap."""
        ep, t = "d1", self._now() + 20
        self.seq += 1
        seq = self.seq
        ws = tuple((f"w{self.rng.randint(1, 60)}", t + i * 180, t + i * 180 + 160, 1.0) for i in range(2))
        self._feed(conv, S.VadEdge(ep, "rise", t), S.WordSpan(ep, seq, 1, True, ws, (t, ws[-1][2])),
                   S.VadEdge(ep, "fall", ws[-1][2] + 10),
                   *[S.Watermark(ep, x) for x in range(ws[-1][2] + 60, ws[-1][2] + 2900, 240)])
        end = ws[-1][2] + 3000
        if self.rng.random() < 0.5:
            self._feed(conv, S.WordSpan(ep, seq, self.rng.choice([1, 2]), True, ws, (t, ws[-1][2])), S.Tick(end))
        else:
            grown = ws + ((f"w{self.rng.randint(1, 60)}", end, end + 160, 1.0),)
            self._feed(conv, S.WordSpan(ep, seq, 2, True, grown, (t, end + 160)), S.Watermark(ep, end + 300),
                       S.EotHint(ep, "flux", "end", .9, end + 320, True))

    def _monologue(self, conv: Conversation) -> None:
        """A long thought said in pieces with no sentence mark (the profile: p90 7 pieces, pauses up to 5 s): longer in
        all than the liveness, every piece within the grace of the one before."""
        ep = "d1"
        for _ in range(self.rng.randint(7, 12)):
            t = self._now() + 20
            self.seq += 1
            ws = tuple((f"w{self.rng.randint(1, 60)}", t + i * 180, t + i * 180 + 160, 1.0) for i in range(2))
            end = ws[-1][2]
            self._feed(conv, S.VadEdge(ep, "rise", t), S.WordSpan(ep, self.seq, 1, True, ws, (t, end)),
                       S.VadEdge(ep, "fall", end + 10), S.Watermark(ep, end + 60),
                       S.EotHint(ep, "flux", "end", .8, end + 80, False))
            gap = self.rng.choice([3000, 4000, 4500])
            self._feed(conv, *[S.Tick(x) for x in range(end + 300, end + gap, 500)])

    def _two_devices(self, conv: Conversation) -> None:
        """Two voices close at the same instant on two devices; he goes on on one of them and keeps talking."""
        t = self._now() + 20
        for ep in ("d1", "d2"):
            self.seq += 1
            ws = ((f"w{self.rng.randint(1, 60)}", t, t + 160, 1.0),)
            self._feed(conv, S.VadEdge(ep, "rise", t), S.WordSpan(ep, self.seq, 1, True, ws, (t, t + 160)),
                       S.VadEdge(ep, "fall", t + 170), S.Watermark(ep, t + 200))
        for ep in ("d1", "d2"):
            self._feed(conv, S.EotHint(ep, "flux", "end", .9, t + 300, True))
        ep, x = self.rng.choice(["d1", "d2"]), t + 300 + self.rng.choice([30, 800, 2500])
        self.seq += 1
        self._feed(conv, S.VadEdge(ep, "rise", x),
                   S.WordSpan(ep, self.seq, 1, False, ((f"w{self.rng.randint(1, 60)}", x, x + 160, 1.0),),
                              (x, x + 160)), *[S.Watermark(ep, y) for y in range(x + 200, x + 4000, 240)])

    def _fan(self, conv: Conversation) -> None:
        """A noise that keeps rising with no word (a fan, an echo leak): each rise cuts the line in course, each fall
        ends a voice that brought nothing."""
        from conversation.mouth import SayEnded
        ep = "d1"
        for _ in range(self.rng.randint(2, 6)):
            t = self._now() + 20
            live = conv.speaker.live_line()
            self._feed(conv, S.VadEdge(ep, "rise", t))
            if live is not None:
                conv.ack(SayEnded(live["say_id"], "cut", self.rng.choice([0, 3, len(live["text"]) // 2]), t + 10,
                                  live.get("endpoint"), "agent_estimate"))
            self._feed(conv, S.VadEdge(ep, "fall", t + 120), S.Tick(t + 120 + self.cfg.close_cap_ms + 10))

    def _background(self, conv: Conversation) -> None:
        """A background that keeps talking: the voice up, words every 400 ms, never an end, never a fall."""
        ep, t = self.rng.choice(["d1", "d2"]), self._now() + 20
        self._feed(conv, S.VadEdge(ep, "rise", t))
        for i in range(self.rng.choice([10, 40, 90])):
            self.seq += 1
            x = t + i * 400
            self._feed(conv, S.WordSpan(ep, self.seq, 1, True, ((f"w{self.rng.randint(1, 60)}", x, x + 300, 1.0),),
                                        (x, x + 300)), S.Watermark(ep, x + 380))

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
        """The signals stop: no new input, not even a tick for the ear — only the manager's own timer, every 5 s (as
        `keep_time` would); every hold and budget expires and whatever is ready runs."""
        self.draining = True
        self.drain_from = self._now()
        span = 2 * max(self.cfg.liveness_ms, self.cfg.cross_channel_hold_ms, self.cfg.intervention_max_ms)
        for _ in range(span // DRAIN_STEP_MS + 1):
            self.clock.advance(DRAIN_STEP_MS)
            self.conv.sweep()
            self.loop.run_until_complete(self.conv.pump())
            self.owed.expire(self.clock.now_ms())          # the ledger's pulse: a claim past its deadline goes back


DRAIN_STEP_MS = 5000


def _held_voice_spoken_over(case, events, inbox_rows) -> list[str]:
    """A line of a run said, or a run started, while a voice that holds its batch is open — the rule as the design
    writes it, not as the code does: a voice open on ANY device that contributed an entry to the batch, begun within
    the window of the last entry that device contributed, before the bound counted from the batch's last close."""
    envs = {r["id"]: r["env"] for r in inbox_rows}
    opened, ended, batch, out = {}, {}, {}, []
    for k, lab, p in events:
        r = p["refs"]
        if k == "conv_ear" and lab == "onset":
            opened[r["iv"]] = (p["t_onset_ms"], r.get("endpoint"))
        elif k == "conv_ear" and lab in ("closed", "incomplete", "discarded"):
            ended.setdefault(r.get("iv"), p["t_ms"])
        elif k == "conv_run" and lab == "started":
            batch[r["run"]] = [envs[e] for e in p["batch_envs"] if e in envs and envs[e]["kind"] != "user.control"]
        if not ((k == "conv_mouth" and lab == "say" or k == "conv_run" and lab == "started") and batch.get(r.get("run"))):
            continue
        t, entries = p["t_ms"], batch[r["run"]]       # neither a line said, nor a run started, with his voice open
        if t - max(e["sealed_ms"] for e in entries) >= SPEC["resume_hold_max_ms"]:
            continue
        own = {e["refs"]["intervention_id"] for e in entries}
        for iv, (on, ep) in opened.items():
            last_there = [e["sealed_ms"] for e in entries if e.get("endpoint") == ep]
            if (iv not in own and last_there and on - max(last_there) <= SPEC["resume_window_ms"]
                    and on <= t < ended.get(iv, 10 ** 18)):
                out.append(f"held: {r['run']} {lab} at {t} over {iv} open on {ep}")
    return out


def _due(voice: list[dict], complete) -> int | None:
    """When a batch's order may go out, from the design's numbers: the model's reading if it was a boolean (§1.6
    quater), the marks' graces otherwise (§1.6 ter)."""
    if not voice:
        return None
    if isinstance(complete, bool):
        return max(e["sealed_ms"] for e in voice) + SPEC["complete_grace_ms" if complete else "incomplete_grace_ms"]
    return max(e["sealed_ms"] + SPEC["nonterminal_grace_ms" if e["body"].get("terminal") is False
                                     else "terminal_grace_ms"] for e in voice)


def _graces(case, inbox_rows) -> list[str]:
    """§1.6 ter and quater, judged from the design's numbers (the review of A6c): no voice reply — and no silent close
    the model read as incomplete — before the grace its batch got; at most one line per run; no run before `nonterminal_start` after a close with no mark; no line of a run after a stop accepted in its
    flow; a reply waiting for its grace and superseded by a new entry of his is never said; no line owed and no
    resumed line while a reply waits for its grace."""
    envs = {r["id"]: r["env"] for r in inbox_rows}
    batch, trace, stopped, parked, out = {}, {}, {}, {}, []
    reading: dict = {}                                     # run → the model's last reading of the thought
    lines: dict = {}
    resumed: dict = {}                                     # a line is resumed once, and a resumption never
    for k, lab, p in case.tel.events:
        if k == "conv_mouth" and lab == "say" and p.get("resumes"):
            resumed[p["resumes"]] = resumed.get(p["resumes"], 0) + 1
            resumed.setdefault("_said", set()).add(p["refs"]["say"])
    out += [f"resume: {sid} resumed {n} times" for sid, n in resumed.items() if sid != "_said" and n > 1]
    out += [f"resume: a resumption {sid} resumed again" for sid in resumed if sid in resumed.get("_said", ())]
    for k, lab, p in case.tel.events:
        r, t = p["refs"], p["t_ms"]
        if k == "conv_run" and lab == "started":
            batch[r["run"]], trace[r["run"]] = [envs[e] for e in p["batch_envs"] if e in envs], p["trace"]
            early = [e for e in batch[r["run"]] if e["kind"] == "user.utterance" and e["body"].get("terminal") is False
                     and t - e["sealed_ms"] < SPEC["nonterminal_start_ms"]]
            if early:
                out.append(f"grace: {r['run']} started {t - early[0]['sealed_ms']} ms after a close with no mark")
        elif k == "conv_run" and lab == "command" and p.get("command") in ("reply", "no_reply"):
            reading[r["run"]] = p.get("complete")
        elif k == "conv_close" and lab == "silent" and reading.get(r.get("run")) is False and r.get("run") in batch:
            due = _due([e for e in batch[r["run"]] if e["kind"] == "user.utterance"], False)
            if due is not None and t < due and p.get("reason") == "p3":          # the model's own no_reply
                out.append(f"grace: {r['run']} closed silent at {t}, before its grace at {due}")
        elif k == "conv_run" and lab == "held" and p.get("waits_for") == "grace":
            parked[r["run"]] = None
        elif k == "conv_run" and r.get("run") in parked and lab in ("held", "superseded", "cancelled", "ended"):
            parked.pop(r["run"])
        elif k == "conv_inbox" and lab == "accepted":
            if p.get("kind") == "user.control":
                stopped.update({run: t for run, tr in trace.items() if tr == p["trace"] and run not in stopped})
            else:
                parked.update({run: t for run, at in parked.items() if at is None})
        elif k == "conv_mouth" and lab == "say":
            run = r.get("run")
            if (p.get("notice_key") or p.get("resumes")) and parked:
                out.append(f"grace: a line owed or resumed at {t} while {sorted(parked)[0]} waits")
            elif run in batch and not p.get("resumes"):
                lines[run] = lines.get(run, 0) + 1                  # a resumption is the same line again

                if lines[run] > 1:
                    out.append(f"grace: {run} said {lines[run]} lines")
                due = _due([e for e in batch[run] if e["kind"] == "user.utterance"], reading.get(run))
                if due is not None and t < due:
                    out.append(f"grace: {run} said at {t}, before its grace at {due}")
                if run in stopped and t >= stopped[run]:
                    out.append(f"stop: {run} said at {t} after a stop at {stopped[run]}")
                if parked.get(run) is not None:
                    out.append(f"grace: {run} said after an entry at {parked[run]} during its grace")
    return out


def _stalled_while_he_spoke(case, inbox_rows) -> list[str]:
    """v3.1 §1.6: a request is never `stalled` while a continuation of his that travels in
    its batch closed within the budget — waiting for him to finish a thought said in pieces is not stalling."""
    sealed = {r["id"]: r["env"]["sealed_ms"] for r in inbox_rows}
    iv_of = {r["id"]: r["env"]["refs"]["intervention_id"] for r in inbox_rows}
    batches = [p["batch_envs"] for k, lab, p in case.tel.events if k == "conv_run" and lab == "started"]
    out = []
    for k, lab, p in case.tel.events:
        if k != "conv_close" or lab != "stalled":
            continue
        t, req = p["t_ms"], p["refs"].get("req")
        mates = {e for b in batches if any(f"r_{iv_of.get(x)}" == req for x in b) for e in b}
        late = [e for e in mates if t - SPEC["liveness_ms"] < sealed.get(e, -1) <= t]
        if late:
            out.append(f"I9: {req} stalled at {t} with a continuation of his closed at {sealed[late[0]]}")
    return out


def _flows_batches_and_bounds(case, inbox_rows) -> list[str]:
    """The properties of v3.1 over what a case left: every event in a flow, a request a run closed carries it, an entry
    in at most one batch that ended, nothing said over his resumed voice, no turn past its maximum, and — once the
    signals stop — every request ended within its liveness."""
    out: list[str] = []
    blank = [f"{k}/{lab}" for k, lab, p in case.tel.events if not p.get("trace")]      # every event in a flow
    if blank:
        out.append(f"trace: {len(blank)} events outside any flow, first {blank[0]}")
    run_trace = {p["refs"]["run"]: p["trace"] for k, lab, p in case.tel.events if k == "conv_run" and lab == "started"}
    for k, lab, p in case.tel.events:                       # a request a run closed joins that run's flow
        if k != "conv_close":
            continue
        run = p["refs"].get("run")
        if lab == "answered" and not run:
            out.append(f"trace: {p['refs'].get('req')} answered by no run")
        elif run and run_trace.get(run) != p["trace"]:
            out.append(f"trace: {p['refs'].get('req')} closed by {run} outside its flow")
    if case.old is None:                                    # no intervention gathers words past its maximum
        onsets = {p["refs"]["iv"]: p["t_onset_ms"] for k, lab, p in case.tel.events
                  if k == "conv_ear" and lab == "onset"}
        for iv, on in onsets.items():                       # gathered over several provider turns: one turn that
            words = case.conv.ear.spans.words(iv)           # arrives whole is the provider's, not the ear's doing
            if len(case.conv.ear.spans.seqs(iv)) > 1 and words[-1][2] - on > SPEC["intervention_max_ms"] + 1000:
                out.append(f"ear: {iv} gathered words for {words[-1][2] - on} ms")
    delivered: dict = {}                                    # I2: a word reaches the inbox in one utterance only
    for r in inbox_rows:
        if r["kind"] == "user.utterance":
            for w in r["env"]["body"]["spans"]:
                delivered.setdefault((r["env"].get("endpoint"), w[0], w[1], w[2]), set()).add(r["id"])
    out += [f"I2: word {w[1]} delivered in {sorted(ids)}" for w, ids in delivered.items() if len(ids) > 1][:3]
    accounted_in: dict = {}                                 # I6: an entry is in at most one batch that ended
    run_envs = {p["refs"]["run"]: p["batch_envs"] for k, lab, p in case.tel.events
                if k == "conv_run" and lab == "started"}
    for k, lab, p in case.tel.events:
        if k == "conv_run" and lab in ("ended", "cancelled"):
            for env in run_envs.get(p["refs"]["run"], ()):
                accounted_in.setdefault(env, set()).add(p["refs"]["run"])
    out += [f"I6: {env} accounted by two runs" for env, runs in accounted_in.items() if len(runs) > 1]
    if case.old is None:                                    # a takeover's two processes share no ear: not judged
        out += _held_voice_spoken_over(case, case.tel.events, inbox_rows)
    drain_from = getattr(case, "drain_from", None)          # I9: once the signals stop, everything ends in time
    if drain_from is not None:
        for k, lab, p in case.tel.events:
            if k == "conv_close" and p["t_ms"] > drain_from:
                start = max(p["t_ms"] - p["total_ms"], drain_from)
                if p["t_ms"] - start > SPEC["liveness_ms"] + DRAIN_STEP_MS:
                    out.append(f"I9: {p['refs'].get('req')} ended {p['t_ms'] - start} ms after the signals stopped")
    return out


def _never_silent(case) -> list[str]:
    """Never silence: a request that ends `stalled` or `recovered` was answered with the failure line in place (a line
    its run said) or is owed it — never closed with nothing heard. A `silent` close is the model's order (no_reply) or
    his stop, never the manager's."""
    said = {o.run_id for o in case.mouth.orders}
    owed = set(getattr(getattr(case, "owed", None), "rows", {}) or {})
    out = []
    for k, lab, p in case.tel.events:
        if k == "conv_close" and lab in ("stalled", "recovered"):
            req, run_id = p["refs"].get("req"), p["refs"].get("run")
            if run_id not in said and f"conv:failed:{req}" not in owed:
                out.append(f"silence: {req} closed {lab} with nothing heard and nothing owed")
    return out


def _half_thought_heard(case) -> list[str]:
    """Half a thought whose rest never came never ends with nothing said: a run the model read as incomplete
    (`complete: false`) that closes silent on its own order is a violation — unless our last answer was already the
    «go on, I'm listening» line (never twice in a row)."""
    reading, listening, last_listening, out = {}, set(), False, []
    for k, lab, p in case.tel.events:
        r = p.get("refs") or {}
        if k == "conv_run" and lab == "command" and p.get("command") in ("reply", "no_reply"):
            reading[r.get("run")] = p.get("complete")
        elif k == "conv_run" and lab == "command" and p.get("command") == "listening":
            listening.add(r.get("run"))
        elif k == "conv_mouth" and lab == "say" and not str(r.get("run") or "").startswith("owed:"):
            last_listening = r.get("run") in listening
        elif (k == "conv_close" and lab == "silent" and p.get("reason") == "p3" and reading.get(r.get("run")) is False
              and not last_listening):
            out.append(f"half a thought: {r.get('req')} closed silent on a reading of incomplete, nothing said")
    return out


def check(case: Case) -> list[str]:
    """I1–I9 over what the case left behind. Each violation is one sentence."""
    out = [f"crash: {c}" for c in case.crashes]
    snap = case.store.snapshot(getattr(case, "account", ACCT))
    items = {k: r for k, r in snap.scan("items")}
    phases = {k: r["phase"] for k, r in snap.scan("interventions")}
    classes = {t.name: t.effect_class for t in case.tools.catalog()}
    for eid, row in items.items():
        if row["kind"] != str(ItemKind.EFFECT):
            continue
        for iv in row["data"].get("ivs", []):                                        # I1
            if phases.get(iv) not in ("sealed", "final"):
                out.append(f"I1: effect {eid} rests on {iv} in phase {phases.get(iv)}")
        if classes.get(row["data"].get("tool")) is not EffectClass.WRITE:             # I8: only a local act reserves
            out.append(f"I8: effect {eid} reserved for {row['data'].get('tool')}, which is no local act")
        if not row["data"].get("ivs"):
            out.append(f"I8: effect {eid} rests on no entry of the person's")
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
    sent: dict[str, int] = {}
    for name, _args, effect_id in case.tools.calls:     # I8: a read, or a local act by its reservation — and once
        if classes.get(name) is EffectClass.READ and effect_id is None:
            continue
        if classes.get(name) is EffectClass.WRITE and effect_id in items:
            sent[effect_id] = sent.get(effect_id, 0) + 1
            if sent[effect_id] == 2:
                out.append(f"I8: {effect_id} reached the tools twice")
            continue
        out.append(f"I8: {name} reached the tools outside its class or its reservation")
    closes: dict[str, int] = {}
    closed_at: dict[str, int] = {}
    for k, lab, p in case.tel.events:
        if k == "conv_close":
            closes[p["refs"]["req"]] = closes.get(p["refs"]["req"], 0) + 1
            closed_at.setdefault(p["refs"]["req"], p["t_ms"])
    for r in inbox_rows:                                                               # I8: the producer is of its kind
        if not r["env"]["producer"].startswith(E.KINDS[EnvelopeKind(r["kind"])][3]) or \
                r["env"]["account"] != getattr(case, "account", ACCT):
            out.append(f"I8: {r['id']} accepted from {r['env']['producer']} for {r['env']['account']}")
    for r in inbox_rows:                                    # I6: a control with no handler is refused at once
        if r["kind"] == "user.control" and r["env"]["body"]["op"] != "stop" and r["state"] == "accounted" and \
                (r["outcome"], r.get("accounted_ms")) != ("refused", r["accepted"]):
            out.append(f"I6: control {r['id']} with no handler ended {r['outcome']}, not refused when accepted")
    if any(o.text == "w8nv" for o in case.mouth.orders):                              # a claim with no value
        out.append("claims: a reply published with a numeric claim that has no value")
    batch_of, fenced = {}, set()                            # a FENCED batch never runs again unchanged
    for k, lab, p in case.tel.events:
        if k == "conv_run" and lab == "started":
            b = tuple(p["batch_envs"])
            if b in fenced:
                out.append("I1: a fenced batch ran again unchanged")
                break
            batch_of[p["refs"]["run"]] = b
        elif k == "conv_run" and lab == "fenced":
            fenced.add(batch_of.get(p["refs"]["run"]))
    owed = getattr(case, "owed", None)                      # I6, the ledger of what is owed
    if owed is not None:
        said: dict = {}
        for o in case.mouth.orders:
            if o.notice_key:
                said[o.notice_key] = said.get(o.notice_key, 0) + 1
        out += [f"I6: owed line {k} said {n} times" for k, n in said.items() if n > 1]
        out += [f"I6: owed line {k} spoken and never said" for k, r in owed.rows.items()
                if r["state"] == "spoken" and not said.get(k)]
        out += [f"I6: owed line {k} still claimed at the end" for k, r in owed.rows.items() if r["state"] == "claimed"]
    for r in inbox_rows:                                    # I9: every entry of the person is a request at once
        req = f"r_{r['env']['refs'].get('intervention_id')}"
        if r["kind"] in ("user.utterance", "user.text") and req not in items:
            out.append(f"I9: {r['id']} was accepted and is no request")
        elif r["kind"] in ("user.utterance", "user.text") and r["state"] != "duplicate" and \
                closed_at.get(req, r["accepted"]) < r["accepted"]:
            out.append(f"I9: {r['id']} was accepted after its request {req} had closed")
    out += _flows_batches_and_bounds(case, inbox_rows)
    out += _stalled_while_he_spoke(case, inbox_rows)
    out += _never_silent(case)
    out += _half_thought_heard(case)
    out += [f"empty item: {c.run_id} was prompted with an entry that has no words" for c in case.model.calls
            if "«»" in c.prompt.input]
    if case.old is None:
        out += _graces(case, inbox_rows)
    for rid, row in items.items():                                                     # I9
        if row["kind"] == str(ItemKind.REQUEST):
            if row["state"] == "open":
                out.append(f"I9: request {rid} still open")
            if closes.get(rid, 0) != 1:
                out.append(f"I9: request {rid} closed {closes.get(rid, 0)} times")
    return out


def run_case(seed: int, actions: int = 14, sql_store=None) -> list[str]:
    """`sql_store`: a factory of an AUDITED store over sqlite (`audited(…)`), used one case in ten."""
    case = Case(seed, sql_store=sql_store)
    try:
        case.play(actions)
        return check(case)
    finally:
        case.loop.close()
        if case.on_sqlite:
            case.store.close()
