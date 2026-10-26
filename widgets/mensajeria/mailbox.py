#
# mailbox.py — the EMAIL section as a mail client: the account's folders, one folder's messages newest first, one
# message open, one draft open. The home answers «what is addressed to me»; this answers «what is in my Inbox /
# Sent / Drafts», like Gmail does. Rows come from the connector (`msg.mailbox` → `connector.mailbox`), one page at a
# time; everything here is server state, so a tap and a voice order («enséñame los enviados», «abre el borrador»)
# land on the same screen.
#
# Screens, one at a time: the LIST of `folder`; an OPEN message (`open`); an open DRAFT (`draft`, a key of the
# card's own drafts). Leaving a screen goes back one level — draft/message → its folder — never to the home.
#
# Same widget-package contract as data.py: stdlib plus the `widgets` package, never `connectors`.
#
import logging
import time

_log = logging.getLogger("zaelar.mensajeria.mailbox")

PAGE = 30
REFRESH_S = 60           # entering a folder again re-asks its first page at most this often
ASK_TIMEOUT_S = 45       # an unanswered ask stops counting as «loading» after this
DRAFTS = "@drafts"       # the drafts screen when the server names no Drafts folder: only the card's own drafts


def _idx(db: dict) -> dict:
    return db.setdefault("mailbox", {})


def _fresh(ts) -> bool:
    try:
        return bool(ts) and time.time() - float(ts) < ASK_TIMEOUT_S
    except (TypeError, ValueError):
        return False


def folder_name(db: dict, ref: str) -> str:
    """A folder named the way he says it — a role («sent», «drafts») or the server's own label — to its SELECT name.
    Unknown roles fall back to the name itself; «inbox» is always INBOX, even before the list has arrived."""
    ref = str(ref or "").strip()
    low = ref.lower()
    if low in ("", "inbox"):
        return "INBOX"
    for f in _idx(db).get("folders") or []:
        if low in (str(f.get("role") or "").lower(), str(f.get("label") or "").lower(), str(f.get("name")).lower()):
            return str(f["name"])
    # The card's own drafts exist before (and without) the server's Drafts folder: «borradores» always has a home.
    return DRAFTS if low in ("drafts", DRAFTS) else ref


def role_of(db: dict, name: str) -> str:
    if str(name).upper() == "INBOX":
        return "inbox"
    if name == DRAFTS:
        return "drafts"
    return next((str(f.get("role") or "") for f in _idx(db).get("folders") or [] if f.get("name") == name), "")


def ask(db: dict, folder: str, *, older: bool = False, force: bool = False) -> bool:
    """Queue one page of `folder` for the connector. Returns whether anything was queued."""
    if folder == DRAFTS:
        return False
    lst = _idx(db).setdefault("lists", {}).setdefault(folder, {})
    if _fresh(lst.get("asked_at")):
        return False
    if older:
        if lst.get("complete") or not lst.get("cursor"):
            return False
        before = lst["cursor"]
    else:
        try:
            if not force and lst.get("answered_at") and time.time() - float(lst["answered_at"]) < REFRESH_S:
                return False
        except (TypeError, ValueError):
            _log.warning("mailbox: unreadable answer time, refreshing")
        before = None
    db.setdefault("pending_mail", []).append({"platform": "email", "folder": folder, "before": before,
                                              "limit": PAGE})
    lst["asked_at"] = time.time()
    return True


def go(db: dict, folder: str) -> str:
    """Show `folder`'s list (closing any message or draft on screen) and make sure its first page is coming."""
    idx = _idx(db)
    name = folder_name(db, folder)
    idx.update({"folder": name, "open": None, "draft": None})
    ask(db, name)
    return name


def open_message(db: dict, uid: str, folder: str | None = None) -> None:
    """Open one message of a folder. A message the card already holds whole (an Inbox mail that is also a triage
    item) is shown from there; anything else is asked of the mailbox."""
    idx = _idx(db)
    name = folder_name(db, folder) if folder else str(idx.get("folder") or "INBOX")
    idx.update({"folder": name, "draft": None, "open": {"folder": name, "uid": str(uid), "asked_at": time.time()}})
    if name.upper() == "INBOX" and any(str(it.get("messageId")) == str(uid) and it.get("platform") == "email"
                                       for it in db.get("items") or []):
        return
    db.setdefault("pending_mail", []).append({"platform": "email", "folder": name, "open": str(uid)})


