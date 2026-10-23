#
# chatlist.py — the CHAT LIST of a platform: every conversation the account has, newest first, independent of
# what triage kept. The inbox answers «what wants my attention»; this answers «what conversations do I have»,
# the first screen of the real app. Rows come from the connector (`chat_index`, one page at a time over
# `msg.chats`) and are moved forward live by the conversations this widget holds.
#
# The window is the operator's: what moved in the last RECENT_H hours shows on entry, and «Cargar más» walks
# back PAGE rows at a time — asking the connector for the next page when the index runs out. Everything here is
# server state, so a click and a voice order («enséñame más chats de WhatsApp») land on the same list.
#
# Same widget-package contract as data.py: stdlib plus the `widgets` package, never `connectors`.
#
import logging
import time

_log = logging.getLogger("zaelar.mensajeria.chatlist")

LIST_PLATFORMS = ("whatsapp", "telegram")
RECENT_H = 72
PAGE = 20
MIN_SHOWN = 10
REFRESH_S = 300          # entering a platform again refreshes the first page at most this often
ASK_TIMEOUT_S = 45       # an unanswered ask stops counting as «loading» after this


def _index(db: dict, platform: str) -> dict:
    return db.setdefault("chat_index", {}).setdefault(platform, {})


def _loading(idx: dict) -> bool:
    try:
        return bool(idx.get("asked_at")) and time.time() - float(idx["asked_at"]) < ASK_TIMEOUT_S
    except (TypeError, ValueError):
        _log.warning("chat list: unreadable ask time, treated as not loading")
        return False


def ask(db: dict, platform: str, *, older: bool = False) -> bool:
    """Queue one page for the connector. The first page is refreshed at most every REFRESH_S; an older page is
    asked only while the connector has not said the list is complete. Returns whether anything was queued."""
    if platform not in LIST_PLATFORMS:
        return False
    idx = _index(db, platform)
    if _loading(idx):
        return False
    if older:
        if idx.get("complete") or not idx.get("cursor"):
            return False
        before = idx["cursor"]
    else:
        try:
            if idx.get("answered_at") and time.time() - float(idx["answered_at"]) < REFRESH_S:
                return False
        except (TypeError, ValueError):
            _log.warning("chat list: unreadable answer time, refreshing")
        before = None
    db.setdefault("pending_chats", []).append({"platform": platform, "before": before, "limit": PAGE})
    idx["asked_at"] = time.time()
    return True


def _rows(db: dict, platform: str) -> list[dict]:
    """Index rows, moved forward by the conversations held here and marked with what the inbox holds."""
    idx = (db.get("chat_index") or {}).get(platform) or {}
    rows = {cid: dict(r) for cid, r in (idx.get("rows") or {}).items() if isinstance(r, dict)}
    for k, th in (db.get("threads") or {}).items():
        p, _, cid = str(k).partition("|")
        if p != platform or not cid or not isinstance(th, dict) or not th.get("msgs"):
            continue
        last = th["msgs"][-1]
        r = rows.get(cid) or {"chatId": cid, "kind": "group" if th.get("isGroup") else "person"}
        ts = float(last.get("ts") or 0)
        if ts >= float(r.get("ts") or 0):
            r.update({"ts": ts, "preview": last.get("body") or "", "mediaType": last.get("mediaType") or "",
                      "fromMe": last.get("dir") == "out"})
        r["name"] = r.get("name") or th.get("name") or ""
        rows[cid] = r
    for it in db.get("items") or []:
        if it.get("platform") != platform or it.get("chatId") is None:
            continue
        r = rows.get(str(it["chatId"]))
        if r is None:
            continue
        r["pending"] = int(r.get("pending") or 0) + 1
        r["forMe"] = bool(r.get("forMe") or it.get("dirigido_a_mi"))
        r["urgent"] = bool(r.get("urgent") or str(it.get("urgencia") or "").lower() in ("alta", "high"))
    out = [r for r in rows.values() if r.get("chatId")]
    for r in out:
        r["name"] = r.get("name") or str(r["chatId"]).split("@")[0]
        r["preview"] = str(r.get("preview") or "")[:160]
    out.sort(key=lambda r: (-float(r.get("ts") or 0)))
    return out


def view(db: dict, platform: str) -> dict:
    """What the list shows: everything inside the recent window plus `shown` older rows the operator asked
    for. `more` = there is something to load (held here or still at the connector)."""
    idx = (db.get("chat_index") or {}).get(platform) or {}
    rows = _rows(db, platform)
    cutoff = time.time() - RECENT_H * 3600
    recent = sum(1 for r in rows if float(r.get("ts") or 0) >= cutoff)
    try:
        extra = max(0, int(idx.get("shown") or 0))
    except (TypeError, ValueError):
        extra = 0
    # Never an empty first screen for an account that has chats: a quiet week still shows the latest MIN_SHOWN.
    visible = rows[:max(recent, MIN_SHOWN) + extra]
    return {"rows": visible, "recent_h": RECENT_H, "total": len(rows),
            "more": len(rows) > len(visible) or not idx.get("complete"),
            "complete": bool(idx.get("complete")), "loading": _loading(idx),
            "asked": bool(idx.get("answered_at") or idx.get("asked_at")), "error": idx.get("error") or ""}


def more(db: dict, platform: str) -> dict:
    """«Cargar más»: PAGE more rows on screen, and the next page from the connector when the index runs short."""
    idx = _index(db, platform)
    try:
        idx["shown"] = max(0, int(idx.get("shown") or 0)) + PAGE
    except (TypeError, ValueError):
        idx["shown"] = PAGE
    v = view(db, platform)
    asked = False
    if v["total"] - len(v["rows"]) < PAGE:
        asked = ask(db, platform, older=True)
    return {"shown": len(v["rows"]), "asked": asked, "complete": v["complete"]}


def row(db: dict, platform: str, chat_id) -> dict | None:
    """The index row of one chat, or None."""
    r = (((db.get("chat_index") or {}).get(platform) or {}).get("rows") or {}).get(str(chat_id))
    return dict(r) if isinstance(r, dict) else None
