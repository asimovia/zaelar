"""The durable inbox of one account: the PERSON's entries — voice, text, controls — accepted, deduped, held, collected,
one batch at a time (§5.3, I6). What the engine owes the person is not here: it is a line owed (`ports.Owed`).

Every envelope is a row of the `inbox` table in the `Store`, so a suspended Machine or a restarted process finds
what it had accepted. `accept` dedupes by (producer, producer_id) in the same transaction that writes the row. Each
row is in exactly one state:

  queued    waits for a batch                          held      a text waiting behind earlier, open voice
  dequeued  in a batch the manager is running          accounted done, with its outcome: told · silent · expired ·
                                                                 applied (a control, handled by id) · failed ·
                                                                 refused (a control nobody here handles)

Controls never wait: `accept` hands them back at once (`control`) and the manager applies them by id; the voice
intervention stays open and closes as always. A control this manager has no handler for is accounted `refused` in
the transaction that accepts it, with its event — never left for the sweep. Which voice is open the manager tells the inbox (`voice_open`, on the
ear's onset; `voice_done`, on its utterance or its discard): a text waits behind a voice that began before it.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Callable

from conversation import envelopes as E
from conversation.config import Config
from conversation.inbox import ordering
from conversation.ports import Lease, Store
from conversation.telemetry import Emitter
from conversation.types import ControlOp, Coverage, EnvelopeKind, Ids

T = "inbox"
#: the newest entries a question about «just now» reads — never the account's history
RECENT = 64
VOICE = "voice_open"


#: a voice entry the ear cut by its length (`arbiter._incomplete`), and the batch released at the monologue's ceiling
TOO_LONG, MONOLOGUE = "too_long", "monologue"
EVENT_BATCH = "event"        # a batch that is one event of the world, run on its own (R-2)
#: the kinds that are HIS words: what a batch of his is made of (a control is handled on its own, an event runs alone)
WORDS = (str(EnvelopeKind.USER_UTTERANCE), str(EnvelopeKind.USER_TEXT))


class Outcome(Enum):
    """How an accepted envelope ended (I6). `applied`: a control handled by id."""
    TOLD, SILENT, EXPIRED, APPLIED = "told", "silent", "expired", "applied"
    FAILED = "failed"            # its run failed; the request carries the recovery
    REFUSED = "refused"          # a control nobody here handles


class RowState(Enum):
    """The live states of an inbox row; `accounted` is the end."""
    QUEUED, HELD, DEQUEUED, ACCOUNTED = "queued", "held", "dequeued", "accounted"


FINAL = frozenset(m.value for m in Outcome)


@dataclass(frozen=True)
class Batch:
    run_seq: int
    envelopes: tuple[E.Envelope, ...]
    reason: str          # closed · collect_window · cross_channel · incomplete


@dataclass(frozen=True)
class Admission:
    envelope: E.Envelope | None
    disposition: str     # queued · held · control · duplicate · refused (no row) · unhandled (accounted refused)
    extra: object = None  # what the caller's admission hook returned, inside the same transaction


class Inbox:
    def __init__(self, store: Store, lease: Callable[[], Lease], account: str, config: Config, emitter: Emitter,
                 ids: Ids, handles: frozenset = frozenset({ControlOp.STOP})) -> None:
        self.store, self.lease, self.acct, self.cfg, self.em, self.ids = store, lease, account, config, emitter, ids
        self.handles = handles      # the controls the manager has a handler for

    # ── accept ──────────────────────────────────────────────────────────────────────────────────────────────────

    def accept(self, env: E.Envelope, now: int, admit=None, trace: str | None = None) -> Admission:
        """Accept one envelope. `admit(tx, env)` runs INSIDE the same transaction, after the dedupe and before the
        routing — what must be written with the acceptance (the intervention's phase, the request) or not at all.
        `trace`: the flow its events join when it is not its own (a stop joins the flow it stops)."""
        env = replace(env, id=env.id or self.ids.new("e"), accepted_ms=now)
        why = ("not_this_account" if env.account != self.acct else
               "producer_not_of_its_kind" if not E.producer_allowed(env) else None)
        if why is not None:                  # authority follows the producer, and the account is this one
            self._emit("refused", env, cause={"kind": "producer", "ref": env.producer}, reason=why,
                       text=getattr(env.body, "text", None))
            return Admission(None, "refused")
        with self.store.tx(self.lease()) as tx:
            row, new = tx.insert_unique(T, env.id, {**self._row(env), "trace": trace},
                                        f"{env.producer}|{env.producer_id}")
            if not new:
                self._emit("duplicate", env, cause={"kind": "producer", "ref": env.producer},
                           text=getattr(env.body, "text", None))
                return Admission(None, "duplicate")
            # his words travel with their acceptance: the host's record, wall and turns write them from here
            self._emit("accepted", env, trace=trace, **({"text": env.body.text} if env.kind in (
                EnvelopeKind.USER_UTTERANCE, EnvelopeKind.USER_TEXT) else {}))
            extra = admit(tx, env) if admit is not None else None
            disposition = self._route(tx, env, now)
        return Admission(env, disposition, extra)

    def recover(self, now: int) -> list[str]:
        """A new owner of the account: whatever a dead process had dequeued for a run goes back to the queue (its
        run never finished); a control it never handled is closed by the sweep's bound as always."""
        back = []
        with self.store.tx(self.lease()) as tx:
            for key, row in tx.scan(T, states=(RowState.DEQUEUED.value,)):
                if row["kind"] != str(EnvelopeKind.USER_CONTROL):
                    self._move(tx, key, state=RowState.QUEUED.value, batch=None)
                    back.append(key)
        return back

    def _row(self, env: E.Envelope) -> dict:
        return {"id": env.id, "env": E.to_json(env), "kind": str(env.kind), "onset": env.onset_ms,
                "accepted": env.accepted_ms, "state": "queued", "outcome": None, "held_behind": None,
                "hold_until": None, "batch": None}

    def _route(self, tx, env: E.Envelope, now: int) -> str:
        k = env.kind
        if k is EnvelopeKind.USER_CONTROL and env.body.op not in self.handles:
            self._final(tx, env.id, Outcome.REFUSED.value, now, reason="no_handler")
            return "unhandled"
        if k is EnvelopeKind.USER_CONTROL:
            self._move(tx, env.id, state="dequeued")   # handed to the manager; accounted by its handler's transaction
            return "control"
        if k is EnvelopeKind.USER_UTTERANCE:
            self._voice_done(tx, env.body.intervention_id, now)
            return "queued"
        if k is EnvelopeKind.USER_TEXT:
            open_voice = dict(tx.scan(VOICE, states=("open",)))
            iv = ordering.hold_behind(env.onset_ms, open_voice)
            if iv is not None:
                self._move(tx, env.id, state="held", held_behind=iv, hold_until=now + self.cfg.cross_channel_hold_ms)
                self._emit("held", env, refs_extra={"iv": iv}, held_behind=iv)
                return "held"
        return "queued"

    def voice_open(self, iv: str, onset_ms: int, endpoint: str | None, successor: bool = False) -> None:
        """A voice intervention opened (the ear's onset): texts begun after it wait behind it."""
        with self.store.tx(self.lease()) as tx:
            known = tx.get(VOICE, iv) or {"onset": onset_ms, "endpoint": endpoint, "epoch": self.lease().epoch,
                                          "successor": successor}
            tx.put(VOICE, iv, {**known, "state": "open"})

    def voice_heard(self, iv: str) -> None:
        """The open voice brought its first word: a process that dies now leaves a sentence of his, not a silence."""
        with self.store.tx(self.lease()) as tx:
            row = tx.get(VOICE, iv)
            if row is not None:
                tx.put(VOICE, iv, {**row, "heard": True})

    def open_voices(self, before_epoch: int) -> list[tuple[str, dict]]:
        """The voices a dead process left open: opened under an earlier epoch and never ended."""
        with self.store.tx(self.lease()) as tx:
            return [(iv, v) for iv, v in tx.scan(VOICE, states=("open",)) if v.get("epoch", 0) < before_epoch]

    def voice_done(self, iv: str, now: int) -> None:
        """A voice intervention was discarded (no words, a guard): nothing waits behind it any more."""
        with self.store.tx(self.lease()) as tx:
            self._voice_done(tx, iv, now)

    def _voice_done(self, tx, iv: str, now: int) -> None:
        """The voice intervention closed, ended incomplete or was discarded: nothing waits behind it any more."""
        row = tx.get(VOICE, iv)
        if row is not None:
            tx.put(VOICE, iv, {**row, "state": "done"})
        still_open = {v_iv: v for v_iv, v in tx.scan(VOICE, states=("open",)) if v_iv != iv}
        for key, held in tx.scan(T, states=("held",)):
            if held["held_behind"] == iv:
                behind = ordering.hold_behind(held["onset"], still_open)   # another voice begun earlier still open
                if behind is not None:
                    self._move(tx, key, held_behind=behind)
                    continue
                self._move(tx, key, state="queued", held_behind=None, hold_until=None)
                self._emit_row("released", held, held_behind=iv)

    # ── time ────────────────────────────────────────────────────────────────────────────────────────────────────

    def sweep(self, now: int) -> list[str]:
        """Expire holds past their cap (the text runs alone, I4 event with its text); close a control nobody handled."""
        moved = []
        if not any(self._due(row, now) for _k, row in self.store.view(self.acct).scan(T, ("held", "dequeued"))):
            return moved                          # idle: a read, and no transaction is opened
        with self.store.tx(self.lease()) as tx:
            for key, row in tx.scan(T, states=("held", "dequeued")):     # what is in course, never the history
                if row["state"] == "held" and now >= row["hold_until"]:
                    self._move(tx, key, state="queued", held_behind=None, hold_until=None)
                    self._emit_row("expired", row, text=row["env"]["body"].get("text"), held_behind=row["held_behind"],
                                   queue_age_ms=now - row["accepted"])
                    moved.append(key)
                elif (row["state"] == "dequeued" and row["kind"] == str(EnvelopeKind.USER_CONTROL)
                      and now - row["accepted"] >= self.cfg.control_bound_ms):
                    self._final(tx, key, Outcome.EXPIRED.value, now, reason="control_unhandled")
                    moved.append(key)
        return moved

    def _due(self, row: dict, now: int) -> bool:
        return ((row["state"] == "held" and now >= row["hold_until"])
                or (row["state"] == "dequeued" and row["kind"] == str(EnvelopeKind.USER_CONTROL)
                    and now - row["accepted"] >= self.cfg.control_bound_ms))

    # ── out ─────────────────────────────────────────────────────────────────────────────────────────────────────

    def next_batch(self, now: int) -> Batch | None:
        """The next batch to run, or None: every queued entry of HIS, in the order they began — after the collect window
        of the LAST text accepted (two texts in < collect_ms are one batch), and not while the person is still speaking
        on the device of its last entry (`waits_for_voice`). With nothing of his queued, the oldest EVENT runs on its
        own — never while a voice of his is open: an event never goes ahead of his voice (R-2)."""
        queued = [r for _k, r in self.store.view(self.acct).scan(T, ("queued",))]
        if not any(r["kind"] != str(EnvelopeKind.USER_CONTROL) for r in queued):
            return None                           # nothing queued: a read, and no transaction is opened
        with self.store.tx(self.lease()) as tx:
            rows = [r for _k, r in tx.scan(T, states=("queued",))]
            pick = [r for r in rows if r["kind"] in WORDS]
            if not pick:
                return self._event_batch(tx, rows, now)
            texts = [r for r in pick if r["kind"] == str(EnvelopeKind.USER_TEXT)]
            if texts and now - max(r["accepted"] for r in texts) < self.cfg.collect_ms:
                return None                       # the collect window of the last text is still open
            if self._waits_for_voice(tx, pick, now):
                return None
            monologue = self._chained(tx, pick) is not None      # cut by its length, his voice still up, at the cap
            return self._dequeue(tx, pick, MONOLOGUE if monologue else self._reason(pick), now)

    def _event_batch(self, tx, rows: list[dict], now: int) -> Batch | None:
        """The oldest queued event, alone — not while a voice of his is open (he is first, R-2)."""
        events = sorted((r for r in rows if r["kind"] == str(EnvelopeKind.EVENT)), key=lambda r: r["accepted"])
        if not events or any(True for _iv, _v in tx.scan(VOICE, states=("open",))):
            return None
        return self._dequeue(tx, events[:1], EVENT_BATCH, now)

    def _dequeue(self, tx, pick: list[dict], reason: str, now: int) -> Batch:
        seq = tx.next_seq("runs")
        for r in pick:
            self._move(tx, r["id"], state="dequeued", batch=seq)
        pick = ordering.order(pick)
        envs = tuple(E.from_json(r["env"]) for r in pick)
        for r in pick:
            self._emit_row("dequeued", r, batch=seq, queue_age_ms=now - r["accepted"])
        return Batch(seq, envs, reason)

    def _waits_for_voice(self, tx, pick: list[dict], now: int) -> bool:
        """Not yet: a voice entry closed with no sentence mark is not eligible before `nonterminal_start_ms` from its
        close (he goes on, most of the time), and the publication hold applies before a run starts too
        (`ordering.waits_for_voice`, the one predicate)."""
        envs = [r["env"] for r in pick]
        if any(e["kind"] == str(EnvelopeKind.USER_UTTERANCE) and e["body"].get("terminal") is False
               and now - e["sealed_ms"] < self.cfg.nonterminal_start_ms for e in envs):
            return True
        first = self._chained(tx, pick)
        if first is not None:                   # a piece cut by its length, his voice still up: the next piece joins
            return now - first < self.cfg.monologue_max_ms    # it — until the monologue's ceiling, then it runs
        voices = [(iv, v["onset"], v.get("endpoint")) for iv, v in tx.scan(VOICE, states=("open",))]
        return ordering.waits_for_voice([(e["sealed_ms"], e.get("endpoint")) for e in envs], voices, now,
                                        self.cfg.resume_window_ms, self.cfg.resume_hold_max_ms) is not None

    def _chained(self, tx, pick: list[dict]) -> int | None:
        """R3 (plan v3.2 §4): a voice entry cut by its LENGTH (`too_long`) while his voice is still open on its device
        does not run: it waits for the next piece and they enter together. The onset of the batch's first voice entry
        (the monologue's start), or None when nothing chains."""
        envs = [r["env"] for r in pick if r["kind"] == str(EnvelopeKind.USER_UTTERANCE)]
        cut = {e.get("endpoint") for e in envs if e["body"].get("reason") == TOO_LONG}
        if not cut or not any(v.get("endpoint") in cut for _iv, v in tx.scan(VOICE, states=("open",))):
            return None
        return min(e["onset_ms"] for e in envs)

    def words_since(self, t_ms: int) -> bool:
        """Did the person send an entry with words (an utterance or a text) accepted after `t_ms`?"""
        return any(r["kind"] in WORDS and r["accepted"] > t_ms
                   and r["env"]["body"].get("text") for _k, r in self.store.view(self.acct).recent(T, RECENT))

    def in_course(self) -> tuple[frozenset, int | None]:
        """The person's entries not yet accounted — queued, held or in a run: they travel in one batch. Returns their
        interventions and the close of the latest one."""
        rows = [r["env"] for _k, r in self.store.view(self.acct).scan(T, ("queued", "held", "dequeued"))
                if r["kind"] in WORDS]
        return (frozenset(e["refs"]["intervention_id"] for e in rows),
                max((e["sealed_ms"] for e in rows), default=None))

    def pending(self) -> bool:
        """Is there a batch of the person's waiting — queued or held, not yet in a run?"""
        return any(r["kind"] in WORDS for _k, r in self.store.view(self.acct).scan(T, ("queued", "held")))

    def drop_pending(self, now: int) -> list[dict]:
        """A stop while a batch waits (held for a voice, or in the collect window): what waits is accounted `silent`
        (reason `stopped`), as a stop does to a run in course. Returns the rows."""
        with self.store.tx(self.lease()) as tx:
            rows = [r for _k, r in tx.scan(T, states=("queued", "held")) if r["kind"] in WORDS]
            for r in rows:
                self._final(tx, r["id"], Outcome.SILENT.value, now, reason="stopped")
        return rows

    @staticmethod
    def _reason(rows: list[dict]) -> str:
        kinds = {r["kind"] for r in rows}
        if str(EnvelopeKind.USER_UTTERANCE) in kinds and str(EnvelopeKind.USER_TEXT) in kinds:
            return "cross_channel"
        if any(r["env"]["body"].get("coverage") == str(Coverage.INCOMPLETE) for r in rows):
            return "incomplete"
        return "closed" if str(EnvelopeKind.USER_UTTERANCE) in kinds else "collect_window"

    def account(self, env_ids: list[str], outcome: str, now: int, reason: str | None = None) -> None:
        assert outcome in FINAL, outcome
        with self.store.tx(self.lease()) as tx:
            for i in env_ids:
                self._final(tx, i, outcome, now, reason)

    def requeue(self, env_ids: list[str]) -> None:
        """A superseded run gives its batch back: the entries are queued again for the next batch."""
        with self.store.tx(self.lease()) as tx:
            for i in env_ids:
                self._move(tx, i, state="queued", batch=None)

    def applied(self, env_id: str, now: int) -> None:
        """A control handled outside any other transaction (stop, cancel): accounted `applied`."""
        with self.store.tx(self.lease()) as tx:
            apply_control(tx, env_id, now)

    def rows(self) -> list[dict]:
        return [r for _k, r in self.store.snapshot(self.acct).scan(T)]

    # ── helpers ─────────────────────────────────────────────────────────────────────────────────────────────────

    def _move(self, tx, key: str, **fields) -> None:
        row = tx.get(T, key)
        row.update(fields)
        tx.put(T, key, row)

    def _final(self, tx, key: str, outcome: str, now: int, reason: str | None = None) -> None:
        row = tx.get(T, key)
        if row["state"] == "accounted":
            return
        row.update(state="accounted", outcome=outcome, accounted_ms=now, reason=reason)
        tx.put(T, key, row)
        self._emit_row("accounted", row, outcome=outcome, reason=reason)

    def _emit(self, label: str, env: E.Envelope, *, cause: dict | None = None, refs_extra: dict | None = None,
              trace: str | None = None, **payload) -> None:
        refs = {"env": env.id, "iv": env.refs.intervention_id, "task": env.refs.task_id,
                "endpoint": env.endpoint, "channel": str(env.channel), **(refs_extra or {})}
        self.em.emit("conv_inbox", label, owner="inbox", cause=cause or {"kind": "envelope", "ref": env.id},
                     refs=refs, trace=trace, kind=str(env.kind), **payload)

    def _emit_row(self, label: str, row: dict, **payload) -> None:
        refs = row["env"]["refs"]
        self.em.emit("conv_inbox", label, owner="inbox", cause={"kind": "envelope", "ref": row["id"]},
                     refs={"env": row["id"], "iv": refs.get("intervention_id"), "task": refs.get("task_id"),
                           "endpoint": row["env"].get("endpoint"), "channel": row["env"].get("channel")},
                     trace=row.get("trace"), kind=row["kind"], **payload)


def apply_control(tx, env_id: str, now: int) -> None:
    """Account a control `applied` INSIDE the caller's transaction (a confirm spends its handle in the same one)."""
    row = tx.get(T, env_id)
    if row is not None and row["state"] != RowState.ACCOUNTED.value:
        row.update(state=RowState.ACCOUNTED.value, outcome=Outcome.APPLIED.value, accounted_ms=now)
        tx.put(T, env_id, row)
