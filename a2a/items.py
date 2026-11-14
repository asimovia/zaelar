"""Shareable items: the TYPED resources an agent may expose to other agents. What is not declared cannot be shared.

An item is ``{id, kind, owner_widget, schema, verbs, projections}``:

- `kind` ∈ collection | stream | file | calendar | profile | widget-data
- `verbs` the item supports at all (a grant can only give a subset): see · subscribe · append · edit · copy
- `projections` name → reader. A reader gets the query `args` and returns JSON-able data; the projection decides
  what may leave (e.g. calendar `freebusy` = intervals only, never titles). The default projection is `default`.

The first instances (messages, calendar/freebusy, profile/public, activity.live) are registered by
`default_items()`; every widget can declare its own with `ItemRegistry.declare` (post-clean: from its manifest).
Never declarable: episodic memory, the diary, vault/secrets, connector credentials, rules, state.
"""
from __future__ import annotations

from loguru import logger

from dataclasses import dataclass, field
from typing import Any, Callable

KINDS = ("collection", "stream", "file", "calendar", "profile", "widget-data")
VERBS = ("see", "subscribe", "append", "edit", "copy")
NEVER_SHAREABLE = ("memory", "diary", "vault", "credentials", "rules", "state")

Reader = Callable[[dict], Any]


class UnknownItem(KeyError):
    pass


@dataclass
class Item:
    id: str
    kind: str
    owner_widget: str
    schema: str
    verbs: tuple[str, ...]
    projections: dict[str, Reader] = field(default_factory=dict)

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"unknown item kind {self.kind!r}")
        if any(v not in VERBS for v in self.verbs):
            raise ValueError(f"unknown verb in {self.verbs!r}")
        root = self.id.split(".")[0].split("/")[0]
        if root in NEVER_SHAREABLE or self.owner_widget in NEVER_SHAREABLE:
            raise ValueError(f"{self.id!r} can never be shared")

    def read(self, projection: str, args: dict) -> Any:
        fn = self.projections.get(projection or "default")
        if fn is None:
            raise UnknownItem(f"{self.id}:{projection}")
        return fn(args or {})

    def card(self) -> dict:
        return {"id": self.id, "kind": self.kind, "owner_widget": self.owner_widget, "schema": self.schema,
                "verbs": list(self.verbs), "projections": sorted(self.projections)}


class ItemRegistry:
    def __init__(self):
        self._items: dict[str, Item] = {}

    def declare(self, item: Item) -> Item:
        self._items[item.id] = item
        return item

    def get(self, item_id: str) -> Item:
        try:
            return self._items[item_id]
        except KeyError:
            raise UnknownItem(item_id) from None

    def has(self, item_id: str) -> bool:
        return item_id in self._items

    def all(self) -> list[Item]:
        return list(self._items.values())

    def matching(self, selector: str) -> list[Item]:
        return [i for i in self._items.values() if selector_matches(selector, i)]


def selector_matches(selector: str, item: Item) -> bool:
    """A grant's item is an id (`calendar`) or a selector over the class: `kind:widget-data`,
    `widget:activity`, `kind:widget-data,widget:activity`. `*` matches every declared item."""
    if selector == "*":
        return True
    if ":" not in selector:
        return selector == item.id
    for part in selector.split(","):
        k, _, v = part.partition(":")
        if (k == "kind" and item.kind != v) or (k == "widget" and item.owner_widget != v) or \
           (k == "schema" and item.schema != v) or k not in ("kind", "widget", "schema"):
            return False
    return True


# ── the first instances ───────────────────────────────────────────────────────────────────────────────────────

def _freebusy(busy: Callable[[str, str], list]) -> Reader:
    def read(args: dict) -> list:
        out = []
        for iv in busy(str(args.get("from", "")), str(args.get("to", ""))) or []:
            s, e = (iv.get("start"), iv.get("end")) if isinstance(iv, dict) else (iv[0], iv[1])
            out.append({"start": s, "end": e})               # intervals only — a title never leaves
        return out
    return read


def default_items(busy: Callable[[str, str], list] | None = None,
                  public_profile: Callable[[], dict] | None = None) -> ItemRegistry:
    """`busy(from, to)` → intervals (post-clean: `widgets/agenda/free.py::busy`); `public_profile()` → the owner's
    public set (post-clean: the a2a profile config ∩ identity slots)."""
    reg = ItemRegistry()
    reg.declare(Item("messages", "stream", "messaging", "msg.text/1", ("append",)))
    reg.declare(Item("calendar", "calendar", "agenda", "calendar.freebusy/1", ("see",),
                     {"freebusy": _freebusy(busy or (lambda a, b: []))}))
    reg.declare(Item("profile", "profile", "contacts", "profile.public/1", ("see",),
                     {"default": lambda _a: dict(public_profile() if public_profile else {})}))
    reg.declare(Item("activity.live", "stream", "activity", "activity.sample/1", ("subscribe",)))
    return reg


def declare_manifest(reg: ItemRegistry, widget_id: str, entries, readers: dict[str, Reader]) -> list[str]:
    """A widget manifest's `shareable` list → declared items. Each entry is `{id, kind, schema, verbs, projections}`;
    a projection is served only if the engine has a reader for `<widget>:<projection>` (no reader → not served, the
    peer gets `unknown_item`). A bad or never-shareable entry is skipped, never raised: one manifest cannot stop the
    others. Returns the ids declared."""
    out = []
    for e in entries if isinstance(entries, list) else []:
        try:
            projections = {p: readers[f"{widget_id}:{p}"] for p in e.get("projections") or []
                           if f"{widget_id}:{p}" in readers}
            reg.declare(Item(str(e["id"]), str(e["kind"]), widget_id, str(e.get("schema") or ""),
                             tuple(e.get("verbs") or ()), projections))
            out.append(str(e["id"]))
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            logger.debug("a2a: a2a/items.py:declare_manifest failed: {!r}", exc)
            continue
    return out
