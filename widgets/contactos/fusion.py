"""widgets/contactos/fusion.py — two rows that are one person BECOME one row, and can be taken apart again.

`identity.py` says WHO is the same person; this does the folding. Nothing is thrown away: the row that stays gains
the other's phones, addresses, channels, labels, ids and words; the name that is not shown becomes a name the
person is known by, with the source that gave it; and the folded row is kept whole (`db["merged"][its id]`), with
what it gave, so `split` restores it — a fold made by a shared phone can be wrong (a number that changed hands), and
a merge he cannot undo would be the one mistake this directory could not take back.

The id of a folded row keeps answering: `resolve_id` follows it to the row that holds the person now, and the
groups and parents that pointed at it point at that row.
"""
from __future__ import annotations

import copy
import time

from . import channels, identity, model

#: How many folded rows are kept for an undo — the newest.
MERGED_MAX = 2000


def keeper(rows: list[dict]) -> dict:
    """The row that STAYS (its id is the one his rules, his groups and his memory already use): the one carrying
    more of his own marks — a favorite, a word of his, a relation, an edit — then his address book's, then the
    visible one, then the oldest."""
    def marks(c: dict) -> tuple:
        num = int("".join(ch for ch in str(c.get("id") or "") if ch.isdigit()) or 0)
        return (-int(bool(c.get("favorite"))), -int(bool(c.get("aliases") or c.get("relation"))),
                -int(bool(c.get("touchedAt"))), identity._NAME_RANK.get(identity.source_of(c), 4),
                int(bool(c.get("hidden"))), num)
    return min(rows, key=marks)


def resolve_id(db: dict, cid) -> str:
    """The id that holds the person `cid` named — itself, or the row it was folded into (followed to the end)."""
    cid, seen = str(cid or ""), set()
    merged = db.get("merged") or {}
    while cid in merged and cid not in seen:
        seen.add(cid)
        cid = str((merged[cid] or {}).get("into") or "")
    return cid


def _channel(into: dict, ch: dict) -> bool:
    """One channel of the folded row: the same account refreshes ours; another account on a platform we already
    reach keeps the one he uses more (the other stays in the folded row's copy); a new platform is added."""
    row = channels.channel_row(ch)
    if not row:
        return False
    for k in ("linked_by", "lid"):
        if ch.get(k):
            row[k] = ch[k]
    mine = next((c for c in into.get("channels") or [] if c.get("platform") == row["platform"]), None)
    if mine is None:
        into.setdefault("channels", []).append(row)
        return True
    used = lambda c: (float(c.get("volume") or 0), float(c.get("last_seen") or 0))  # noqa: E731
    if channels.same_channel(mine, row) or used(row) > used(mine):
        same = channels.same_channel(mine, row)
        vol = int(mine.get("volume") or 0) + int(row.get("volume") or 0) if same else int(row.get("volume") or 0)
        for k in ("handle", "chatId", "name"):
            if row.get(k) and (not same or not mine.get(k)):
                mine[k] = row[k]
        mine["volume"] = vol
        mine["last_seen"] = max(float(mine.get("last_seen") or 0), float(row.get("last_seen") or 0))
    return False


