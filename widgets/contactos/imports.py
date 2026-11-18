"""widgets/contactos/imports.py — bringing a directory IN from somewhere else, and folding it into ours.

Extracted from `data.py` for the same reason `gcontacts.py` was (V2-699): the data layer must stay
readable, and a matcher that grows a key per source is the file nobody opens twice. Nothing here imports
`data` at module scope.

## The rule the operator set (V2-714, 2026-09-16)

> «Hacemos solo import. Idealmente import continuo. En local los contactos son editables y se pueden
> ocultar, se quedan mapeados a las plataformas, pero ya no se modifican más desde el conector.»

So **continuous import means continuous DISCOVERY, not continuous rewriting**. Every pass brings what we
did not have; a field he can edit is never overwritten. There is no push, no `authoritative`, no «whoever touched
it last wins» — that is Google's contract (V2-699) and it stays Google's, in `gcontacts.py`.

What a pass ADDS to a row that exists: a CHANNEL, a GROUP MEMBERSHIP, every PHONE and ADDRESS the source holds
(they are what proves the person is the same one in another source — `identity.py`), and the NAME the source
knows the person by, kept beside the one shown (`identity.said`): the operator, 2026-11-18 — «if she changes her
name in WhatsApp tomorrow, or he calls her something else on his phone, the system notices by itself». The shown
name follows the source only on a row that source gave and he never touched.

A pass asked with `refresh` (what a connector PUSHES: a rename, a number learned) only touches people the
directory already holds: a socket reports the nickname of every stranger who writes in a group.

## Hiding, and why it beats deleting

A row can be hidden (`hidden: true`): it leaves the directory, the suggestions and the reachable set, and
**it keeps its mapping**. That mapping is the entire reason to hide instead of delete — without it the
next pass re-imports the person and he has to hide them again forever. Deleting still exists and is still
LOCAL: neither Telegram nor WhatsApp has an address-book write API, so nothing we do here ever reaches
them, and the card says so instead of letting him find out.

## What a source hands us

A connector normalises to these two shapes and NEVER writes to the store (the boundary `gcontacts.py`
already keeps):

    contact = {"name", "kind"?, "phone"?, "email"?, "city"?, "notes"?, "avatar"?,
               "groups": [label…]?, "channels": [{"platform", "handle"?, "chatId"?}…]?,
               "externalIds": {"<source>": "<id>"}}

    group   = {"name", "platform", "subtype": "group"|"channel"|"cluster",
               "externalIds": {...}, "channels": [...]?, "members": [contact…]}
"""
from __future__ import annotations

import time

from . import identity
from .model import norm as _norm

#: Sources this module knows how to fold in. Google keeps its own two-way sync in `gcontacts.py`; these
#: are the IMPORT-ONLY ones.
SOURCES = ("telegram", "whatsapp", "meshkore")


#: A phone reduced to what makes it AN ACCOUNT (its last nine digits) — `identity.phone_key`, the one definition.
phone_key = identity.phone_key


def _ext(c: dict) -> dict:
    e = c.get("externalIds")
    return e if isinstance(e, dict) else {}


def match(contacts: list[dict], inc: dict, index=None) -> dict | None:
    """Which existing row this imported person IS, or None for somebody new.

    What PROVES it first — `identity.find`: the same account (the row this source gave last time: it survives a
    rename here and keeps a hidden person hidden), then a phone or an address shared with a row, ANY of the ones
    either side holds. Then the name, the weakest: name + city, and the name ALONE when exactly one contact carries
    it — `add_contact`'s rule, so the two doors agree; the same for a full name (two words or more) the source
    also knows the account by. It stops at two: a duplicate he can merge beats silently folding two people into one.

    ⚠️ What is deliberately NOT a key: WhatsApp's `notify`, the nickname the OTHER person set for themselves. It
    changes whenever they feel like it and two strangers share it all the time. It names, it never identifies.
    """
    from . import identity
    hit = identity.find(index or identity.Index(contacts), inc, str(inc.get("source") or ""))
    if hit is not None:
        return hit
    nm, city = _norm(inc.get("name")), _norm(inc.get("city"))
    if not nm:
        return None
    pool = [c for c in contacts if c.get("kind") == "group"] if inc.get("kind") == "group" else contacts
    for c in pool:
        if _norm(c.get("name")) == nm and _norm(c.get("city")) == city:
            return c
    same = [c for c in pool if _norm(c.get("name")) == nm]
    if len(same) == 1:
        return same[0]
    # …and a FULL name the source also has for this account (the one he saved there, the one its conversation
    # carried), when exactly one row is called that: «Odi V.» on the platform is the «Odile Varga Lund» he keeps.
    for other in inc.get("knownAs") or []:
        o = _norm(other)
        if inc.get("kind") != "group" and len(o.split()) >= 2 and identity.real_name(other):
            same = [c for c in pool if _norm(c.get("name")) == o]
            if len(same) == 1:
                return same[0]
    return None


