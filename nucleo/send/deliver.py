"""How a message leaves: the card's own act (the one he asked for — a new message, a reply, a forward), with the
person already chosen by id, and the act's other fields carried as he gave them.

`check` resolves the target READ-ONLY before he is asked: a channel to choose, a channel down or no way to reach her
is said BEFORE the confirmation, never after his yes.
"""
from __future__ import annotations

from loguru import logger

WIDGET = "mensajeria"
#: The acts a message can be: a new one, a reply to a message on the card, a forward. Anything else goes as a new one.
ACTS = ("send_to", "reply", "forward")
#: The fields of the act that are not the recipient or the text, carried from the model's call as he gave them.
EXTRA = ("n", "messageId", "attach_from", "files", "subject", "objective", "relation", "reply_all", "cc", "from",
         "at", "in_minutes")
#: A message he asked for LATER is written as a draft and sent with its time (`send_draft` holds it until then).
LATER = ("at", "in_minutes")


def _note(e: Exception) -> None:
    logger.debug(f"send.deliver: {type(e).__name__}: {e}")


def shape(hint: dict) -> tuple[str, dict]:
    """`(act, extra)` from the model's call: the act it named when it is a message act, and its other fields."""
    act = str((hint or {}).get("_act") or "send_to")
    extra = {k: hint[k] for k in EXTRA if k in (hint or {}) and hint[k] not in (None, "", [], {})}
    return (act if act in ACTS else "send_to"), extra


def recipient(d) -> dict:
    """The chosen person as the card's act names her: the row id, else the chat id, with the channel."""
    p = {"contact": d.target.get("name") or d.who}
    if d.target.get("contact_id"):
        p["contact_id"] = d.target["contact_id"]
    elif d.target.get("chat_id"):
        p["chat_id"] = d.target["chat_id"]
    if d.target.get("platform") or d.channel:
        p["channel"] = d.target.get("platform") or d.channel
    return p


def payload(d) -> dict:
    if d.act == "reply":                                   # a reply names its message, never a person
        return {**{k: v for k, v in d.extra.items() if k not in LATER}, "text": d.text}
    return {**{k: v for k, v in d.extra.items() if k not in LATER + ("n",)}, **recipient(d), "text": d.text}


def check(d) -> dict:
    """`{"ok": True, "platform": …}` when the message can go as it stands; otherwise what stops it:
    `{"ok": False, "channels": [...]}` (he picks one) or `{"ok": False, "why": "…"}`."""
    if d.act == "reply":
        return {"ok": True, "platform": d.target.get("platform") or ""}
    try:
        from widgets.mensajeria.outbound import targets
        got = targets.describe({**recipient(d), "text": d.text or "-"})
    except Exception as e:  # noqa: BLE001 — unread: the act itself refuses later, said then
        _note(e)
        return {"ok": True, "platform": d.target.get("platform") or d.channel}
    if got.get("ok"):
        return {"ok": True, "platform": str(got.get("platform") or "")}
    if got.get("slot") == "channel" and got.get("candidates"):
        return {"ok": False, "channels": [str(c) for c in got["candidates"]]}
    return {"ok": False, "why": str(got.get("error") or "it cannot be reached")[:240]}


def run(d) -> dict:
    """The card's act, blocking (call it off the loop)."""
    from widgets.mensajeria import data as _md
    p = payload(d)
    later = {k: d.extra[k] for k in LATER if k in d.extra}
    if later and d.act != "reply":
        wrote = _md.apply_action("draft", p)
        if not (isinstance(wrote, dict) and wrote.get("ok")):
            return wrote
        return _md.apply_action("send_draft", {"contact": p.get("contact"), **later})
    return _md.apply_action(d.act, p)


def ref_of(result) -> str:
    from nucleo.request import send_receipt
    return send_receipt._ref_of(result)