def fold(db: dict, into: dict, other: dict, *, by: str = "") -> dict:
    """Fold `other` into `into` (see the module note). `by` says what joined them: «key», or «his» for his word."""
    snap = copy.deepcopy(other)
    gave: dict = {"phones": [], "emails": [], "groups": [], "channels": [], "knownAs": [], "aliases": []}
    src_into, src_other = identity.source_of(into), identity.source_of(other)
    # the shown name: the better of the two; the other one is a name the person is known by
    if model.norm(other.get("name")) != model.norm(into.get("name")):
        if identity.name_rank(other) < identity.name_rank(into):
            old, into["name"] = str(into.get("name") or ""), str(other.get("name") or "")
            into["nameSource"] = str(other.get("nameSource") or "") or src_other
            into["knownAs"] = [r for r in into.get("knownAs") or [] if model.norm(r.get("name")) != model.norm(into["name"])]
            gave["name"] = old
            identity.known_as(into, old, src_into)
        elif identity.known_as(into, other.get("name"), src_other):
            gave["knownAs"].append(str(other.get("name") or ""))
    for r in other.get("knownAs") or []:
        if identity.known_as(into, r.get("name"), r.get("source")):
            gave["knownAs"].append(str(r.get("name") or ""))
    for key in ("phones", "emails"):
        for r in other.get(key) or []:
            if model.add_detail(into, key, r.get("value"), r.get("label") or ""):
                gave[key].append(str(r.get("value") or ""))
    for ch in other.get("channels") or []:
        if _channel(into, ch):
            gave["channels"].append(str(ch.get("platform") or ""))
    have = {model.norm(g) for g in into.get("groups") or []}
    for g in other.get("groups") or []:
        if model.norm(g) not in have:
            have.add(model.norm(g))
            into.setdefault("groups", []).append(g)
            gave["groups"].append(g)
    words = {model.norm(a) for a in into.get("aliases") or []}
    for a in other.get("aliases") or []:
        if model.norm(a) not in words:
            into.setdefault("aliases", []).append(a)
            gave["aliases"].append(a)
            if (other.get("aliasSources") or {}).get(a):
                into.setdefault("aliasSources", {})[a] = other["aliasSources"][a]
    # ids: every account the folded row was keeps matching the next import of its source
    for s, v in (other.get("externalIds") or {}).items():
        if not into.setdefault("externalIds", {}).get(s):
            into["externalIds"][s] = v
        elif str(into["externalIds"][s]) != str(v):
            into.setdefault("alsoIds", []).append({"source": s, "id": v})
    if other.get("googleId"):
        if not into.get("googleId"):
            into["googleId"] = other["googleId"]
        elif str(into["googleId"]) != str(other["googleId"]):
            into.setdefault("alsoIds", []).append({"source": "google", "id": other["googleId"]})
    into["alsoIds"] = (into.get("alsoIds") or []) + list(other.get("alsoIds") or [])
    if not into["alsoIds"]:
        into.pop("alsoIds")
    gave["fields"] = [k for k in ("city", "address", "notes", "avatar", "preferred", "relation", "parentId", "agent")
                      if other.get(k) and not str(into.get(k) or "").strip()]
    for k in gave["fields"]:
        into[k] = other[k]
    into["favorite"] = bool(into.get("favorite") or other.get("favorite"))
    into["flags"] = list(dict.fromkeys(list(into.get("flags") or []) + list(other.get("flags") or [])))
    into["agents"] = list(into.get("agents") or []) + list(other.get("agents") or [])
    into["hidden"] = bool(into.get("hidden")) and bool(other.get("hidden"))
    into["created"] = min(str(into.get("created") or "9"), str(other.get("created") or "9"))
    into["updated"] = time.strftime("%Y-%m-%d")           # not `_touch`: a fold is not him editing the person
    model.normalize(into)
    oid, iid = str(other.get("id") or ""), str(into.get("id") or "")
    db["contacts"] = [c for c in db.get("contacts") or [] if c is not other]
    for c in db["contacts"]:                              # whoever pointed at the folded row points at the person
        if oid in (c.get("members") or []):
            c["members"] = list(dict.fromkeys(iid if m == oid else m for m in c["members"]))
        if str(c.get("parentId") or "") == oid:
            c["parentId"] = iid
    _move_rules(oid, iid)
    merged = db.setdefault("merged", {})
    merged[oid] = {"into": iid, "at": time.time(), "by": by, "row": snap, "gave": gave}
    for old in sorted(merged, key=lambda k: float((merged[k] or {}).get("at") or 0))[:max(0, len(merged) - MERGED_MAX)]:
        merged.pop(old, None)
    return into


def _move_rules(old: str, new: str) -> int:
    """His rules about the folded row (`subject:<id>…`) become rules about the person: an exception he set for her
    («never to her without asking») must not stop applying because her two rows became one. Never raises."""
    moved = 0
    try:
        import rules
        from rules import store as _store
        for r in rules.all_rows(include_defaults=False):
            sc = str(r.get("scope") or "")
            if old and new and (sc == f"subject:{old}" or sc.startswith(f"subject:{old}/")):
                _store.put({**r, "scope": f"subject:{new}" + sc[len(f"subject:{old}"):]})
                moved += 1
    except Exception as e:  # noqa: BLE001 — said loud: a rule left on a folded id no longer guards her
        __import__("loguru").logger.warning(f"contactos: the rules about {old} were not moved to {new}: {e!r}")
    return moved


def split(db: dict, cid) -> dict | None:
    """Take a folded row apart again: it comes back as it was, the row it was folded into gives back what it had
    received from it, and the two are never joined again. None when `cid` was never folded."""
    oid = str(cid or "")
    rec = (db.get("merged") or {}).get(oid)
    if not isinstance(rec, dict) or not isinstance(rec.get("row"), dict):
        return None
    keep = next((c for c in db.get("contacts") or [] if str(c.get("id")) == resolve_id(db, rec.get("into"))), None)
    row, gave = rec["row"], rec.get("gave") or {}
    if keep is not None:
        for key in ("phones", "emails"):
            for v in gave.get(key) or []:
                model.drop_detail(keep, key, v)
        keep["groups"] = [g for g in keep.get("groups") or [] if g not in (gave.get("groups") or [])]
        keep["aliases"] = [a for a in keep.get("aliases") or [] if a not in (gave.get("aliases") or [])]
        keep["channels"] = [c for c in keep.get("channels") or [] if c.get("platform") not in (gave.get("channels") or [])]
        back = {model.norm(n) for n in gave.get("knownAs") or []}
        if gave.get("name"):                               # the shown name had come from the folded row
            keep["name"], keep["nameSource"] = gave["name"], ""
            back.add(model.norm(gave["name"]))
        keep["knownAs"] = [r for r in keep.get("knownAs") or [] if model.norm(r.get("name")) not in back]
        for k in gave.get("fields") or []:
            keep[k] = ""
        ids = {str(v) for v in (row.get("externalIds") or {}).values()} | {str(row.get("googleId") or "")}
        keep["externalIds"] = {s: v for s, v in (keep.get("externalIds") or {}).items()
                               if str(v) not in ids or (keep.get("externalIds") or {}).get(s) != (row.get("externalIds") or {}).get(s)}
        if str(keep.get("googleId") or "") and str(keep.get("googleId")) == str(row.get("googleId") or ""):
            keep["googleId"] = ""
        keep["alsoIds"] = [r for r in keep.get("alsoIds") or [] if str(r.get("id")) not in ids]
        model.normalize(keep)
        db.setdefault("apart", []).append([str(keep.get("id")), oid])
    db.setdefault("contacts", []).append(row)
    db["merged"].pop(oid, None)
    return row