#: Fields an import may FILL IN when they are empty here. It may never change one that has a value — that
#: is the operator's rule, and the reason there is no `authoritative` flag anywhere in this module.
_FILLABLE = ("city", "address", "phone", "email", "notes", "avatar")


GIVE_WAY_EVERY = 50     # rows between two yields of the interpreter while a merge runs in the widget thread (E0)


def give_way(i: int) -> bool:
    """Between batches of a merge the thread yields the interpreter and, while the body's loop is stalling, paces
    itself (`nucleo/pulse/loop_lag.give_way`): a 2 700-row import must never hold the loop. True when it paced."""
    from nucleo.pulse import loop_lag   # in-memory and total: nothing to swallow
    return loop_lag.give_way(i, every=GIVE_WAY_EVERY)


def _details(inc: dict, key: str, scalar: str) -> list[dict]:
    rows = [r if isinstance(r, dict) else {"value": r} for r in inc.get(key) or []]
    return rows + ([{"value": inc[scalar]}] if inc.get(scalar) else [])


def _refresh(c: dict, inc: dict, source: str, _d) -> bool:
    """What a pass adds to a row that exists (see the module note). True when the row changed."""
    from . import identity
    touched = False
    for k in _FILLABLE:
        if inc.get(k) and not str(c.get(k) or "").strip():
            c[k] = inc[k]
            _d.model.normalize(c)        # a filled-in number joins the list, it does not sit beside it
            touched = True
    for key, scalar in (("phones", "phone"), ("emails", "email")):
        for r in _details(inc, key, scalar):
            touched |= _d.model.add_detail(c, key, r.get("value"), r.get("label") or "")
    for row in inc.get("channels") or []:
        r = _d._channel_row(row)
        mine = next((ch for ch in c.get("channels") or [] if r and _d._same_channel(ch, r)), None)
        if r and mine is None:
            _d._merge_channel(c, r)
            touched = True
        elif r and r.get("name") and r["name"] != mine.get("name"):
            mine["name"] = r["name"]     # what that chat calls the person NOW
            touched = True
    for g in inc.get("groups") or []:
        if _norm(g) not in {_norm(x) for x in c.get("groups") or []}:
            c.setdefault("groups", []).append(g)
            touched = True
    for src, val in _ext(inc).items():
        held = c.setdefault("externalIds", {}).get(src)
        if val and not held:
            c["externalIds"][src] = val
            touched = True
        elif val and str(held) != str(val) and not any(str(r.get("id")) == str(val) for r in c.get("alsoIds") or []):
            c.setdefault("alsoIds", []).append({"source": src, "id": val})   # a second account of one person
            touched = True
    touched |= identity.said(c, inc.get("name"), source)
    for n in inc.get("knownAs") or []:
        touched |= identity.known_as(c, n, source)
    return touched


