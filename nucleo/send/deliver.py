"""How a message leaves: ONE act of the card, `send_to`, to a person or a conversation already chosen by id, with the
text he heard — never a screen position or a name read again at the moment it leaves.

Whatever the model called, it is read ONCE when the message is handed over (`adopt`):
  · a reply (`reply {n}` or the open conversation) → that conversation, by its chat id;
  · a forward (`forward {n | messageId | from}`) → its source message, by its message id, whose files travel along;
  · a draft on the card (`send_draft`, `compose`) → that draft's text and conversation;
  · a time (`at`, `in_minutes`) → the moment, read now; the message is then written as the card's held draft and
    sent with its time (`send_draft` by the draft's own key).
`check` resolves the target READ-ONLY before he is asked: a channel to choose, a channel down, no way to reach her or
a time that cannot be read is said BEFORE the confirmation, never after his yes.
"""
from __future__ import annotations

from loguru import logger

WIDGET = "mensajeria"
#: The fields of the model's call that ride with the message as they were given.
CARRIED = ("subject", "objective", "files")
#: A time he asked for.
LATER = ("at", "in_minutes")


def _note(e: Exception) -> None:
    logger.debug(f"send.deliver: {type(e).__name__}: {e}")


def _db():
    from widgets.mensajeria import data as _md
    return _md.load_db()


def _chat(it: dict | None) -> dict:
    """A card item or thread row as a target: `{name, contact_id, platform, chat_id}`; {} when it has no chat."""
    it = it or {}
    platform, chat = str(it.get("platform") or ""), str(it.get("chatId") or "")
    if not (platform and chat):
        return {}
    from widgets import directory
    row = directory.find_by_channel(platform, chat) or {}
    name = str(row.get("name") or it.get("chatName") or it.get("senderName") or it.get("from") or it.get("name") or chat)
    return {"name": name, "contact_id": str(row.get("id") or ""), "platform": platform, "chat_id": chat}


def adopt(act: str, hint: dict) -> dict:
    """What the model's call means, read ONCE now: `{target?, text?, extra}` — `target` when the call names a
    conversation (a reply, a draft), `extra` the fields that ride with the message (a forward's source by id, a time
    already read, a subject, files)."""
    h = dict(hint or {})
    out: dict = {"extra": {k: h[k] for k in CARRIED if h.get(k) not in (None, "", [], {})}}
    try:
        db = _db()
        from widgets.mensajeria.outbound import targets
        if act == "reply":
            n, mid = h.get("n"), h.get("messageId")
            if n is not None:
                from widgets.mensajeria.actions.send import reply_target
                item = reply_target(db, int(n) if str(n).strip().isdigit() else n)
            else:
                item = targets.resolve_reply_target(db, None, mid)
            out["target"] = _chat(item)
            if out["target"]:          # the message it answers, by id: it threads, and is never read by position again
                out["extra"].update(reply_chat=out["target"]["chat_id"], reply_to=str((item or {}).get("messageId") or ""))
        elif act == "forward" or h.get("attach_from") not in (None, ""):
            af = h.get("attach_from")
            src = {k: h[k] for k in ("n", "messageId", "from") if h.get(k) not in (None, "")} if act == "forward" else (
                af if isinstance(af, dict) else ({"n": af} if str(af or "").strip() else {}))
            ref = targets._message_ref(db, src) or {}
            src = {"messageId": str(ref["messageId"])} if ref.get("messageId") else {k: v for k, v in src.items() if k == "from"}
            out["extra"]["attach_from"] = src
            out["extra"]["files_n"] = len(targets.attachments_of(db, src) or []) if src else 0
            if ref.get("subject") and "subject" not in out["extra"]:
                out["extra"]["subject"] = f"Fwd: {ref['subject']}"
        elif act in ("send_draft", "compose"):
            from widgets.mensajeria.actions.send import draft_named
            _key, dr, text, _files, refused = draft_named(db, h)
            if not refused:
                t = dr.get("target") or {}
                out["text"] = text
                out["target"] = _chat(t) or ({"name": str(t.get("name") or ""), "contact_id": str(t.get("contactId") or ""),
                                              "platform": str(t.get("platform") or "")} if t.get("name") else {})
        if any(h.get(k) not in (None, "") for k in LATER):
            from widgets.mensajeria import held
            ts, bad = held.when({k: h.get(k) for k in LATER})
            out["extra"]["at_ts" if not bad else "bad_time"] = ts if not bad else bad
    except Exception as e:  # noqa: BLE001 — unread: the message is asked about as a new one
        _note(e)
    if "target" in out and not out["target"]:
        out.pop("target")
    return out