def open_draft(db: dict, key: str) -> None:
    """Put one of the card's drafts on screen, the whole card, inside the Drafts section."""
    _idx(db).update({"folder": folder_name(db, "drafts"), "open": None, "draft": key})


NOTE_S = 20              # how long the outcome of a save/send stays on the draft screen


def note(db: dict, key: str, text: str = "") -> None:
    """The outcome of the draft screen's last order (`saved`, `sent`, `not_saved`, `not_sent` + the reason): the screen
    reads it from the state because a tap here is queued and answered with nothing."""
    _idx(db)["note"] = {"key": key, "text": str(text or "")[:300], "at": time.time()}


def back(db: dict) -> None:
    """One level up: a message or a draft goes back to its folder's list."""
    _idx(db).update({"open": None, "draft": None})


def fold(db: dict, ev: dict) -> None:
    """Fold a connector answer into the index: a folder page, or one message read whole."""
    idx = _idx(db)
    folder = str(ev.get("folder") or "INBOX")
    if ev.get("open") is not None:
        msg = dict(ev["open"] or {})
        cur = idx.get("open") or {}
        if cur.get("uid") == str(msg.get("uid")) and cur.get("folder") == folder:
            idx["open"] = {**cur, "msg": msg, "asked_at": None}
        return
    if ev.get("folders"):
        idx["folders"] = list(ev["folders"])
    lst = idx.setdefault("lists", {}).setdefault(folder, {})
    rows = [dict(r) for r in ev.get("rows") or [] if isinstance(r, dict) and r.get("uid")]
    if ev.get("before") is None:
        # A refresh of the first page keeps the older pages he already walked back through, and their cursor.
        tail = [r for r in lst.get("rows") or [] if rows and int(r["uid"]) < int(rows[-1]["uid"])]
        lst["rows"] = rows + tail
        if not tail:
            lst["cursor"], lst["complete"] = ev.get("nextBefore"), bool(ev.get("complete"))
    else:
        have = {r["uid"] for r in lst.get("rows") or []}
        lst["rows"] = (lst.get("rows") or []) + [r for r in rows if r["uid"] not in have]
        lst["cursor"], lst["complete"] = ev.get("nextBefore"), bool(ev.get("complete"))
    lst.update({"answered_at": time.time(), "asked_at": None, "error": str(ev.get("error") or "")})


def view(db: dict) -> dict:
    """What the email section shows. `rows` carry `pending` when the same mail is waiting in the home's list."""
    idx = _idx(db)
    folder = str(idx.get("folder") or "INBOX")
    lst = (idx.get("lists") or {}).get(folder) or {}
    waiting = {str(it.get("messageId")) for it in db.get("items") or [] if it.get("platform") == "email"}
    rows = [dict(r) for r in lst.get("rows") or []]
    if folder.upper() == "INBOX":
        for r in rows:
            r["pending"] = r["uid"] in waiting
    opened = idx.get("open")
    if opened:
        opened = {**opened, "loading": _fresh(opened.get("asked_at")) and not opened.get("msg")}
    draft = idx.get("draft")
    if draft and draft not in (db.get("drafts") or {}):
        draft = None                       # sent or discarded meanwhile: the screen goes back to its folder
    return {"folders": list(idx.get("folders") or []), "folder": folder, "role": role_of(db, folder),
            "rows": rows, "loading": _fresh(lst.get("asked_at")), "asked": bool(lst.get("answered_at")
                                                                                or lst.get("asked_at")),
            "more": not lst.get("complete") and bool(lst.get("cursor")), "error": lst.get("error") or "",
            "open": opened, "draft": draft,
            "note": n if (n := idx.get("note")) and _fresh_note(n) else None}


def _fresh_note(n) -> bool:
    try:
        return time.time() - float(n.get("at") or 0) < NOTE_S
    except (TypeError, ValueError, AttributeError):
        return False


def take_pending(db: dict) -> list[dict]:
    pending = list(db.get("pending_mail") or [])
    if pending:
        db["pending_mail"] = []
    return pending
