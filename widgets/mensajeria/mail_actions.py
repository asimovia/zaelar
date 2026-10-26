"""The email section's actions — folders, one message, one draft on screen (mailbox.py holds the state).

Its own module because `actions.py` is near the file ceiling. Same contract: each handler reads `data` through `_d`,
so a patch on `data` still governs every call, and `data.ACTIONS` maps the names here.
"""
from __future__ import annotations

from . import data as _d
from . import mailbox as _mbx


def _rows_answer(db: dict) -> dict:
    v = _mbx.view(db)
    return {"folder": v["folder"], "role": v["role"], "category": v["category"], "unread": v["unread"],
            "categories": [c["key"] for c in v["categories"]], "loading": v["loading"],
            "messages": [{"from": r.get("fromName") or r.get("from"), "subject": r.get("subject"),
                          "unread": not r.get("seen")} for r in v["rows"][:10]]}


def _shown(db: dict, platform: str = "email") -> None:
    """The card follows: the section's lens moves to `platform`, through the same witness counter as show_view."""
    db["active_chat"] = None
    _d._push_view(db, platform)


# «Enséñame los enviados», «abre la papelera», «enséñame promociones», a tap on a folder or a category.
def _a_mail_folder(action, payload) -> dict:
    db = _d.load_db()
    _mbx.go(db, str(payload.get("folder") or "inbox"), payload.get("category"))
    _shown(db)
    _d.store.save(_d.WIDGET_ID, db)
    return {"ok": True, "result": _rows_answer(db), **_d.view_data()}


# «Los de Amazon que vayan a Principal», «no me enseñes Social», «quita esa regla»: his criteria over the
# provider's categories, rows of the rules table (V2-807 T-03). Nothing moves in his real mailbox.
def _a_mail_sort(action, payload) -> dict:
    from . import mail_rules
    db = _d.load_db()
    declared = [str(c["key"]) for c in _mbx.categories(db, include_hidden=True)]
    out = mail_rules.apply(payload or {}, declared)
    if out.get("ok"):
        _mbx.rules_changed(db)
        _shown(db)
        _d.store.save(_d.WIDGET_ID, db)
        return {"ok": True, "result": {"changed": out["changed"], "rule": out["said"],
                                       "rules": [x["text"] for x in mail_rules.listing()]}, **_d.view_data()}
    return {**out, **_d.view_data()}


# «Cargar más» at the bottom of a folder.
def _a_mail_more(action, payload) -> dict:
    db = _d.load_db()
    folder = str((db.get("mailbox") or {}).get("folder") or "INBOX")
    cat = _mbx.view(db)["category"]
    asked = _mbx.ask(db, folder, category=cat, older=True)
    _d.store.save(_d.WIDGET_ID, db)
    return {"ok": True, "result": {"folder": folder, "asked": asked}, **_d.view_data()}


# A tap on a row of a folder: the message, whole card.
def _a_mail_open(action, payload) -> dict:
    uid = str(payload.get("uid") or "").strip()
    if not uid:
        return {"ok": False, "error": "falta `uid` — el mensaje de la carpeta que se abre", **_d.view_data()}
    db = _d.load_db()
    _mbx.open_message(db, uid, payload.get("folder"))
    _shown(db)
    _d.store.save(_d.WIDGET_ID, db)
    return {"ok": True, **_d.view_data()}


# «← Recibidos» on a message or a draft: one level up, to that folder's list.
def _a_mail_back(action, payload) -> dict:
    db = _d.load_db()
    key = (db.get("mailbox") or {}).get("draft")
    plat = str((((db.get("drafts") or {}).get(key) or {}).get("target") or {}).get("platform") or "email")
    _mbx.back(db)
    _shown(db, plat)
    _d.store.save(_d.WIDGET_ID, db)
    return {"ok": True, **_d.view_data()}


def _draft_key(db: dict, payload: dict) -> str | None:
    drafts = db.get("drafts") or {}
    key = str(payload.get("key") or "")
    if key in drafts:
        return key
    if payload.get("contact"):
        return _d._held.draft_for(db, str(payload["contact"]))
    newest = _d._held.held(db)
    return newest[0]["key"] if newest else None


# «Abre el borrador», «enséñame el correo que tenía a medias para CoverManager»: the draft fills the card, with
# everything it needs to be finished — recipient, subject, text, send, save, discard.
def _a_open_draft(action, payload) -> dict:
    db = _d.load_db()
    key = _draft_key(db, payload)
    if key is None:
        return {"ok": False, "error": "no_draft",
                "message": "No hay ningún borrador guardado" + (f" para {payload['contact']}"
                                                                 if payload.get("contact") else "") + ".",
                **_d.view_data()}
    d = db["drafts"][key]
    t = d.get("target") or {}
    _mbx.open_draft(db, key)
    _shown(db, str(t.get("platform") or "email"))
    _d.store.save(_d.WIDGET_ID, db)
    return {"ok": True, "result": {"key": key, "to": t.get("name") or t.get("to") or t.get("chatId"),
                                   "subject": t.get("subject") or "", "text": d.get("text") or "",
                                   "channel": t.get("platform")}, **_d.view_data()}


