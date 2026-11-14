"""Grants: who may do what with which item, until when. Default deny — no row, nothing.

A grant is ``{id, item, audience, verbs, expires_at, conditions, created}``:

- `item` an item id or a selector (see `items.selector_matches`)
- `audience` ``contact:<cid>`` | ``group:<gid>`` | ``network``
- `verbs` ⊂ see · subscribe · append · edit · copy
- `expires_at` epoch seconds, 0 = until revoked
- `conditions` reserved (time window, «only while the ride lasts»); unknown conditions DENY

Storage is a seam: `GrantStore` (list/put/delete). The package ships `JsonGrantStore`; the engine replaces it with a
rules-table adapter writing rows `subject:<audience>/a2a/<item>` (V2-857) — post-clean. `Grants.policy` is the second
seam: a callable `(cid, item, verb) -> "allow" | "ask" | "never" | None` that the engine points at
`consent.decide_act`; `None` means «no opinion», and the grant row decides.
"""
from __future__ import annotations

import secrets
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from .items import VERBS, ItemRegistry, selector_matches
from .store import JsonDoc

KNOWN_CONDITIONS: tuple[str, ...] = ()


@dataclass
class Grant:
    item: str
    audience: str
    verbs: list[str]
    expires_at: float = 0.0
    conditions: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: secrets.token_hex(6))
    created: float = field(default_factory=time.time)

    def live(self, now: float) -> bool:
        return not self.expires_at or self.expires_at > now


@dataclass
class Decision:
    allowed: bool
    reason: str               # allow | no_row | expired | verb | policy_ask | policy_never | condition | unknown_item
    grant: Grant | None = None


class GrantStore(Protocol):
    def list(self) -> list[Grant]: ...
    def put(self, g: Grant) -> None: ...
    def delete(self, grant_id: str) -> None: ...


class JsonGrantStore:
    def __init__(self, state_dir: Path):
        self._doc = JsonDoc(Path(state_dir) / "grants.json", {"grants": {}})

    def list(self) -> list[Grant]:
        return [Grant(**g) for g in self._doc.data["grants"].values()]

    def put(self, g: Grant) -> None:
        self._doc.data["grants"][g.id] = asdict(g)
        self._doc.save()

    def delete(self, grant_id: str) -> None:
        if self._doc.data["grants"].pop(grant_id, None) is not None:
            self._doc.save()


def contact_audience(cid: str) -> str:
    return f"contact:{cid}"


class Grants:
    def __init__(self, store: GrantStore, items: ItemRegistry, clock=time.time,
                 groups: Callable[[str], list[str]] | None = None,
                 policy: Callable[[str, str, str], str | None] | None = None):
        self.store, self.items, self._clock = store, items, clock
        self._groups = groups or (lambda cid: [])
        self.policy = policy

    def grant(self, item: str, audience: str, verbs, expires_at: float = 0.0, conditions: dict | None = None) -> Grant:
        verbs = sorted(set(verbs))
        if not verbs or any(v not in VERBS for v in verbs):
            raise ValueError(f"verbs must be a non-empty subset of {VERBS}")
        if ":" not in item and item != "*":
            supported = set(self.items.get(item).verbs)
            if not set(verbs) <= supported:
                raise ValueError(f"{item} supports only {sorted(supported)}")
        if not (audience == "network" or audience.startswith(("contact:", "group:"))):
            raise ValueError("audience must be contact:<id>, group:<id> or network")
        for g in self.store.list():                         # one row per (item, audience): a re-grant replaces it
            if g.item == item and g.audience == audience:
                self.store.delete(g.id)
        g = Grant(item=item, audience=audience, verbs=verbs, expires_at=expires_at, conditions=dict(conditions or {}))
        self.store.put(g)
        return g

    def revoke(self, item: str, audience: str) -> list[Grant]:
        gone = [g for g in self.store.list() if g.item == item and g.audience == audience]
        for g in gone:
            self.store.delete(g.id)
        return gone

    def revoke_all(self, audience: str) -> list[Grant]:
        gone = [g for g in self.store.list() if g.audience == audience]
        for g in gone:
            self.store.delete(g.id)
        return gone

    def for_audience(self, audience: str) -> list[Grant]:
        now = self._clock()
        return [g for g in self.store.list() if g.audience == audience and g.live(now)]

    def sweep(self) -> list[Grant]:
        """Delete expired rows (a temporary share ends by itself)."""
        now = self._clock()
        dead = [g for g in self.store.list() if not g.live(now)]
        for g in dead:
            self.store.delete(g.id)
        return dead

    def allowed(self, cid: str, item_id: str, verb: str) -> Decision:
        if not self.items.has(item_id):
            return Decision(False, "unknown_item")
        item = self.items.get(item_id)
        audiences = {contact_audience(cid), "network", *(f"group:{g}" for g in self._groups(cid))}
        now = self._clock()
        rows = [g for g in self.store.list() if g.audience in audiences and selector_matches(g.item, item)]
        if self.policy is not None:
            verdict = self.policy(cid, item_id, verb)
            if verdict == "never":
                return Decision(False, "policy_never")
            if verdict == "ask":
                return Decision(False, "policy_ask")
        if not rows:
            return Decision(False, "no_row")
        live = [g for g in rows if g.live(now)]
        if not live:
            return Decision(False, "expired")
        for g in live:
            if verb in g.verbs and verb in item.verbs:
                if any(k not in KNOWN_CONDITIONS for k in g.conditions):
                    return Decision(False, "condition", g)
                return Decision(True, "allow", g)
        return Decision(False, "verb")
