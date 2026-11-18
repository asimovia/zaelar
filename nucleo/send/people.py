"""WHO a said name is, for a send: the conversation he has open first, then his contacts ranked.

No model and no guess. One person → that person (with the channel the send will use). Several, or a name only part of
which anyone carries → the people to ask him among, by name, closest first. Nobody → nobody.
"""
from __future__ import annotations

from loguru import logger

#: How many people one question names.
ASK_MAX = 6


def _note(e: Exception) -> None:
    logger.debug(f"send.people: {type(e).__name__}: {e}")


def _row(c: dict, note: str = "") -> dict:
    return {"name": str(c.get("name") or ""), "contact_id": str(c.get("id") or ""), "note": note}


def _in_front(name: str) -> dict:
    """The conversation open on the messaging card when his word names it: `{name, platform}`; {} otherwise."""
    try:
        from widgets import directory
        from widgets.mensajeria import data as _md
        from widgets.mensajeria.outbound import in_front
        got = in_front.named(_md.load_db(), name, "", directory) or {}
        if got.get("ok"):
            return {"name": str(got.get("name") or ""), "platform": str(got.get("platform") or ""),
                    "contact_id": str(got.get("contactId") or "")}
    except Exception as e:  # noqa: BLE001
        _note(e)
    return {}


def resolve(name: str, channel: str = "") -> dict:
    """`{"one": {name, contact_id, platform}}` · `{"several": [{name, contact_id, note}], "unmatched": [...]}` ·
    `{"none": True}`. `platform` is "" when the person's own channel is to be used."""
    q = " ".join(str(name or "").split())
    if not q:
        return {"none": True}
    front = _in_front(q)
    if front.get("name"):
        return {"one": {**front, "platform": channel or front.get("platform", "")}}
    try:
        from widgets.contactos import who
        got = who.find(q)
    except Exception as e:  # noqa: BLE001
        _note(e)
        return {"none": True}
    people = [r["contact"] for r in got.get("people") or []]
    if got.get("confidence") == "one" and people:
        return {"one": {**_row(people[0]), "platform": channel}}
    if people:
        return {"several": [_row(c, _apart(c)) for c in people[:ASK_MAX]], "unmatched": list(got.get("unmatched") or [])}
    return {"none": True}


def chosen(name: str, candidates: list[dict], channel: str = "") -> dict:
    """A name he gave while being asked among `candidates`: the candidate it names exactly (by its full name), else
    the name resolved afresh."""
    said = " ".join(str(name or "").lower().split())
    for c in candidates or ():
        if said and said == " ".join(str(c.get("name") or "").lower().split()) and c.get("contact_id"):
            return {"one": {"name": c["name"], "contact_id": c["contact_id"], "platform": channel}}
    return resolve(name, channel)


def named(query: str) -> list[str]:
    """The names of the people a word names, closest first — what he asks for with «which <name>s do you have?»."""
    got = resolve(query)
    if got.get("one"):
        return [got["one"]["name"]]
    return [c["name"] for c in got.get("several") or []]


def _apart(c: dict) -> str:
    """What tells this person apart from a namesake (a city, a company), or ""."""
    try:
        from widgets import directory
        from widgets.mensajeria.outbound import targets
        return targets._apart(c, directory) or ""
    except Exception as e:  # noqa: BLE001
        _note(e)
        return ""


def conversation(n=None) -> dict:
    """The conversation a reply goes to — the message numbered `n` on the card, else the one he has open:
    `{name, contact_id, platform, chat_id}`; {} when there is none."""
    try:
        from widgets import directory
        from widgets.mensajeria import data as _md
        from widgets.mensajeria.outbound import in_front, targets
        db = _md.load_db()
        if n not in (None, ""):
            it = targets.resolve_reply_target(db, int(n) if str(n).strip().isdigit() else n) or {}
            front = {"platform": str(it.get("platform") or ""), "chatId": str(it.get("chatId") or ""),
                     "name": str(it.get("chatName") or it.get("senderName") or it.get("from") or "")}
        else:
            front = in_front.conversation(db) or {}
        if not front.get("platform") or not front.get("chatId"):
            return {}
        row = directory.find_by_channel(front["platform"], front["chatId"]) or {}
        return {"name": str(row.get("name") or front.get("name") or front["chatId"]),
                "contact_id": str(row.get("id") or ""), "platform": front["platform"], "chat_id": front["chatId"]}
    except Exception as e:  # noqa: BLE001
        _note(e)
        return {}

