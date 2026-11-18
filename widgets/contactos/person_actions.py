"""widgets/contactos/person_actions.py — HIS word about who is who: «these two are the same person», and its undo.

A shared phone or address joins two rows by itself (`identity.py`). When nothing proves it — the row of his address
book holds only an address, the chat's account hides its number — the only one who knows is him, and he says it
once: `merge_contacts`. `split_contact` takes a fold apart again, his or an automatic one, and the two are never
joined again.
"""
from __future__ import annotations

from . import data as _d
from . import fusion, identity, model


def _named(db: dict, ref) -> dict | None:
    """A row by its id, or by a name that means exactly one person."""
    ref = str(ref or "").strip()
    if not ref:
        return None
    hit = _d._find(db, ref)
    if hit is not None:
        return hit
    from widgets import directory
    found = directory.resolve(ref)
    return _d._find(db, found[0].get("id")) if len(found) == 1 else None


def _a_merge_contacts(action, payload, q, db, contacts, now) -> dict:
    a = _named(db, payload.get("contactId"))
    b = _named(db, payload.get("otherId") or payload.get("with") or payload.get("other"))
    if not a or not b or a is b:
        return {"ok": False, "error": "merge_contacts needs the two rows that are one person: `contactId` and `with` "
                                      "(an id, or a name that means exactly one contact) — ask him which if a name "
                                      "matches several"}
    if model.kind(a.get("kind")) != model.kind(b.get("kind")) or model.kind(a.get("kind")) not in identity.PEOPLE:
        return {"ok": False, "error": "only two people (or two companies) can be one — a group or an agent is an "
                                      "account of its own"}
    pair = {str(a.get("id")), str(b.get("id"))}
    db["apart"] = [p for p in db.get("apart") or [] if set(map(str, p)) != pair]    # his word undoes his split
    keep = fusion.keeper([a, b])
    other = b if keep is a else a
    folded = str(other.get("name") or "")
    fusion.fold(db, keep, other, by="his")
    _d.store.save(_d.WIDGET_ID, db)
    d = _d.view_data(q)
    d.update({"ok": True, "result": {"contact": _d._public(keep), "folded": folded}})
    return d


def _a_split_contact(action, payload, q, db, contacts, now) -> dict:
    """Undo a fold: by the folded row's id, by its name, or — given the row that holds the person — its latest one."""
    merged = db.get("merged") or {}
    ref = str(payload.get("contactId") or "").strip()
    name = model.norm(payload.get("name") or payload.get("other"))
    into = [k for k, r in merged.items() if str((r or {}).get("into") or "") == ref]
    if name:                                         # among the rows folded into that person, the one so named
        pool = into or list(merged)
        oid = next((k for k in pool if model.norm(((merged[k] or {}).get("row") or {}).get("name")) == name), "")
    elif ref in merged:
        oid = ref
    else:
        oid = max(into, key=lambda k: float((merged[k] or {}).get("at") or 0), default="")
    row = fusion.split(db, oid) if oid else None
    if row is None:
        return {"ok": False, "error": "that contact was not joined from two rows — split_contact needs the `contactId` "
                                      "of the person and, when several rows were folded into it, the `name` of the one "
                                      "to take apart"}
    _d.store.save(_d.WIDGET_ID, db)
    d = _d.view_data(q)
    d.update({"ok": True, "result": {"contact": _d._public(row)}})
    return d
