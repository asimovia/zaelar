"""widgets/contactos/identity.py — WHO a row is: one person is one row, whatever source each row came from.

Measured 2026-11-18 on a real directory (2 912 rows: one address book, one messaging import): 21 sets of rows
shared a phone and 12 an address, unmerged; the person he wrote to every day was two rows — the one of his address
book and the one of the chat, under the name SHE chose there — and «send her a message» found only the first. The
phone match read only the PRIMARY number of each side, the address-book import never looked at a phone, a name
another source gave was thrown away, nothing looked back at rows already stored, and a rename never arrived.

One definition, asked by every importer, by the store's migration and by the daily pass:

  · `keys(row)` — what PROVES an identity: every phone (as an account: its last nine digits), every address,
    every platform account (an external id, a chat id, a handle) and the address-book resource id;
  · `same(a, b)` — two rows that share a key are one person. The one exception is a LINE, not a person: two rows
    of the SAME source, each with a real name and a different given name (`akin`), on one phone or address —
    a home landline, a switchboard, a family mailbox. An address book that keeps them apart is believed; its
    nickname row and its full-name row of one person («Odile Work» · «Odile Varga Lund») are one;
  · `find(index, row)` — the stored row an arriving one IS (the same account first, then the one its name fits);
  · `unify(db)` — the look back: every set of rows that are one person is folded into one (`fusion.fold`);
  · `known_as` / `said` — the names OTHER sources know the person by. They are not his words (`aliases` are, and
    name their person outright): they are matched like a name, each with the source that gave it.

A name is never a key. Two rows with nothing in common but a first name are two rows until he says otherwise
(`merge_contacts`), and what he took apart (`split_contact`) is never joined again (`db["apart"]`).
"""
from __future__ import annotations

import re

from . import model

#: The kinds that are people to unify. A group or an agent is an account of its own; a place is found by its name.
PEOPLE = ("person", "company")
#: The WhatsApp address suffixes whose digits ARE a phone number (a `@lid` is not one).
_PHONE_JID = ("s.whatsapp.net", "c.us")
#: How many names from other sources one row keeps.
KNOWN_MAX = 8
#: Whose name is shown, best first: the one he gave here, then his address books, then a messaging account's.
_NAME_RANK = {"his": 0, "google": 1, "icloud": 1, "carddav": 1, "telegram": 2, "whatsapp": 3}


def phone_key(v) -> str:
    """A phone as an ACCOUNT: its last nine digits («+34 600 11 22 33» = «600112233»); "" under nine."""
    d = re.sub(r"\D+", "", str(v or ""))
    return d[-9:] if len(d) >= 9 else ""


def source_of(c: dict) -> str:
    """Where a row came from: a source's canonical name, or «his» for one he made here."""
    return model.source_key(c.get("source")) or ("google" if str(c.get("googleId") or "").strip() else "his")


def _account_phone(platform: str, field: str, value: str) -> str:
    """The phone an account id carries, or "": a WhatsApp phone address or bare number; a Telegram handle written
    as «+number». A Telegram account id and a `@lid` carry digits that are no phone."""
    base, _, host = value.partition("@")
    if platform == "whatsapp" and (host in _PHONE_JID or (not host and re.fullmatch(r"\+?[\d\s().-]+", base))):
        return phone_key(base)
    if platform == "telegram" and field == "handle" and re.fullmatch(r"\+[\d\s().-]+", value):
        return phone_key(value)
    return ""


def keys(c: dict) -> set[tuple]:
    """Everything that proves who this row is (see the module note). Empty for a row that is only a name."""
    out: set[tuple] = set()
    for v in model.values(c, "phones") + [c.get("phone")]:
        if k := phone_key(v):
            out.add(("phone", k))
    for v in model.values(c, "emails") + [c.get("email")]:
        if "@" in (k := model.norm(v)):
            out.add(("email", k))
    for ch in c.get("channels") or []:
        p = model.norm((ch or {}).get("platform"))
        if (ch or {}).get("linked_by") == "name":      # a chat tied to the row by a display name proves nothing
            continue
        for f in ("chatId", "handle"):
            v = str((ch or {}).get(f) or "").strip()
            if not v or not p:
                continue
            if p == "email":
                if "@" in v:
                    out.add(("email", model.norm(v)))
                continue
            out.add(("acct", p, model.norm(v).lstrip("@")))
            if k := _account_phone(p, f, v):
                out.add(("phone", k))
    for src, val in list((c.get("externalIds") or {}).items()) + [(r.get("source"), r.get("id"))
                                                                  for r in c.get("alsoIds") or []]:
        if str(val or "").strip():
            out.add(("acct", model.source_key(src), model.norm(val).lstrip("@")))
    if gid := str(c.get("googleId") or "").strip():
        out.add(("acct", "google", model.norm(gid)))
    return out