# The draft screen's Send (and the Save of a message NOT saved yet — «Redactar», «Responder» on a folder's mail):
# what is on screen becomes the draft and, with `send`, leaves — in ONE order. One action and not two because this card's
# taps are queued to its owner and answered with nothing — the screen learns the outcome from the state (`note`),
# and a failed send leaves the draft open with his text instead of losing it.
def _a_compose(action, payload) -> dict:
    db = _d.load_db()
    if str(payload.get("key") or "") in (db.get("drafts") or {}):
        # A draft already on screen: what he left there is written, then sent (or kept) — one order.
        out = _edit(db, str(payload["key"]), payload)
        if not out.get("ok") or not out.get("key"):
            _mbx.note(db, "not_sent" if payload.get("send") else "not_saved", out.get("error") or "")
            _d.store.save(_d.WIDGET_ID, db)
            return {**out, "ok": False, **_d.view_data()}
        return _finish(db, out["key"], bool(payload.get("send")))
    to = str(payload.get("to") or payload.get("contact") or "").strip()
    out = _d._a_draft("draft", {"contact": to, "subject": str(payload.get("subject") or ""),
                                "text": str(payload.get("text") or ""), "channel": payload.get("channel") or "email"})
    db = _d.load_db()
    if not out.get("ok") or not out.get("key"):
        _mbx.note(db, "not_saved", out.get("message") or out.get("error") or "")
        _d.store.save(_d.WIDGET_ID, db)
        return {**out, **_d.view_data()}
    return _finish(db, out["key"], bool(payload.get("send")))


def _finish(db: dict, key: str, send: bool) -> dict:
    """After a save: on screen with «Guardado», or sent and back to the folder — or, when the send fails, still on
    screen with the reason."""
    _mbx.open_draft(db, key)
    _shown(db, str((((db.get("drafts") or {}).get(key) or {}).get("target") or {}).get("platform") or "email"))
    if not send:
        _mbx.note(db, "saved")
        _d.store.save(_d.WIDGET_ID, db)
        return {"ok": True, "result": {"key": key, "saved": True}, **_d.view_data()}
    _d.store.save(_d.WIDGET_ID, db)
    sent = _d._a_send_draft("send_draft", {"key": key})
    db = _d.load_db()
    if sent.get("ok"):
        _mbx.back(db)
        _mbx.note(db, "sent")
    else:
        _mbx.note(db, "not_sent", sent.get("message") or sent.get("error") or "")
    _d.store.save(_d.WIDGET_ID, db)
    return {**sent, **_d.view_data()}


def _edit(db: dict, key: str, payload: dict) -> dict:
    """Write what he left on the draft screen into draft `key`: the text and, for a new message, its recipient
    and subject. A new recipient is re-resolved exactly like writing it did. Returns `{ok, key}` or a refusal."""
    d = db["drafts"][key]
    t = dict(d.get("target") or {})
    text = str(payload.get("text") if payload.get("text") is not None else d.get("text") or "")
    to = str(payload.get("to") or "").strip()
    if t.get("new") and to and to.lower() not in {str(t.get(f) or "").lower() for f in ("to", "name", "chatId")}:
        r = _d._outbound.resolve_target({"contact": to, "platform": t.get("platform"), "text": text or "-"})
        if not r.get("ok"):
            return r
        t = {**r, "new": True, "subject": t.get("subject") or ""}
    if t.get("new") and payload.get("subject") is not None:
        t["subject"] = str(payload["subject"]).strip()
    out = _d._drafts.write(db, t, text, bool(d.get("reply_all")), files=d.get("files"))
    if t.get("new") and out.get("key") and out["key"] != key:
        db["drafts"].pop(key, None)
    if out.get("cleared"):
        return {"ok": True, "key": None}
    if not t.get("new") and d.get("recipients"):
        db["drafts"][out["key"]]["recipients"] = d["recipients"]
    return {"ok": True, "key": out["key"]}


# «Guardar borrador» in the draft screen: what he left on screen, kept. Nothing leaves.
def _a_save_draft(action, payload) -> dict:
    db = _d.load_db()
    key = _draft_key(db, {"key": payload.get("key")}) if payload.get("key") else None
    if key is None:
        return {"ok": False, "error": "no_draft", "message": "Ese borrador ya no existe.", **_d.view_data()}
    out = _edit(db, key, payload)
    if not out.get("ok"):
        _mbx.note(db, "not_saved", out.get("error") or "")
        _d.store.save(_d.WIDGET_ID, db)
        return {**out, **_d.view_data()}
    if out["key"] is None:
        _d.store.save(_d.WIDGET_ID, db)
        return {"ok": True, "result": {"key": key, "saved": False}, **_d.view_data()}
    return _finish(db, out["key"], False)


# «Descartar» in the draft screen, or «tira ese borrador»: the draft goes, nothing is sent.
def _a_discard_draft(action, payload) -> dict:
    db = _d.load_db()
    key = _draft_key(db, payload)
    if key is None:
        return {"ok": False, "error": "no_draft", "message": "No hay ningún borrador que descartar.",
                **_d.view_data()}
    t = (db["drafts"][key].get("target") or {})
    _d._drafts.forget(db, key)
    _mbx.back(db)
    _d.store.save(_d.WIDGET_ID, db)
    return {"ok": True, "result": {"discarded": t.get("name") or t.get("to") or t.get("chatId")},
            **_d.view_data()}