def recipient(d) -> dict:
    """The chosen person or conversation as `send_to` names it: the row id, else the chat id, with the channel."""
    p = {"contact": d.target.get("name") or d.who}
    if d.target.get("contact_id"):
        p["contact_id"] = d.target["contact_id"]
    elif d.target.get("chat_id"):
        p["chat_id"] = d.target["chat_id"]
        if d.target.get("platform"):          # a chat lives on ONE platform: no other channel applies to it
            p["channel"] = d.target["platform"]
            return p
    if d.target.get("platform") or d.channel:
        p["channel"] = d.target.get("platform") or d.channel
    return p


def payload(d) -> dict:
    return {**{k: v for k, v in d.extra.items() if k in CARRIED + ("attach_from",)}, **recipient(d), "text": d.text}


def at(d) -> float:
    """The moment he asked it to leave (0.0: now)."""
    return float(d.extra.get("at_ts") or 0.0)


def check(d) -> dict:
    """`{"ok": True, "platform": …}` when the message can go as it stands; otherwise what stops it:
    `{"ok": False, "channels": [...]}` (he picks one) or `{"ok": False, "why": "…"}`."""
    if d.extra.get("bad_time"):
        return {"ok": False, "why": "the time he gave cannot be read or is too far ahead"}
    if "attach_from" in d.extra:
        if not d.extra.get("files_n"):
            return {"ok": False, "why": "the message he wants forwarded has no files that can be found"}
        if at(d):
            return {"ok": False, "why": "a forward with its files cannot be scheduled, only sent now"}
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
    """The card's act, blocking (call it off the loop): `send_to` now, or the held draft sent at its time. Returns
    `{"ok", "ref"?, "later"?, "error"?}`."""
    from widgets.mensajeria import data as _md
    p = payload(d)
    when = at(d)
    if d.extra.get("reply_chat") and d.extra["reply_chat"] == d.target.get("chat_id"):
        return _reply(d, when)
    if when:
        wrote = _md.apply_action("draft", p)
        if not (isinstance(wrote, dict) and wrote.get("ok") and wrote.get("key")):
            return {"ok": False, "error": str((wrote or {}).get("message") or (wrote or {}).get("error") or "no draft")}
        res = _md.apply_action("send_draft", {"key": wrote["key"], "in_minutes": max(0.1, (when - _now()) / 60.0)})
        return {**(res if isinstance(res, dict) else {}), "later": when}
    res = _md.apply_action("send_to", p)
    return res if isinstance(res, dict) else {"ok": False, "error": "no answer from the card"}


def _reply(d, when: float) -> dict:
    """A reply to the conversation it answers, threaded on the message it answers (found by id, never by position)."""
    from widgets.mensajeria import data as _md
    from widgets.mensajeria.outbound import queue, targets
    db = _md.load_db()
    mid = str(d.extra.get("reply_to") or "")
    item = (targets.resolve_reply_target(db, None, mid) if mid else None) or {
        "platform": d.target.get("platform"), "chatId": d.target.get("chat_id")}
    ref = queue.new_ref()
    queue.enqueue_reply(db, item, d.text, not_before=when, ref=ref)
    _md.store.save(_md.WIDGET_ID, db)
    return {"ok": True, "ref": ref, **({"later": when} if when else {})}


def _now() -> float:
    import time
    return time.time()


def ref_of(result) -> str:
    from nucleo.request import send_receipt
    return send_receipt._ref_of(result)