# ── names: a name is never a key, and it still tells two people sharing a line apart ───────────────────────────
def names(c: dict) -> list[str]:
    """Every name the row is known by: its own, the ones other sources gave, and the one each chat shows."""
    out = [str(c.get("name") or "")] + [str(r.get("name") or "") for r in c.get("knownAs") or []]
    out += [str((ch or {}).get("name") or "") for ch in c.get("channels") or []]
    if not any(out[1:]):                       # the usual row: one name (this runs once per row of a name lookup)
        return [out[0].strip()] if out[0].strip() else []
    seen: dict[str, str] = {}
    for n in out:
        if n.strip() and model.norm(n) not in seen:
            seen[model.norm(n)] = n.strip()
    return list(seen.values())


def real_name(name) -> bool:
    """A name somebody GAVE — letters, and none of a handle's decoration (a dot, an underscore, a digit, an @).
    «odile.varga» and «+34 600…» are an address and a number standing where the name is missing."""
    n = str(name or "").strip()
    return bool(re.search(r"[^\W\d_]", n)) and not re.search(r"[._@\d]", n)


def _words(name) -> set[str]:
    from widgets.directory import sound
    return {sound(t) for t in re.findall(r"[^\W\d_]+", model.norm(name)) if len(t) >= 2}


def alike(a: dict, b: dict) -> bool:
    """Do the two rows carry ONE name? Some name of one is contained, word by word and by sound, in a name of the
    other («Odile Varga» in «Odile Varga Lund»), or spells it («odile.vargalund»)."""
    from widgets.directory import _spelled
    for x in names(a):
        for y in names(b):
            wx, wy = _words(x), _words(y)
            if wx and wy and (wx <= wy or wy <= wx):
                return True
            sx, sy = _spelled(x), _spelled(y)
            if min(len(sx), len(sy)) >= 6 and (sx.startswith(sy) or sy.startswith(sx)):
                return True
    return False


#: How short a given name may be to count, and how short the stem a one-word nickname row is read by.
AKIN_WORD, AKIN_STEM = 3, 4


def _ordered(name) -> list[str]:
    from widgets.directory import sound
    return [sound(t) for t in re.findall(r"[^\W\d_]+", model.norm(name)) if len(t) >= 2]


def akin(a: dict, b: dict) -> bool:
    """Are the two names one person's two entries? They START with the same given name, by sound («Odile Work» ·
    «Odile Varga Lund»), or one is a single word that is a stem of a word of the other («Varg» · «Odile Vargas»).
    Read only for two rows that already share a phone or an address. A shared SURNAME says nothing: a family on one
    landline («Odile Varga» · «Tomas Varga») stays two people."""
    for x in names(a):
        for y in names(b):
            wx, wy = _ordered(x), _ordered(y)
            if not wx or not wy:
                continue
            if wx[0] == wy[0] and len(wx[0]) >= AKIN_WORD:
                return True
            one, other = (wx, wy) if len(wx) == 1 else (wy, wx)
            if len(one) == 1 and len(one[0]) >= AKIN_STEM and any(t != one[0] and t.startswith(one[0]) for t in other):
                return True
    return False


def same(a: dict, b: dict, apart: set | None = None) -> str:
    """The reason two rows are ONE person — «phone», «email», «acct» — or "" (see the module note)."""
    if a is b or model.kind(a.get("kind")) != model.kind(b.get("kind")) or model.kind(a.get("kind")) not in PEOPLE:
        return ""
    if apart and frozenset((str(a.get("id")), str(b.get("id")))) in apart:
        return ""
    shared = keys(a) & keys(b)
    if not shared:
        return ""
    if any(k[0] == "acct" for k in shared):
        return "acct"
    if (source_of(a) == source_of(b) and real_name(a.get("name")) and real_name(b.get("name"))
            and not alike(a, b) and not akin(a, b)):
        return ""                                  # one source, two unrelated names, one line: two people
    return sorted(k[0] for k in shared)[0]


def apart_pairs(db: dict) -> set:
    """The pairs he took apart (`split_contact`): never joined again."""
    return {frozenset(map(str, p)) for p in db.get("apart") or [] if isinstance(p, (list, tuple)) and len(p) == 2}


class Index:
    """key → rows, built once per pass (an import of thousands must not scan the directory per row)."""

    def __init__(self, contacts: list[dict], apart: set | None = None):
        self.by: dict[tuple, list[dict]] = {}
        self.apart = apart or set()
        for c in contacts:
            self.add(c)

    def add(self, c: dict) -> None:
        for k in keys(c):
            rows = self.by.setdefault(k, [])
            if not any(r is c for r in rows):
                rows.append(c)

    def holders(self, c: dict) -> list[dict]:
        seen: list[dict] = []
        for k in keys(c):
            seen += [r for r in self.by.get(k, []) if r is not c and not any(r is s for s in seen)]
        return seen


