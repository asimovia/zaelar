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
                    "contact_id": str(got.get("contactId") or ""), "chat_id": str(got.get("chatId") or "")}
    except Exception as e:  # noqa: BLE001
        _note(e)
    return {}


def resolve(name: str, channel: str = "", relation: str = "") -> dict:
    """`{"one": {name, contact_id, platform}}` · `{"several": [{name, contact_id, note}], "unmatched": [...]}` ·
    `{"none": True}`. `platform` is "" when the person's own channel is to be used."""
    q = " ".join(str(name or "").split())
    if relation:                         # «mum»: only the people he said are that, never a name carrying the word
        try:
            from widgets import directory
            hits = list(directory.by_relation(relation.strip().lower()) or [])
        except Exception as e:  # noqa: BLE001
            _note(e)
            hits = []
        if len(hits) == 1:
            return {"one": {**_row(hits[0]), "platform": channel}}
        if hits:
            return {"several": [_row(c, _apart(c)) for c in hits[:ASK_MAX]], "unmatched": []}
    if not q:
        return {"none": True}
    front = _in_front(q)
    if front.get("name") and (not channel or channel == front.get("platform")):
        return {"one": front}             # the open chat, on ITS platform (another channel is the person's, below)
    try:
        from widgets.contactos import who
        got = who.find(q)
    except Exception as e:  # noqa: BLE001 — an unreadable directory is not «nobody has that name»
        _note(e)
        return {"several": [], "unread": True}
    people = [r["contact"] for r in got.get("people") or []]
    if got.get("confidence") == "one" and people:
        return {"one": {**_row(people[0]), "platform": channel}}
    if people:
        return {"several": [_row(c, _apart(c)) for c in people[:ASK_MAX]], "unmatched": list(got.get("unmatched") or [])}
    return {"none": True}


def chosen(name: str, candidates: list[dict], channel: str = "") -> dict:
    """A name he gave while being asked among `candidates`: the candidate it names exactly (by its full name), else
    the name resolved afresh."""
    from nucleo.send import ask
    said = ask._fold(name)
    if not said:
        return resolve(name, channel)
    full = [c for c in candidates or () if c.get("contact_id")
            and said == ask._fold(f"{c.get('name')} {c.get('note') or ''}")]
    named_ = [c for c in candidates or () if c.get("contact_id") and said == ask._fold(c.get("name"))]
    hits = full or named_
    if len(hits) == 1:                       # by the row he picked — two people of one name are told apart by note
        c = hits[0]
        same = sum(1 for x in candidates if ask._fold(x.get("name")) == ask._fold(c.get("name"))) > 1
        return {"one": {"name": c["name"], "contact_id": c["contact_id"], "platform": channel,
                        **({"note": c.get("note") or ""} if same else {})}}
    if len(hits) > 1:                        # he named a name several of them carry: ask among THEM, by what differs
        return {"several": hits, "unmatched": []}
    return resolve(name, channel)


def named(query: str) -> list[str]:
    """The names of the people a word names, closest first — what he asks for with «which <name>s do you have?»: his
    contacts only (an open conversation is one of them, never the whole answer)."""
    try:
        from widgets.contactos import who
        return [str(r["contact"].get("name") or "") for r in who.find(query).get("people") or []][:ASK_MAX]
    except Exception as e:  # noqa: BLE001
        _note(e)
        return []


def _apart(c: dict) -> str:
    """What tells this person apart from a namesake (a city, a company), or ""."""
    try:
        from widgets import directory
        from widgets.mensajeria.outbound import targets
        return targets._apart(c, directory) or ""
    except Exception as e:  # noqa: BLE001
        _note(e)
        return ""


def open_conversation() -> dict:
    """The conversation open on the messaging card, as a target `{name, contact_id, platform, chat_id}`; {} when none."""
    try:
        from nucleo.send import deliver
        from widgets.mensajeria import data as _md
        from widgets.mensajeria.outbound import in_front
        return deliver._chat({**(in_front.conversation(_md.load_db()) or {})})
    except Exception as e:  # noqa: BLE001
        _note(e)
        return {}
