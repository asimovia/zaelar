#
# found_mail.py — what an archive search FOUND, made usable by the card: a mail the card no longer holds is asked
# back from the mailbox, and the last find is remembered so «open it» has a referent.
#
import time

from .. import store
from .shape import WIDGET_ID, load_db


_BRING_BACK_MAX = 2


def _bring_back_found_mail(payload: dict) -> int:
    """A mail the archive found but this card no longer holds is asked back from the mailbox, attachments included.

    The card holds only the most recent unread; the archive keeps the mailbox UID, so the card's own «load previous»
    order (`fetch_older`, one message just below UID+1) brings exactly that mail back. Never raises; returns how many
    orders were queued."""
    try:
        from . import views as _v
        db = load_db()
        held = _held_mail(db)
        queued, seen = 0, set()
        for r in _v.archive_rows(payload):
            if queued >= _BRING_BACK_MAX:
                break
            chat, uid = str(r.get("chat_id") or ""), str(r.get("msg_id") or "")
            if (r.get("platform") != "email" or r.get("direction") != "in" or not chat or not uid.isdigit()
                    or (chat, uid) in held or chat in seen):
                continue
            seen.add(chat)
            _ask_back(db, chat, uid)
            queued += 1
        if queued:
            store.save(WIDGET_ID, db)
        return queued
    except Exception:  # noqa: BLE001
        return 0


def _held_mail(db: dict) -> set:
    """(chatId, message id) of every mail the card HOLDS — a pending row or a message of a thread. A conversation
    is not «held» by its key alone: a «load previous» that came back empty leaves an empty thread, and counting that
    as holding the mail kept the found mail from ever being asked back (live demo pass on b136, E2/E3)."""
    held = {(str(it.get("chatId")), str(it.get("messageId"))) for it in db.get("items", [])
            if it.get("platform") == "email"}
    for k, th in (db.get("threads") or {}).items():
        if str(k).startswith("email|") and isinstance(th, dict):
            chat = str(k).partition("|")[2]
            held |= {(chat, str(m.get("id"))) for m in th.get("msgs") or []}
    return held


def _ask_back(db: dict, chat: str, uid: str) -> None:
    """Queue the card's own «load previous» order for exactly that mail (one message just below UID+1)."""
    db.setdefault("pending_history", []).append(
        {"platform": "email", "chatId": chat, "beforeTs": 0, "beforeId": str(int(uid) + 1), "limit": 1})


def await_found(db: dict, platform, chat_id) -> bool:
    """Opening the mail the card last found while the card does not hold it yet: ask it back and keep the
    conversation open while it arrives (`opening`), instead of an open that auto-closes on an empty thread. True
    when it is on its way. Mutates `db`; the caller saves."""
    lf = last_found(db)
    uid = str((lf or {}).get("uid") or "")
    if (not lf or platform != "email" or (lf.get("platform"), str(lf.get("chatId"))) != (platform, str(chat_id))
            or not uid.isdigit()):
        return False
    if (str(chat_id), uid) not in _held_mail(db):
        if not any(o.get("chatId") == str(chat_id) and o.get("beforeId") == str(int(uid) + 1)
                   for o in db.get("pending_history") or [] if isinstance(o, dict)):
            _ask_back(db, str(chat_id), uid)
    db["opening"] = {"key": f"{platform}|{chat_id}", "at": time.time()}
    return True


FOUND_TTL_S = 1800


def _remember_found(payload: dict) -> None:
    """The mail an archive search found, so «open it» has a referent even when it is not in the inbox list: what the
    card last found is a fact of the card, like what it last sent. Never raises."""
    try:
        from . import views as _v
        row = next((r for r in _v.archive_rows(payload) if r.get("direction") == "in" and r.get("chat_id")), None)
        if row is None:
            return
        db = load_db()
        body = str(row.get("body") or "")
        subject = body[len("[Asunto: "):body.index("]")] if body.startswith("[Asunto: ") and "]" in body else ""
        db["last_found"] = {"platform": str(row.get("platform") or ""), "chatId": str(row.get("chat_id")),
                            "name": str(row.get("chat_name") or row.get("sender") or row.get("chat_id")),
                            "subject": subject[:120], "uid": str(row.get("msg_id") or ""), "at": time.time()}
        store.save(WIDGET_ID, db)
    except Exception:  # noqa: BLE001
        pass


def last_found(db: dict) -> dict | None:
    """The fresh `last_found` of this card, or None."""
    lf = db.get("last_found")
    if isinstance(lf, dict) and lf.get("chatId") and time.time() - float(lf.get("at") or 0) < FOUND_TTL_S:
        return lf
    return None