def find(index: Index, inc: dict, source: str = "") -> dict | None:
    """The stored row an arriving one IS, or None. The same ACCOUNT first (the row this source gave before, which
    survives a rename and keeps a hidden person hidden); then the rows that share a phone or an address — one of
    them, or the only one whose name fits; several that fit is an ambiguity, and nothing is joined on one."""
    probe = {**inc, "source": inc.get("source") or source, "kind": inc.get("kind") or "person"}
    mine = keys(probe)
    hits = [(c, mine & keys(c)) for c in index.holders(probe)]
    hits = [(c, sh) for c, sh in hits if model.kind(c.get("kind")) == model.kind(probe["kind"])]
    exact = [c for c, sh in hits if any(k[0] == "acct" for k in sh)]
    if exact:
        return exact[0]
    rows = [c for c, _sh in hits if model.kind(c.get("kind")) in PEOPLE and same(c, probe, index.apart)]
    if len(rows) > 1:
        rows = [c for c in rows if alike(c, probe)]
    return rows[0] if len(rows) == 1 else None


# ── the names other sources know the person by ─────────────────────────────────────────────────────────────────
def known_as(c: dict, name, source: str) -> bool:
    """Record a name `source` knows this person by. False when it adds nothing (it is the row's own name, it is
    already there, or it is no name at all). The newest `KNOWN_MAX` are kept."""
    n = re.sub(r"\s+", " ", str(name or "")).strip()[:120]
    src = model.source_key(source) or "his"
    if not re.search(r"[^\W\d_]", n) or model.norm(n) == model.norm(c.get("name")):
        return False
    rows = [r for r in c.get("knownAs") or [] if isinstance(r, dict) and str(r.get("name") or "").strip()]
    if any(model.norm(r["name"]) == model.norm(n) for r in rows):
        return False
    c["knownAs"] = (rows + [{"name": n, "source": src}])[-KNOWN_MAX:]
    return True


def name_rank(c: dict) -> int:
    """How much the row's shown name is HIS choice (lower is more): the giver's rank, and a name that is only a
    handle or a number loses to any real one."""
    src = str(c.get("nameSource") or "") or source_of(c)
    return _NAME_RANK.get(src, 4) + (0 if real_name(c.get("name")) else 10)


def said(c: dict, name, source: str) -> bool:
    """`source` calls this person `name` — a rename on the platform, or its first word about a row another source
    gave. The SHOWN name follows when he has not named the person himself and the source is the one that gave the
    name, or one whose name is more his choice (his address book over the name she chose in a chat app); otherwise
    the name is one more the person is known by. The name it replaces stays findable. True when the row changed.
    A row he edited before the giver of its name was recorded counts as named by him."""
    n = re.sub(r"\s+", " ", str(name or "")).strip()[:120]
    src = model.source_key(source) or "his"
    if not n or model.norm(n) == model.norm(c.get("name")):
        return False
    gave = str(c.get("nameSource") or "") or ("his" if c.get("touchedAt") else source_of(c))
    better = _NAME_RANK.get(src, 4) < name_rank(c)
    if gave != "his" and src != "his" and real_name(n) and (gave == src or better):
        old, c["name"], c["nameSource"] = str(c.get("name") or ""), n, src
        c["knownAs"] = [r for r in c.get("knownAs") or [] if model.norm(r.get("name")) != model.norm(n)]
        known_as(c, old, gave)
        return True
    return known_as(c, n, src)


# ── the look back ──────────────────────────────────────────────────────────────────────────────────────────────
def _clusters(contacts: list[dict], apart: set) -> list[list[dict]]:
    """The sets of rows that are one person. Rows sharing a key are grouped per key: a row joins the group it is
    `same` as with every member; offered several, the one its name fits, and none when no name decides."""
    parent: dict[int, int] = {}

    def root(i: int) -> int:
        while parent.setdefault(i, i) != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    people = [c for c in contacts if model.kind(c.get("kind")) in PEOPLE]
    index = Index(people, apart)
    for bucket in index.by.values():
        if len(bucket) < 2:
            continue
        groups: list[list[dict]] = []
        for c in sorted(bucket, key=name_rank):
            fits = [g for g in groups if all(same(c, m, apart) for m in g)]
            if len(fits) > 1:
                fits = [g for g in fits if any(alike(c, m) for m in g)]
            if len(fits) == 1:
                fits[0].append(c)
            elif not fits:
                groups.append([c])
        for g in groups:
            for m in g[1:]:
                parent[root(id(m))] = root(id(g[0]))
    sets: dict[int, list[dict]] = {}
    for c in people:
        if id(c) in parent:
            sets.setdefault(root(id(c)), []).append(c)
    return [rows for rows in sets.values() if len(rows) > 1]


def unify(db: dict) -> dict:
    """Fold every set of rows that are one person into one row. Idempotent; `{"merged": n, "into": [ids]}`."""
    from . import fusion
    contacts = db.setdefault("contacts", [])
    apart, merged, into_ids = apart_pairs(db), 0, []
    for rows in _clusters(contacts, apart):
        keep = fusion.keeper(rows)
        for other in rows:
            if other is keep or frozenset((str(keep.get("id")), str(other.get("id")))) in apart:
                continue
            fusion.fold(db, keep, other, by="key")
            merged += 1
        into_ids.append(keep.get("id"))
    return {"merged": merged, "into": into_ids}
