"""gmerge.py — THE GOOGLE MERGE (V2-714, split from `gcontacts.py`): Google's two-way contract — «whoever touched it
last wins», a sync token deciding when Google may replace instead of fill. `imports.py` holds the opposite rule.

`_norm`/`_touch`/`store` resolve through `data` lazily: `data` imports this module at its top, and bound names make
the direction of that dependency visible (a moved block keeps its globals only when they are bound here).
"""
from __future__ import annotations

import time


def _model():
    """The record shape, lazily — `model.py` is a leaf and this module is imported BY `data.py`."""
    from . import model
    return model


def _norm(s):
    from .data import _norm as _n
    return _n(s)


def _touch(c, now):
    from .data import _touch as _t
    return _t(c, now)


class _StoreProxy:
    """`store.save(...)` as the moved block spells it, resolved through `data` so there is ONE store."""

    def __getattr__(self, name):
        from .data import store as _s
        return getattr(_s, name)


store = _StoreProxy()


def match_imported(contacts: list[dict], inc: dict, index=None) -> dict | None:
    """Which existing contact this Google person IS, or None for somebody new (V2-699).

    In descending order of how much each PROVES:

      1. what `identity.find` reads: the same Google resource (it survives him renaming the person here), then a
         PHONE or an ADDRESS shared with a row — any of the ones either side holds. Two rows sharing an account
         are one person (the rule V2-693 settled for Telegram), unless this very address book keeps two differently
         named people on one line.
      2. name + city, normalized — `add_contact`'s own rule, so the two doors agree.
      3. the name ALONE, but only when exactly ONE contact here carries it. This is what makes a second
         import safe: Google routinely knows a city he never typed — so «Marta Ruiz» with no city here and
         «Marta Ruiz, Soria» there would otherwise import as a SECOND Marta every single time. When two
         contacts share the name it stops: adding a duplicate he can merge beats silently folding two
         people into one.
    """
    from . import identity
    hit = identity.find(index or identity.Index(contacts), {**inc, "source": "google"}, "google")
    if hit is not None:
        return hit
    nm, city = _norm(inc.get("name")), _norm(inc.get("city"))
    if not nm:
        return None
    for c in contacts:
        if _norm(c.get("name")) == nm and _norm(c.get("city")) == city:
            return c
    same_name = [c for c in contacts if _norm(c.get("name")) == nm]
    return same_name[0] if len(same_name) == 1 else None


