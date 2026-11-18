"""widgets/mensajeria/outbound/in_front.py — the conversation he has OPEN is the first reading of a name it carries.

Measured 2026-11-18: with her chat open on the screen he said «send her a message» by her first name. The name was
resolved against the directory alone, which held another row of the same person — the one of his address book, with
only a mail address — and the reply offered to write there. What he is looking at was never a candidate.

So before the directory is asked, the name he said is read against the conversation in front of him: its own name
(the one the chat shows) and every name its contact is known by — a whole name, every word, or the same SOUND
(`directory.strength`, the one ranking). When it names that conversation, the message goes there.

One thing outranks the screen, and only as a QUESTION: a word HE gave to somebody else (`aliases`). Then both are
named, the one in front first, and his answer decides — a message to the wrong person cannot be taken back.
"""
from __future__ import annotations


def conversation(db: dict) -> dict | None:
    """`{platform, chatId, name}` of the conversation open on the card, or None."""
    active = (db or {}).get("active_chat")
    if not isinstance(active, dict) or not active.get("platform") or active.get("chatId") in (None, ""):
        return None
    platform, chat_id = str(active["platform"]), str(active["chatId"])
    from .. import chatlist, thread
    th = thread._thread(db, platform, chat_id, create=False) or {}
    name = str(th.get("name") or (chatlist.row(db, platform, chat_id) or {}).get("name") or "").strip()
    return {"platform": platform, "chatId": chat_id, "name": name}


def named(db: dict, who: str, want: str, d) -> dict | None:
    """What a send to `who` means when the conversation in front carries that name: the target (`ok: True`), the
    question between it and the person who holds the word as HIS alias (`ask`: the rows, the one in front first),
    or None — nothing is open, he named another channel, or the name is not this conversation's."""
    front = conversation(db)
    if not front or (want and want != front["platform"]):
        return None
    from ... import textmatch
    owner = d.find_by_channel(front["platform"], front["chatId"])
    seen = {"name": front["name"], "channels": [], "aliases": list((owner or {}).get("aliases") or []),
            "knownAs": [{"name": n} for n in (d.names(owner) if owner else [])]}
    for span in textmatch.spans(who):
        q = d._norm(span.strip(d._QUOTES))
        if not q or d.strength(q, seen) < d.SOUND:
            continue
        others = [c for c in d.resolve(span, tolerant=False, platform=want or "")
                  if str(c.get("id")) != str((owner or {}).get("id") or "") and d.strength(q, c) == d.ALIAS]
        row = owner or {"id": "", "name": front["name"] or front["chatId"]}
        if others:
            return {"ask": [row] + others}
        return {"ok": True, "platform": front["platform"], "to": front["chatId"], "chatId": front["chatId"],
                "name": str(row.get("name") or front["name"]), "contactId": str(row.get("id") or ""),
                "known": owner is not None, "in_front": True}
    return None
