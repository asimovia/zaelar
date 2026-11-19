"""The durable inbox of one account: accept, dedupe, hold, collect, one batch at a time (§5.3, I6).

Every envelope is a row of the `inbox` table in the `Store`, so a suspended Machine or a restarted process finds
what it had accepted. `accept` dedupes by (producer, producer_id) in the same transaction that writes the row. Each
row is in exactly one state:

  queued    waits for a batch                          held      a text waiting behind earlier, open voice
  deferred  told later, with its next due time         dequeued  in a batch the manager is running
  accounted done, with its outcome: told · coalesced · silent · expired · applied (a control, handled by id)

Controls never wait: `accept` hands them back at once (`control`) and the manager applies them by id; the voice
intervention stays open and closes as always. State envelopes of the ear (opened, tentative, extended) tell the inbox
which voice is open — they are accounted `silent` on arrival; a reopen is handed back (`reopened`) for the policy.
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
from conversation.types import EnvelopeKind, Ids, IvState, Surfacing, WorkerUpdate

T = "inbox"
VOICE = "voice_open"


class Outcome(Enum):
    """How an accepted envelope ended (I6). `applied`: a control handled by id."""
    TOLD, COALESCED, SILENT, EXPIRED, APPLIED = "told", "coalesced", "silent", "expired", "applied"


class RowState(Enum):
    """The live states of an inbox row; `accounted` is the end."""
    QUEUED, HELD, DEFERRED, DEQUEUED, ACCOUNTED = "queued", "held", "deferred", "dequeued", "accounted"


FINAL = frozenset(m.value for m in Outcome)


@dataclass(frozen=True)
class Batch:
    run_seq: int
    envelopes: tuple[E.Envelope, ...]
    reason: str          # closed · collect_window · cross_channel · idle_drain · incomplete


@dataclass(frozen=True)
class Admission:
    envelope: E.Envelope | None
    disposition: str     # queued · held · control · reopened · state · silent · duplicate


class Inbox:
    def __init__(self, store: Store, lease: Callable[[], Lease], account: str, config: Config, emitter: Emitter,
                 ids: Ids) -> None:
        self.store, self.lease, self.acct, self.cfg, self.em, self.ids = store, lease, account, config, emitter, ids

    # ── accept ──────────────────────────────────────────────────────────────────────────────────────────────────

    def accept(self, env: E.Envelope, now: int) -> Admission:
        env = replace(env, id=env.id or self.ids.new("e"), accepted_ms=now)
        with self.store.tx(self.lease()) as tx:
            row, new = tx.insert_unique(T, env.id, self._row(env), f"{env.producer}|{env.producer_id}")
            if not new:
                self._emit("duplicate", env, cause={"kind": "producer", "ref": env.producer})
                return Admission(None, "duplicate")
            self._emit("accepted", env)
            disposition = self._route(tx, env, now)
        return Admission(env, disposition)

    def _row(self, env: E.Envelope) -> dict:
        task = env.body.task_id if env.kind is EnvelopeKind.WORKER_UPDATE else None
        return {"id": env.id, "env": E.to_json(env), "kind": str(env.kind), "onset": env.onset_ms,
                "accepted": env.accepted_ms, "user": env.is_user, "surfacing": str(env.surfacing),
                "must_tell": env.must_tell, "state": "queued", "outcome": None, "held_behind": None,
                "hold_until": None, "due": None, "batch": None, "task": task}

    def _route(self, tx, env: E.Envelope, now: int) -> str:
        k = env.kind
        if k is EnvelopeKind.USER_CONTROL:
            self._move(tx, env.id, state="dequeued")   # handed to the manager; accounted by its handler's transaction
            return "control"
        if k is EnvelopeKind.INTERVENTION_STATE:
            return self._voice_state(tx, env, now)
        if k is EnvelopeKind.USER_UTTERANCE:
            self._voice_done(tx, env.body.intervention_id, now)
            return "queued"
        if k is EnvelopeKind.USER_TEXT:
            open_voice = {iv: v for iv, v in tx.scan(VOICE) if v.get("open")}
            iv = ordering.hold_behind(env.onset_ms, open_voice)
            if iv is not None:
                self._move(tx, env.id, state="held", held_behind=iv, hold_until=now + self.cfg.cross_channel_hold_ms)
                self._emit("held", env, refs_extra={"iv": iv}, held_behind=iv)
                return "held"
            return "queued"
        if env.surfacing is Surfacing.SILENT:
            self._final(tx, env.id, "silent", now)
            return "silent"
        if k is EnvelopeKind.WORKER_UPDATE and env.body.type is WorkerUpdate.PROGRESS:
            self._coalesce(tx, env, now)
        return "queued"

    def _voice_state(self, tx, env: E.Envelope, now: int) -> str:
        b = env.body
        if b.state in (IvState.OPEN, IvState.TENTATIVE):
            known = tx.get(VOICE, b.intervention_id) or {"onset": env.onset_ms, "endpoint": env.endpoint}
            tx.put(VOICE, b.intervention_id, {**known, "open": True})
            self._final(tx, env.id, "silent", now)
            return "reopened" if E.is_reopen(env) else "state"
        self._voice_done(tx, b.intervention_id, now)
        if b.state is IvState.INCOMPLETE:
            return "queued"                       # the run asks for the end
        self._final(tx, env.id, "silent", now)    # discarded: the ear already said so, with text and reason
        return "state"

    def _voice_done(self, tx, iv: str, now: int) -> None:
        """The voice intervention closed, ended incomplete or was discarded: nothing waits behind it any more."""
        row = tx.get(VOICE, iv)
        if row is not None:
            tx.put(VOICE, iv, {**row, "open": False})
        for key, held in tx.scan(T):
            if held["state"] == "held" and held["held_behind"] == iv:
                self._move(tx, key, state="queued", held_behind=None, hold_until=None)
                self._emit_row("released", held, held_behind=iv)

    def _coalesce(self, tx, env: E.Envelope, now: int) -> None:
        for key, row in tx.scan(T):
            if (key != env.id and row["state"] == "queued" and row["task"] == env.body.task_id
                    and row["env"]["body"].get("type") == str(WorkerUpdate.PROGRESS)):
                self._final(tx, key, "coalesced", now)
                self._emit_row("coalesced", row, into=env.id)

    # ── time ────────────────────────────────────────────────────────────────────────────────────────────────────

    def sweep(self, now: int) -> list[str]:
        """Expire holds past their cap (the text runs alone, I4 event with its text); bring deferred rows due."""
        moved = []
        with self.store.tx(self.lease()) as tx:
            for key, row in tx.scan(T):
                if row["state"] == "held" and now >= row["hold_until"]:
                    self._move(tx, key, state="queued", held_behind=None, hold_until=None)
                    self._emit_row("expired", row, text=row["env"]["body"].get("text"), held_behind=row["held_behind"],
                                   queue_age_ms=now - row["accepted"])
                    moved.append(key)
                elif row["state"] == "deferred" and now >= row["due"]:
                    self._move(tx, key, state="queued", due=None)
                    moved.append(key)
                elif (row["state"] == "dequeued" and row["kind"] == str(EnvelopeKind.USER_CONTROL)
                      and now - row["accepted"] >= self.cfg.control_bound_ms):
                    self._final(tx, key, Outcome.EXPIRED.value, now, reason="control_unhandled")
                    moved.append(key)
        return moved

    # ── out ─────────────────────────────────────────────────────────────────────────────────────────────────────

    def next_batch(self, now: int, *, idle: bool) -> Batch | None:
        """The next batch to run, or None. User entries wait out the collect window of the LAST text accepted (two
        texts in < collect_ms are one batch); `when_idle` entries come only when the manager is idle, unless what
        must be told has waited past its cap."""
        with self.store.tx(self.lease()) as tx:
            rows = [r for _k, r in tx.scan(T) if r["state"] == "queued"]
            texts = [r for r in rows if r["kind"] == str(EnvelopeKind.USER_TEXT)]
            if texts and now - max(r["accepted"] for r in texts) < self.cfg.collect_ms:
                return None                       # the collect window of the last text is still open
            pick = [r for r in rows if self._eligible(r, now, idle)]
            if not pick:
                return None
            seq = tx.next_seq("runs")
            for r in pick:
                self._move(tx, r["id"], state="dequeued", batch=seq)
            pick = ordering.order(pick)
            envs = tuple(E.from_json(r["env"]) for r in pick)
            reason = self._reason(pick)
            for r in pick:
                self._emit_row("dequeued", r, batch=seq, queue_age_ms=now - r["accepted"])
            return Batch(seq, envs, reason)

    def _eligible(self, row: dict, now: int, idle: bool) -> bool:
        if row["user"]:
            return True
        if row["surfacing"] == str(Surfacing.NOW):
            return True
        overdue = row["must_tell"] and now - row["accepted"] >= self.cfg.must_tell_max_defer_ms
        return idle or overdue

    @staticmethod
    def _reason(rows: list[dict]) -> str:
        kinds = {r["kind"] for r in rows}
        if str(EnvelopeKind.USER_UTTERANCE) in kinds and str(EnvelopeKind.USER_TEXT) in kinds:
            return "cross_channel"
        if str(EnvelopeKind.USER_UTTERANCE) in kinds:
            return "closed"
        if str(EnvelopeKind.INTERVENTION_STATE) in kinds:
            return "incomplete"
        return "collect_window" if str(EnvelopeKind.USER_TEXT) in kinds else "idle_drain"

    def account(self, env_ids: list[str], outcome: str, now: int) -> None:
        assert outcome in FINAL, outcome
        with self.store.tx(self.lease()) as tx:
            for i in env_ids:
                self._final(tx, i, outcome, now)

    def defer(self, env_id: str, due_ms: int, now: int) -> None:
        """Told later: back to the queue at `due_ms`. Never past the must-tell cap for what must be told."""
        with self.store.tx(self.lease()) as tx:
            row = tx.get(T, env_id)
            if row["must_tell"]:
                due_ms = min(due_ms, row["accepted"] + self.cfg.must_tell_max_defer_ms)
            self._move(tx, env_id, state="deferred", due=due_ms, batch=None)

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
              **payload) -> None:
        refs = {"env": env.id, "iv": env.refs.intervention_id, "rev": env.refs.revision, "task": env.refs.task_id,
                "endpoint": env.endpoint, "channel": str(env.channel), **(refs_extra or {})}
        self.em.emit("conv_inbox", label, owner="inbox", cause=cause or {"kind": "envelope", "ref": env.id},
                     refs=refs, kind=str(env.kind), surfacing=str(env.surfacing), **payload)

    def _emit_row(self, label: str, row: dict, **payload) -> None:
        refs = row["env"]["refs"]
        self.em.emit("conv_inbox", label, owner="inbox", cause={"kind": "envelope", "ref": row["id"]},
                     refs={"env": row["id"], "iv": refs.get("intervention_id"), "task": refs.get("task_id"),
                           "endpoint": row["env"].get("endpoint"), "channel": row["env"].get("channel")},
                     kind=row["kind"], **payload)


def apply_control(tx, env_id: str, now: int) -> None:
    """Account a control `applied` INSIDE the caller's transaction (a confirm spends its handle in the same one)."""
    row = tx.get(T, env_id)
    if row is not None and row["state"] != RowState.ACCOUNTED.value:
        row.update(state=RowState.ACCOUNTED.value, outcome=Outcome.APPLIED.value, accounted_ms=now)
        tx.put(T, env_id, row)
