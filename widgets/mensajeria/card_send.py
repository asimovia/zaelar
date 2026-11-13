"""card_send.py — the card's own Send button: his text, for the conversation on screen, answered (V2-819).

His order from his own hand, in his own card, is the send. Three things the old path got wrong, each one a way for
a send to vanish without a word:

  · it took TWO actions (`draft`, then a bare `send_draft {}`), and the second one sent «the most recent draft» —
    whatever conversation that was — instead of the one on screen;
  · the card cleared the box the moment the order was queued, while the owner dropped what the action returned and
    the connectors' reply paths told only the brain;
  · a platform that was not connected took the order anyway, and nothing ever drained it.

Here the order carries the box's text, names its conversation (`chat` for a thread, `n`/`messageId` for one mail)
and a `ref`; it is checked BEFORE it is queued (`check`, read-only, the backed route's veto), and its outcome is a
row in the outbox (`sent.outbox_*`) that the card reads to clear the box — or to keep his text and say why.
"""
from __future__ import annotations

import logging

from . import data as _d
from . import sent as _sent
from .words import say as _say

logger = logging.getLogger("zaelar.mensajeria.card_send")


def is_card_send(payload: dict) -> bool:
    """The composer's order: the box's text with the `ref` the card will look for. A voice «envíalo» carries
    neither and keeps its own path (the held draft, named by recipient or the most recent one)."""
    p = payload if isinstance(payload, dict) else {}
    return bool(str(p.get("ref") or "").strip()) and "text" in p


def _target(db: dict, payload: dict) -> dict | None:
    """The conversation this order names — never «whatever was touched last»."""
    if payload.get("n") is not None or payload.get("messageId"):
        return _d._outbound.resolve_reply_target(db, payload.get("n"), payload.get("messageId"))
    chat = payload.get("chat") if isinstance(payload.get("chat"), dict) else None
    if not chat or not chat.get("platform") or chat.get("chatId") in (None, ""):
        return None
    key = (str(chat["platform"]), str(chat["chatId"]))
    msgs = [it for it in db.get("items", []) if (it.get("platform"), str(it.get("chatId"))) == key]
    return msgs[-1] if msgs else {"platform": key[0], "chatId": key[1]}


def check(db: dict, payload: dict) -> tuple[dict | None, dict | None]:
    """`(target, None)` when the order can be queued, `(None, refusal)` when it cannot. Never writes."""
    target = _target(db, payload)
    if target is None:
        return None, {"ok": False, "error": "no_target",
                      "message": _say("no_conversation", "I don't know which conversation it goes to: open it and send it again.")}
    text = str(payload.get("text") or "")
    files = _d._media.local_paths(_d.store.data_dir(_d.WIDGET_ID), payload.get("files"))
    if not text.strip() and not files:
        return None, {"ok": False, "error": "empty", "message": _say("nothing_written", "There is nothing written to send.")}
    platform = str(target.get("platform") or "")
    status = str(((db.get("platforms") or {}).get(platform) or {}).get("status") or "off")
    if status != "connected":
        label = {"whatsapp": "WhatsApp", "telegram": "Telegram"}.get(platform) or (_say("email_channel", "Email") if platform == "email" else platform)
        return None, {"ok": False, "error": "not_connected",
                      "message": _say("not_connected_now", "{channel} is not connected right now, so nothing was sent.", channel=label)}
    return target, None


def send(payload: dict) -> dict:
    """Queue the card's send and open its outbox row; a refusal settles the row at once, with the reason."""
    db = _d.load_db()
    ref = str(payload.get("ref") or "").strip()
    target, refusal = check(db, payload)
    chat = payload.get("chat") if isinstance(payload.get("chat"), dict) else {}
    platform = str((target or {}).get("platform") or chat.get("platform") or "")
    chat_id = (target or {}).get("chatId") if target else chat.get("chatId")
    _sent.outbox_queue(db, ref, platform, chat_id, str(payload.get("box_key") or ""), str(payload.get("text") or ""))
    if refusal is not None:
        _sent.outbox_settle(db, ref, False, refusal["message"])
        _d.store.save(_d.WIDGET_ID, db)
        logger.info(f"app send {ref} refused: {refusal['error']}")
        return refusal
    text = str(payload.get("text") or "")
    files = _d._media.local_paths(_d.store.data_dir(_d.WIDGET_ID), payload.get("files"))
    reply_all = bool(payload.get("reply_all"))
    cc = [str(a) for a in (target.get("recipients") or []) if str(a).strip()] if reply_all else []
    _d._outbound.enqueue_reply(db, target, text, cc=cc, attachments=files, ref=ref)
    # The conversation's autosaved draft WAS this text: it leaves with it, and only it.
    _d._drafts.forget(db, _d._drafts.key(target))
    _d.store.save(_d.WIDGET_ID, db)
    return {"ok": True, "ref": ref, "to": target.get("senderId") or target.get("chatId"), "text": text,
            "attachments": len(files)}


def answer_action(action: str, payload: dict | None = None) -> dict | None:
    """The backed route's read-only veto (`data.answer_action`): the card's own Send is checked BEFORE it is
    queued — a send that cannot leave answers the button now, with the reason, and the card keeps his text. Every
    other action is answered by `answers.answer_action`, unchanged."""
    if action == "send_draft" and is_card_send(payload or {}):
        _target, refusal = check(_d.load_db(), payload or {})
        return refusal
    from . import answers
    return answers.answer_action(action, payload)
