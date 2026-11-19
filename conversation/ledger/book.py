"""Operations on the ledger, inside ONE transaction of the `Store` (`Book.tx()`).

Every move goes through the table in `items.py`, as a compare-and-set on the item's state: two writers cannot both
move the same item from the same state. The ledger's events are buffered and emitted only when the transaction
commits — a rolled-back move never says it happened. A taken lease raises `StaleEpoch`, writes nothing and is said
(`conv_ledger/stale_epoch`).
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Callable, Iterator

from conversation.ledger.items import INITIAL, InvalidTransition, check
from conversation.ports import Clock, Conflict, Lease, StaleEpoch, Store, Tx
from conversation.telemetry import Emitter
from conversation.types import ItemKind

T = "items"


class BookTx:
    def __init__(self, tx: Tx, now: int, pending: list) -> None:
        self.tx, self.now, self._pending = tx, now, pending

    def _say(self, label: str, row: dict, cause: dict | None, **payload) -> None:
        refs = {"item": row["id"], "req": row["data"].get("req"), "task": row["data"].get("task_id"),
                "effect": row["id"] if row["kind"] == str(ItemKind.EFFECT) else None, "run": row["data"].get("run")}
        self._pending.append((label, cause or {"kind": "ledger", "ref": row["id"]}, refs,
                              {"item_kind": row["kind"], "owner_of_item": row["owner"],
                                                        "waiting_on": row.get("waiting_on"), **payload}))

    def get(self, item_id: str) -> dict | None:
        return self.tx.get(T, item_id)

    def items(self, kind: ItemKind | None = None, states: tuple[str, ...] | None = None) -> list[dict]:
        return [r for _k, r in self.tx.scan(T) if (kind is None or r["kind"] == str(kind))
                and (states is None or r["state"] in states)]

    def open(self, kind: ItemKind, item_id: str, *, owner: str = "conversation", data: dict | None = None,
             waiting_on: str | None = None, cause: dict | None = None) -> dict:
        existing = self.tx.get(T, item_id)
        if existing is not None:
            return existing                                   # idempotent by id
        row = {"id": item_id, "kind": str(kind), "state": INITIAL[kind], "owner": owner, "data": data or {},
               "waiting_on": waiting_on, "attached": [], "created_ms": self.now, "updated_ms": self.now}
        self.tx.put(T, item_id, row)
        self._say("opened", row, cause, to=row["state"])
        return row

    def open_unique(self, kind: ItemKind, item_id: str, unique: str, *, owner: str = "conversation",
                    data: dict | None = None, cause: dict | None = None) -> tuple[dict, bool]:
        """Open an item under a unique key: a repeat of the same key returns the SAME row, never a second (N3)."""
        row = {"id": item_id, "kind": str(kind), "state": INITIAL[kind], "owner": owner, "data": data or {},
               "waiting_on": None, "attached": [], "created_ms": self.now, "updated_ms": self.now}
        got, new = self.tx.insert_unique(T, item_id, row, unique)
        if new:
            self._say("opened", got, cause, to=got["state"])
        return got, new

    def move(self, item_id: str, to: str, *, cause: dict | None = None, reason: str | None = None,
             data: dict | None = None, waiting_on: str | None = None) -> dict:
        row = self.tx.get(T, item_id)
        if row is None:
            raise InvalidTransition(f"no item {item_id}")
        kind = ItemKind(row["kind"])
        try:
            check(kind, row["state"], to)
        except InvalidTransition:
            self._pending.append(("refused", cause or {"kind": "ledger", "ref": item_id}, {"item": item_id},
                                  {"item_kind": row["kind"], "from": row["state"], "to": to}))
            raise
        new = {"state": to, "updated_ms": self.now, "data": {**row["data"], **(data or {})},
               "waiting_on": waiting_on if waiting_on is not None else row.get("waiting_on")}
        if reason:
            new["reason"] = reason
        if not self.tx.cas(T, item_id, "state", row["state"], new):
            raise Conflict(f"{item_id} moved under us")
        self._say("moved", {**row, **new}, cause, **{"from": row["state"], "to": to, "reason": reason})
        return {**row, **new}

    def attach(self, item_id: str, ref: str, *, decided_by: str, cause: dict | None = None) -> dict:
        """Something joined an item: by its id (`decided_by='id'`) or by the model's command (`'model'`)."""
        row = self.tx.get(T, item_id)
        if row is None:
            raise InvalidTransition(f"no item {item_id}")
        if ref not in row["attached"]:
            row["attached"].append(ref)
            row["updated_ms"] = self.now
            self.tx.put(T, item_id, row)
        self._say("attached", row, cause, decided_by=decided_by, ref=ref)
        return row


class Book:
    def __init__(self, store: Store, lease: Callable[[], Lease], account: str, emitter: Emitter,
                 clock: Clock) -> None:
        self.store, self.lease, self.account, self.em, self.clock = store, lease, account, emitter, clock

    @contextmanager
    def tx(self) -> Iterator[BookTx]:
        pending: list = []
        lease = self.lease()
        try:
            with self.store.tx(lease) as raw:
                yield BookTx(raw, self.clock.now_ms(), pending)
        except StaleEpoch:
            self.em.emit("conv_ledger", "stale_epoch", owner="ledger", cause={"kind": "lease", "ref": lease.owner},
                         epoch_held=lease.epoch)
            raise
        except InvalidTransition:
            self._flush([p for p in pending if p[0] == "refused"])
            raise
        self._flush(pending)

    def say(self, pending: list) -> None:
        """Say the ledger events a transaction of someone else's buffered (`BookTx` over a raw tx), once it committed."""
        self._flush(pending)

    def _flush(self, pending: list) -> None:
        for label, cause, refs, payload in pending:
            self.em.emit("conv_ledger", label, owner="ledger", cause=cause, refs=refs, **payload)

    def snapshot(self):
        return self.store.snapshot(self.account)
