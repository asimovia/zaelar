"""widgets/chat_names.py — the name and picture of the other side of a conversation, for every list that shows one.

`directory.namer` is the door (V2-819); this module is its lookups. A card's view names dozens of rows and is read
many times between two writes of the contacts store, so the directory is INDEXED once per version of that store and a
row is named by three dictionary reads. Measured on a live engine (2026-11-19): naming each row by walking every
channel, address and number of thousands of contacts held the loop 1–5 s per view.
"""
from __future__ import annotations

from .directory import _PHONE_MIN_DIGITS, _digits, _emails, _norm, _phone_of, _phones


def _photo(contact: dict) -> str:
    """A picture the card can draw without a fetch of its own: same-origin or inline. A remote URL is left out
    rather than handed to a widget that must never reach the network (widgets/validator.py)."""
    a = str((contact or {}).get("avatar") or "").strip()
    return a if a.startswith(("/widgets/", "data:image/")) else ""


#: The directory as the namer last indexed it, and the version of the store it was read from (`store.version`).
_NAMES: dict = {"key": None, "index": None}


def _name_index(people: list[dict]) -> tuple[dict, dict, dict]:
    """Who holds each conversation, address and number — three lookups built in ONE pass over the directory, so
    naming a row never walks it again: (platform, chatId) → contacts · address → contacts · the number's last
    `_PHONE_MIN_DIGITS` digits → (digits, contact) (two numbers that are the same share at least that suffix)."""
    by_chat: dict = {}
    by_mail: dict = {}
    by_tel: dict = {}
    plat: dict = {}

    def _add(table: dict, key, value, c: dict) -> None:
        lst = table.setdefault(key, [])
        if not (lst and lst[-1][1] is c and lst[-1][0] == value):
            lst.append((value, c))

    for c in people:
        if not (isinstance(c, dict) and c.get("kind") != "group" and str(c.get("name") or "").strip()):
            continue
        for ch in c.get("channels") or []:
            raw = ch.get("platform")
            p = plat.get(raw) if isinstance(raw, str) else None
            if p is None:
                p = _norm(raw)
                if isinstance(raw, str):
                    plat[raw] = p
            _add(by_chat, (p, str(ch.get("chatId") or "")), None, c)
        for a in _emails(c):
            _add(by_mail, _norm(a), None, c)
        for t in _phones(c):
            d = _digits(t)
            if len(d) >= _PHONE_MIN_DIGITS:
                _add(by_tel, d[-_PHONE_MIN_DIGITS:], d, c)
    return by_chat, by_mail, by_tel


def _names_of_the_store() -> tuple[dict, dict, dict]:
    """The index of the contacts store, built once per VERSION of it (any write, by this process or another, is a
    new one)."""
    from . import store
    from .contactos import data as _cd
    ver = store.version(_cd.WIDGET_ID)      # read BEFORE the store: a write that lands meanwhile misses next time
    key = None if ver is None else (ver, _cd.load_db)
    if key is None or key != _NAMES["key"]:
        try:
            people = _cd.visible(_cd.load_db())
        except Exception:  # noqa: BLE001 — no directory: every name stays what the platform said
            people = []
        _NAMES.update({"key": key, "index": _name_index(people)})
    return _NAMES["index"]


def namer(people: list[dict] | None = None):
    """ONE resolver for the name and picture of the other side of a conversation, for every list and header
    that shows one. The directory is INDEXED once per version of its store — a view names dozens of rows, and a
    card's view is read many times between two writes.

        name = namer()
        name("whatsapp", "34600111222@s.whatsapp.net", fallback="Mamá ❤")  ->  {"name": "mama", "photo": ""}

    Order, each step only when the previous one has nothing: the contact holding this conversation → the contact
    whose phone/address the id carries → the platform's display name (`fallback`) → the bare id. A contact match
    must be UNIQUE: two rows with the same number is an ambiguity, and the platform's name is then more honest."""
    by_chat, by_mail, by_tel = _names_of_the_store() if people is None else _name_index(people)

    def _one(hits: list) -> dict | None:
        uniq = {id(c): c for _v, c in hits}
        return next(iter(uniq.values())) if len(uniq) == 1 else None

    def resolve(platform: str, chat_id, fallback: str = "") -> dict:
        p, cid = _norm(platform), str(chat_id or "").strip()
        hit = None
        if p and cid:
            hit = _one(by_chat.get((p, cid), ()))
            if hit is None and p == "email" and "@" in cid:
                hit = _one(by_mail.get(_norm(cid), ()))
            if hit is None:
                tel = _phone_of(p, cid)
                if len(tel) >= _PHONE_MIN_DIGITS:
                    hit = _one([(d, c) for d, c in by_tel.get(tel[-_PHONE_MIN_DIGITS:], ())
                                if d.endswith(tel) or tel.endswith(d)])
        if hit is not None:
            return {"name": str(hit.get("name")).strip(), "photo": _photo(hit), "contactId": str(hit.get("id") or "")}
        name = str(fallback or "").strip() or cid.split("@", 1)[0]
        return {"name": name, "photo": "", "contactId": ""}

    return resolve