def merge_contacts(db: dict, rows: list[dict], *, source: str, refresh: bool = False, members: bool = False,
                   index=None) -> dict:
    """Fold imported people in. Returns counts and the `ids` of the rows these people are; never overwrites a
    field he can edit.

    A hidden row is matched and left hidden: the mapping is what stops the next pass resurrecting somebody
    he removed from his sight on purpose. With `refresh`, nobody is added.

    Who becomes a row IN SIGHT (2026-11-18, measured: one pass of one account added 1 716 people, 1 046 of them
    seen only as members of his groups, and 13 whose name was a phone number): a person the source lists as HIS —
    its address book, a conversation — with a name somebody gave. A group's member nobody else knows (`members`)
    and an account with a number where its name should be are kept, mapped and out of sight (`identity.keep_back`):
    never a candidate, never a new row on the card — and back by themselves when a source proves the first is a
    contact or names the second.
    """
    from . import data as _d, identity
    contacts = db.setdefault("contacts", [])
    index = index or identity.Index(contacts, identity.apart_pairs(db))
    today = time.strftime("%Y-%m-%d")
    added = filled = unchanged = 0
    ids: list = []
    for i, inc in enumerate(rows or []):
        give_way(i)                      # E0: a thousand rows in the widget thread give the loop its turn
        name = str(inc.get("name") or "").strip()
        if not name:
            continue                        # a row with no name cannot be referenced, listed or spoken
        named = any(ch.isalpha() for ch in name)      # a number is not a name: it never shows a row (`identity.said`
                                                      # and `known_as` already refuse to rename or nickname by one)
        c = match(contacts, {**inc, "source": source}, index)
        if c is None and refresh:
            continue
        if c is not None:
            ids.append(c.get("id"))
            if not members and identity.surface(c, identity.MEMBER):     # the source now lists them as HIS
                c["updated"] = today
            if named and identity.surface(c, identity.NO_NAME):
                c["updated"] = today
        if c is None:
            cid = f"c{db.get('next_id', 1)}"
            db["next_id"] = int(db.get("next_id", 1)) + 1
            c = {"id": cid, "kind": _d._kind(inc.get("kind")), "name": name,
                 "city": inc.get("city", ""), "address": inc.get("address", ""),
                 "phone": inc.get("phone", ""), "email": inc.get("email", ""),
                 "notes": inc.get("notes", ""), "avatar": inc.get("avatar", ""),
                 "groups": list(inc.get("groups") or []), "favorite": False,
                 "channels": [], "preferred": "", "parentId": "", "members": [],
                 "hidden": False, "created": today, "updated": today,
                 "source": source, "externalIds": dict(_ext(inc))}
            contacts.append(c)
            _d.model.normalize(c)            # V2-715: the scalar it just wrote becomes its phones/emails list
            for row in inc.get("channels") or []:
                _d._merge_channel(c, _d._channel_row(row) or {})
            c["channels"] = [ch for ch in c.get("channels") or [] if ch.get("platform")]
            for n in inc.get("knownAs") or []:
                identity.known_as(c, n, source)
            if members or not named:
                identity.keep_back(c, identity.MEMBER if members else identity.NO_NAME)
            index.add(c)
            ids.append(cid)
            added += int(not c.get("hidden"))
            continue
        if _refresh(c, inc, source, _d):
            c["updated"] = today             # NOT `_touch`: an import filling a blank is not him deciding
            index.add(c)
            filled += 1
        else:
            unchanged += 1
    return {"added": added, "filled": filled, "unchanged": unchanged, "read": len(rows or []), "ids": ids}


