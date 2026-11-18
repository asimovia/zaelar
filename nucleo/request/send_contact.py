"""nucleo/request/send_contact.py — the send worker's bridge act `find_contact`: WHO his word can be.

The worker hands over the name he said; it gets back the rows of his contacts RANKED, each with how sure the match
is (`widgets/contactos/who`), and — before any of them — the conversation he has open when his word names it. A word
of his that nobody carries makes the answer `partial`: names to ask him among, never a match (measured 2026-11-18:
a first name plus a word no row had came back as six people of that first name, as if they were the answer).
"""
from __future__ import annotations

from loguru import logger


def _note(e: Exception) -> None:
    logger.debug(f"send_contact: {type(e).__name__}: {e}")


def find_contact(name: str) -> dict:
    """Bridge act `find_contact`: who his word can be — the rows of his contacts, RANKED, each with how sure the
    match is (`widgets/contactos/who.find`: word, sound, stem, a slip of spelling, any order, an address that sounds
    like it), and their channels. `match` says what the worker holds: `one` person, `several` to ask among, or
    `partial` — some word he said is on these rows and `unmatched` is on nobody's: a question with names, never a
    match. When no row is named, the people his memory points at for that description («my sister»)."""
    q = " ".join(str(name or "").split())
    if not q:
        return {"ok": False, "error": "find_contact needs the name or description he used"}
    rows, match, unmatched = [], "", []
    try:
        from widgets.contactos import data as _cd, digest as _dg, who
        got = who.find(q)
        match, unmatched = got["confidence"], list(got["unmatched"])
        for r in got["people"]:
            row = dict(_dg._aka(r["contact"]), confidence=r["confidence"])
            row.pop("phone", None)                     # who and by which platforms; a number is nothing he asked for
            if r["missing"]:
                row["not_in_the_name"] = list(r["missing"])
            rows.append(row)
        if got.get("more") and rows:
            rows[-1]["more"] = got["more"]
        if not rows:
            match, rows = "", list(_cd.people_named(q, limit=6) or [])
    except Exception as e:  # noqa: BLE001
        _note(e)
    if not rows:
        try:
            from nucleo.memory_agent import contacts as _mc
            rows = [{"name": w.get("name"), "contact_id": w.get("contact_id"),
                     "why": [x.get("text") for x in (w.get("evidence") or [])][:2]} for w in _mc.who(q)]
        except Exception as e:  # noqa: BLE001
            _note(e)
    out = {"query": q, "people": rows,
           "note": "one person → use that name; several → ask him which, naming them; none → ask him who it is"}
    if match:
        out["match"] = match
    if match == "partial":
        out["unmatched"] = unmatched
        out["note"] = ("NOBODY in his contacts carries every word he said" + (f" (no one has «{' '.join(unmatched)}»)"
                       if unmatched else "") + ": `people` only share part of the name, closest first. That is not a "
                       "match — ask him which he means, naming them; never pick one")
    front = _in_front(q) or (_front_shares(q) if match in ("partial", "") else {})
    if front.get("shares"):   # he is looking at somebody a word of his names and the rest does not: asked FIRST
        out["in_front"] = front
        out["note"] = ("`in_front` is the conversation he has open; it carries part of the name he said. Ask him if he "
                       "means that one, naming it first. " + out["note"])
    elif front:    # what he is LOOKING AT is the first reading of the name (measured 2026-11-18: her chat was open
        out["in_front"] = front        # and the message was offered to another row of hers, by mail)
        out["note"] = ("`in_front` is the conversation he has open and his word names it: write THERE — pass its "
                       "`name` as the contact" + ("; somebody else holds that word as his own for them: ask him which "
                                                  "of the two, the open one first" if front.get("ask") else "")
                       + ". Otherwise: " + out["note"])
    return {"ok": True, "result": out}


def _front_shares(name: str) -> dict:
    """The conversation open on the messaging card when it carries PART of the name he said and no row carries all
    of it: `{name, platform, shares: True}`; {} otherwise."""
    try:
        from widgets import directory
        from widgets.contactos import who
        from widgets.mensajeria import data as _md
        from widgets.mensajeria.outbound import in_front
        front = in_front.conversation(_md.load_db())
        if not front or not front.get("name"):
            return {}
        owner = directory.find_by_channel(front["platform"], front["chatId"]) or {}
        seen = {"name": front["name"], "knownAs": [{"name": n} for n in (directory.names(owner) if owner else [])],
                "aliases": list(owner.get("aliases") or [])}
        if who.score(directory._norm(name), seen)["confidence"] == "partial":
            return {"name": front["name"], "platform": front["platform"], "shares": True}
    except Exception as e:  # noqa: BLE001 — unread: the directory's rows alone
        _note(e)
    return {}


def _in_front(name: str) -> dict:
    """The conversation open on the messaging card when `name` names it (`mensajeria/outbound/in_front`); {} else."""
    try:
        from widgets import directory
        from widgets.mensajeria import data as _md
        from widgets.mensajeria.outbound import in_front
        got = in_front.named(_md.load_db(), name, "", directory) or {}
        if got.get("ok"):
            return {"name": got["name"], "platform": got["platform"]}
        if got.get("ask"):
            return {"name": str(got["ask"][0].get("name") or ""), "ask": [str(c.get("name") or "") for c in got["ask"][1:]]}
    except Exception as e:  # noqa: BLE001 — unread: the directory's rows alone, as before
        _note(e)
    return {}