def merge_imported(db: dict, rows: list[dict], *, authoritative: bool = False) -> dict:
    """Fold Google's side into ours. The MERGE lives here, not in the connector: this store is the only
    module that knows which fields the OPERATOR typed himself.

    **His edits win.** Google only FILLS IN what is empty here — a pass that overwrote a field he had
    fixed would silently undo the correction, and he would have no way to tell which of the two surfaces
    was lying. The other direction (his newer rows reaching Google) is `gcontacts.sync`'s push half, which
    has already run by the time this is called.

    `authoritative` is the one case where Google may REPLACE a value instead of only filling a blank, and
    it is narrow on purpose (V2-701): the row arrived through a SYNC TOKEN, which means Google is telling
    us it changed since we last looked, AND our copy has nothing pending («whoever touched it last wins»,
    the rule this connector has answered conflicts with since V2-699). A row he has edited and we have not
    sent yet is still his — it is waiting its turn in the push half, and letting Google win here would
    delete the edit before it ever left the house. A FULL re-read is never authoritative: there, «changed»
    is unknown, and treating every row as fresh would undo his corrections wholesale on the first pass.
    """
    contacts = db.setdefault("contacts", [])
    now = time.strftime("%Y-%m-%d")
    added = updated_n = unchanged = 0
    from . import identity
    from .imports import give_way
    index = identity.Index(contacts, identity.apart_pairs(db))
    for i, inc in enumerate(rows or []):
        give_way(i)                      # E0: a thousand rows in the widget thread give the loop its turn
        c = match_imported(contacts, inc, index)
        if c is None:
            cid = f"c{db.get('next_id', 1)}"
            db["next_id"] = int(db.get("next_id", 1)) + 1
            c = {"id": cid, "kind": inc.get("kind") or "person", "name": inc["name"],
                 "city": inc.get("city", ""), "address": inc.get("address", ""),
                 "phone": inc.get("phone", ""), "email": inc.get("email", ""),
                 "notes": inc.get("notes", ""), "groups": list(inc.get("groups") or []),
                 "favorite": bool(inc.get("favorite")), "channels": [], "preferred": "",
                 "phones": list(inc.get("phones") or []), "emails": list(inc.get("emails") or []),
                 "parentId": "", "created": now, "updated": now,
                 "source": "google", "googleId": inc.get("googleId", "")}
            _model().normalize(c)
            for n in inc.get("knownAs") or []:           # the nicknames his address book holds for the person
                identity.known_as(c, n, "google")
            contacts.append(c)
            index.add(c)
            added += 1
            continue
        # HIS EDITS WIN. Google only FILLS IN what is empty here — it never overwrites a field the
        # operator typed, because a second import would silently undo every correction he had made,
        # and he would have no way to tell which of the two surfaces was lying.
        #
        # …unless this row reached us through a sync token AND we have nothing pending on it: then Google
        # touched it last and Google wins, which is what makes this a SYNC rather than a repeated import.
        takes_over = authoritative and float(c.get("touchedAt") or 0.0) <= float(c.get("pushedAt") or 0.0)
        touched = False
        for k in ("city", "address", "phone", "email", "notes"):
            if inc.get(k) and (takes_over or not str(c.get(k) or "").strip()) and inc[k] != c.get(k):
                c[k] = inc[k]
                touched = True
        if takes_over and inc.get("name") and inc["name"] != c.get("name"):
            was, c["name"], c["nameSource"] = c.get("name"), inc["name"], "google"
            identity.known_as(c, was, "google")          # the name he called her until today still finds her
            touched = True
        touched |= identity.said(c, inc.get("name"), "google")   # a row a chat app gave takes his address book's name
        for n in inc.get("knownAs") or []:
            touched |= identity.known_as(c, n, "google")
        # V2-715 — the OTHER phones and addresses. An ADDITION, always, even when Google is authoritative:
        # a number he typed here is his, and the failure the `takes_over` rule protects against («a second
        # import silently undoes every correction») has exactly the same shape one field over. Google
        # removing a number therefore never removes ours — the card's ✕ is the door for that.
        m = _model()
        for key in ("phones", "emails"):
            for row in inc.get(key) or []:
                if m.add_detail(c, key, row.get("value"), row.get("label") or ""):
                    touched = True
        for g in inc.get("groups") or []:
            if _norm(g) not in {_norm(x) for x in c.get("groups") or []}:
                c.setdefault("groups", []).append(g)
                touched = True
        # A ★ only ever travels ONE way: starring in Google stars here, un-starring there never
        # un-stars the favourite he set on this card.
        if inc.get("favorite") and not c.get("favorite"):
            c["favorite"] = True
            touched = True
        if inc.get("googleId") and not c.get("googleId"):
            c["googleId"] = inc["googleId"]
            touched = True
        if touched:
            # NOT `_touch`: Google filling in a blank is not the operator changing his mind, and stamping
            # `touchedAt` here would make the next push send Google's own value straight back at it.
            c["updated"] = now
            index.add(c)
            updated_n += 1
        else:
            unchanged += 1

    merged = identity.unify(db)["merged"] if added or updated_n else 0   # what the pass proved to be one person
    return {"added": added, "updated": updated_n, "unchanged": unchanged, "read": len(rows or []), "merged": merged}


#: A single pass may never remove more than this share of the address book, nor more than this many rows,
#: whichever bites first. It is not a policy about how many contacts a person deletes in a minute — it is a
#: circuit breaker around OUR OWN code: the failure mode of a sync token gone wrong is «everything looks
#: deleted», and the difference between a bug and a catastrophe is whether anything acted on that.
_DELETE_CAP_SHARE = 0.2
_DELETE_CAP_ROWS = 25


def drop_deleted(db: dict, google_ids: list[str]) -> int:
    """Mirror deletions Google reported, and ONLY the ones that are safe to mirror (V2-701).

    A row he has edited here since we last sent it is not Google's to delete: he touched it last, which is
    the same rule that decides every other conflict in this connector. Those are kept and simply unhooked
    from the pass — they stay in the directory, still carrying their `googleId`, and a later edit will try
    to push and report honestly if Google no longer has them.
    """
    ids = {str(g).strip() for g in (google_ids or []) if str(g).strip()}
    if not ids:
        return 0
    contacts = db.get("contacts") or []
    victims = [c for c in contacts
               if str(c.get("googleId") or "") in ids
               and float(c.get("touchedAt") or 0.0) <= float(c.get("pushedAt") or 0.0)]
    if not victims:
        return 0
    cap = max(_DELETE_CAP_ROWS, int(len(contacts) * _DELETE_CAP_SHARE))
    if len(victims) > cap:
        db.setdefault("sync", {})["blockedDeletes"] = len(victims)
        return 0
    doomed = {c["id"] for c in victims}
    db["contacts"] = [c for c in contacts if c.get("id") not in doomed]
    for x in db["contacts"]:
        if x.get("parentId") in doomed:
            x["parentId"] = ""          # a dangling link paints a dead breadcrumb (same rule as remove_contact)
    db.get("sync", {}).pop("blockedDeletes", None)
    return len(victims)