def merge_groups(db: dict, rows: list[dict], *, source: str, listed: set | None = None) -> dict:
    """Fold imported GROUPS in — a Telegram/WhatsApp group chat, a Telegram channel, a MeshKore cluster.

    A group is a `kind`, not a label (V2-714). `data.py` has warned since V2-523 that a group LABEL
    («restaurantes») says how he files things while a `kind` says what the entry IS, and a group chat is
    the second: it has identity, it has members, it comes from a platform and **you can write to it**.
    Putting it in the label field would be exactly the confusion that comment exists to prevent.

    Members are merged as contacts FIRST (so the person in two groups is one row, through the same keys as
    everybody else) and the group then stores their local ids. Membership lives on the GROUP because that
    is where it lives on all three platforms — the group has members, the person does not have groups.

    A broadcast channel enumerates no members. It arrives with none, and the card says «sin miembros» —
    an empty list that means «we cannot know» must not look like one that means «nobody».
    """
    from . import data as _d
    contacts = db.setdefault("contacts", [])
    today = time.strftime("%Y-%m-%d")
    added = filled = unchanged = 0
    # ONE index for the whole pass (measured 2026-11-18: an index per group and per member made a pass of 53
    # groups over 4 000 rows take minutes in the widget thread).
    index = identity.Index(contacts, identity.apart_pairs(db))
    by_id = {c.get("id"): c for c in contacts}
    for i, inc in enumerate(rows or []):
        give_way(i)                      # E0: a thousand rows in the widget thread give the loop its turn
        name = str(inc.get("name") or "").strip()
        if not name:
            continue
        member_rows = [m for m in (inc.get("members") or []) if isinstance(m, dict)]
        member_ids: list = []
        if member_rows:
            got = merge_contacts(db, member_rows, source=source, members=True, index=index)
            member_ids = list(dict.fromkeys(got["ids"]))
            for mid in member_ids:
                c = by_id.get(mid) or by_id.setdefault(mid, _d._find(db, mid))
                # a row an earlier pass made of somebody only ever seen as a member
                if (listed is not None and mid not in listed and c is not None and identity.source_of(c) == source
                        and not identity.keys(c) - _own_keys(c, source)):
                    identity.keep_back(c, identity.MEMBER)
        g = match(contacts, {**inc, "kind": "group"}, index)
        if g is None:
            gid = f"c{db.get('next_id', 1)}"
            db["next_id"] = int(db.get("next_id", 1)) + 1
            g = {"id": gid, "kind": "group", "name": name, "city": "", "address": "",
                 "phone": "", "email": "", "notes": inc.get("notes", ""), "avatar": inc.get("avatar", ""),
                 "groups": [], "favorite": False, "channels": [], "preferred": "", "parentId": "",
                 "members": member_ids, "membersKnown": bool(member_rows) or inc.get("subtype") != "channel",
                 "platform": str(inc.get("platform") or source), "subtype": str(inc.get("subtype") or "group"),
                 "hidden": False, "created": today, "updated": today,
                 "source": source, "externalIds": dict(_ext(inc))}
            contacts.append(g)
            for row in inc.get("channels") or []:
                _d._merge_channel(g, _d._channel_row(row) or {})
            g["channels"] = [ch for ch in g.get("channels") or [] if ch.get("platform")]
            index.add(g)
            added += 1
            continue
        touched = False
        # A group that already exists keeps its name (he may have renamed it) and GAINS members: somebody
        # joining is new information, not an edit of his.
        known = set(g.setdefault("members", []))
        for mid in member_ids:
            if mid not in known:
                known.add(mid)
                g["members"].append(mid)
                touched = True
        for row in inc.get("channels") or []:
            r = _d._channel_row(row)
            if r and not any(_d._same_channel(ch, r) for ch in g.get("channels") or []):
                _d._merge_channel(g, r)
                touched = True
        for src, val in _ext(inc).items():
            if val and not g.setdefault("externalIds", {}).get(src):
                g["externalIds"][src] = val
                touched = True
        if touched:
            g["updated"] = today
            filled += 1
        else:
            unchanged += 1
    return {"added": added, "filled": filled, "unchanged": unchanged, "read": len(rows or [])}


def _own_keys(c: dict, source: str) -> set:
    """The keys of the row that are only the source's own account of it — what a stranger of a group has."""
    return {k for k in identity.keys(c) if k[0] == "acct" and k[1] == identity.model.source_key(source)}


def absorb(db: dict, payload: dict, *, source: str, refresh: bool = False) -> dict:
    """One pass of one source: `{"contacts": [...], "groups": [...]}` → counts. The single door every
    importer comes through, so a new platform adds a normaliser and nothing else. After it, the rows the pass
    proved to be one person are one row (`identity.unify`)."""
    from . import identity
    people = merge_contacts(db, payload.get("contacts") or [], source=source, refresh=refresh)
    groups = merge_groups(db, [] if refresh else payload.get("groups") or [], source=source,
                          listed=None if refresh else set(people["ids"]))
    merged = identity.unify(db)["merged"]            # change-gated by what it finds: cheap when nothing is one
    return {"contacts": people, "groups": groups, "merged": merged,
            "added": people["added"] + groups["added"],
            "filled": people["filled"] + groups["filled"]}
