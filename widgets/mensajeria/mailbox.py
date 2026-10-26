#
# mailbox.py — the EMAIL section as a mail client: the account's folders, one folder's messages newest first, one
# message open, one draft open. The home answers «what is addressed to me»; this answers «what is in my Inbox /
# Sent / Drafts», like Gmail does. Rows come from the connector (`msg.mailbox` → `connector.mailbox`), one page at a
# time; everything here is server state, so a tap and a voice order («enséñame los enviados», «abre el borrador»)
# land on the same screen.
#
# Screens, one at a time: the LIST of `folder` (and, for an Inbox the provider sorts, of one `category` of it —
# Primary, Promotions… as the connector reports them, V2-807 T-01); an OPEN message (`open`); an open DRAFT
# (`draft`, a key of the card's own drafts). Leaving a screen goes back one level — draft/message → its list —
# never to the home. A list is keyed `folder` or `folder#category`.
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
        _log.debug(f"mailbox: unreadable ask time {ts!r} — counted as not in flight")
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


def list_key(folder: str, category: str | None = None) -> str:
    return f"{folder}#{category}" if category else str(folder)


def categories(db: dict, *, include_hidden: bool = False) -> list[dict]:
    """The Inbox's categories as the PROVIDER reported them (`[{key, unread}]`) — never a list of our own — minus
    the ones he asked not to see (a rule, `mail_rules.py`). A server that sorts nothing reports none, and the Inbox
    is one entry."""
    cats = [c for c in _idx(db).get("categories") or [] if isinstance(c, dict) and c.get("key")]
    if include_hidden:
        return cats
    from . import mail_rules
    off = mail_rules.hidden()
    return [c for c in cats if str(c["key"]) not in off]


def default_category(db: dict) -> str | None:
    """The category the Inbox opens on: the provider's first (Gmail's Primary), as Gmail itself does."""
    cats = categories(db)
    return str(cats[0]["key"]) if cats else None


def _routes(db: dict) -> list[dict]:
    """His criteria over the provider's categories (rows of the rules table, `mail_rules.py`), applied by the
    connector to each category's query."""
    from . import mail_rules
    return mail_rules.routes()


def rules_changed(db: dict) -> None:
    """A criterion changed: every category page is stale (its query changed), so each is asked again on entry, and
    the one on screen at once. A category he hid is left for the provider's first visible one."""
    idx = _idx(db)
    for key, lst in (idx.get("lists") or {}).items():
        if str(key).startswith("INBOX#"):
            lst["answered_at"] = lst["asked_at"] = None       # an ask in flight carries the old query
    if str(idx.get("folder") or "").upper() != "INBOX" or idx.get("draft") or idx.get("open"):
        return
    cat = idx.get("category")
    if cat not in {str(c["key"]) for c in categories(db)}:
        go(db, "INBOX")
    else:
        ask(db, "INBOX", category=cat, force=True)


def ask(db: dict, folder: str, *, category: str | None = None, older: bool = False, force: bool = False) -> bool:
    """Queue one page of `folder` (of one `category` of it) for the connector. Returns whether anything was queued."""
    if folder == DRAFTS:
        return False
    lst = _idx(db).setdefault("lists", {}).setdefault(list_key(folder, category), {})
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
    order = {"platform": "email", "folder": folder, "before": before, "limit": PAGE}
    if category:
        order.update(category=category, routes=_routes(db))
        lst["routes"] = order["routes"]
    db.setdefault("pending_mail", []).append(order)
    lst["asked_at"] = time.time()
    return True


def go(db: dict, folder: str, category: str | None = None) -> str:
    """Show `folder`'s list — for the Inbox, one of its categories — closing any message or draft on screen, and
    make sure its first page is coming. A category can be named alone («promotions»): it is an entry of the Inbox.
    The Inbox with no category named opens on the provider's first one, as Gmail does."""
    idx = _idx(db)
    keys = {str(c["key"]).lower() for c in categories(db)}
    ref = str(folder or "").strip().lower()
    if not category and ref in {str(c["key"]).lower() for c in categories(db, include_hidden=True)}:
        folder, category = "INBOX", ref          # an entry of the Inbox — even one he hid: the Inbox, then
    name = folder_name(db, folder)
    cat = str(category or "").strip().lower() or None
    if name.upper() != "INBOX" or cat not in keys:
        cat = None                     # a category the provider never returned is not invented
    if name.upper() == "INBOX" and not cat:
        cat = default_category(db)
    idx.update({"folder": name, "category": cat, "open": None, "draft": None})
    # When he last LOOKED at this list: the connector keeps a list he looked at recently in step with the server
    # (what he archives elsewhere leaves it, what arrives joins it) and leaves the rest alone.
    idx.setdefault("lists", {}).setdefault(list_key(name, cat), {})["viewed_at"] = time.time()
    ask(db, name, category=cat)
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
    """Put one of the card's drafts on screen as the WHOLE card — its only content, never painted over a list
    (V2-807 T-02). It is STATE, so it survives the card mounting after the order, closed or not. «Back» returns to
    the list it was opened from (`back_to`), or to Drafts when it was opened from there."""
    idx = _idx(db)
    if not idx.get("draft"):
        idx["back_to"] = {"folder": str(idx.get("folder") or "INBOX"), "category": idx.get("category") or None}
    idx.update({"folder": folder_name(db, "drafts"), "category": None, "open": None, "draft": key})


NOTE_S = 20              # how long the outcome of a save/send stays on the draft screen


def note(db: dict, key: str, text: str = "") -> None:
    """The outcome of the draft screen's last order (`saved`, `sent`, `not_saved`, `not_sent` + the reason): the screen
    reads it from the state because a tap here is queued and answered with nothing."""
    _idx(db)["note"] = {"key": key, "text": str(text or "")[:300], "at": time.time()}


def back(db: dict) -> None:
    """One level up: a message goes back to its folder's list; a draft to the list it was opened from."""
    idx = _idx(db)
    to = idx.pop("back_to", None) if idx.get("draft") else None
    idx.update({"open": None, "draft": None})
    if isinstance(to, dict) and to.get("folder"):
        idx.update({"folder": str(to["folder"]), "category": to.get("category") or None})


def section(db: dict) -> str:
    """Enter the mail section without naming a list («enséñame el correo»): where he was. An open DRAFT stays on
    screen — it is his work in progress and has no other face (V2-807 T-02); an open message goes back to its list,
    as entering the section always did."""
    idx = _idx(db)
    if idx.get("draft") and idx["draft"] in (db.get("drafts") or {}):
        return str(idx.get("folder") or "INBOX")
    return go(db, str(idx.get("folder") or "INBOX"), idx.get("category"))


def drop_gone(db: dict, folder: str, uids) -> int:
    """Messages the server says are no longer in `folder` (archived, deleted or moved in his own client) leave the
    card: from every page of that folder and, for the Inbox, from the home's pending items. Returns how many rows
    left. The card mirrors the server's MEMBERSHIP, not only its flags (V2-807 T-04)."""
    gone = {str(u) for u in uids or []}
    if not gone:
        return 0
    n = 0
    for key, lst in (_idx(db).get("lists") or {}).items():
        if str(key).split("#", 1)[0] != folder:
            continue
        keep = [r for r in lst.get("rows") or [] if str(r.get("uid")) not in gone]
        n += len(lst.get("rows") or []) - len(keep)
        lst["rows"] = keep
    if folder.upper() == "INBOX":
        items = db.get("items") or []
        keep = [it for it in items if not (it.get("platform") == "email" and str(it.get("messageId")) in gone)]
        n += len(items) - len(keep)
        for i, it in enumerate(keep, 1):
            it["n"] = i
        db["items"] = keep
    return n


def fold(db: dict, ev: dict) -> None:
    """Fold a connector answer into the index: a folder page, one message read whole, or what left a folder."""
    idx = _idx(db)
    folder = str(ev.get("folder") or "INBOX")
    if ev.get("gone") is not None:
        drop_gone(db, folder, ev["gone"])
        return
    if ev.get("open") is not None:
        msg = dict(ev["open"] or {})
        cur = idx.get("open") or {}
        if cur.get("uid") == str(msg.get("uid")) and cur.get("folder") == folder:
            idx["open"] = {**cur, "msg": msg, "asked_at": None}
        return
    if ev.get("folders"):
        idx["folders"] = list(ev["folders"])
    if isinstance(ev.get("counts"), dict):
        idx["counts"] = dict(ev["counts"])
    if folder.upper() == "INBOX" and isinstance(ev.get("categories"), list):
        idx["categories"] = [dict(c) for c in ev["categories"] if isinstance(c, dict) and c.get("key")]
    cat = ev.get("category") or None
    lst = idx.setdefault("lists", {}).setdefault(list_key(folder, cat), {})
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
    lst.update({"answered_at": time.time(), "asked_at": None, "error": str(ev.get("error") or ""),
                "exists": ev.get("exists")})
    # The Inbox was asked before its categories were known (the very first open): now that the provider has said
    # how it sorts it, the screen moves to the first category — the one Gmail opens on.
    if (not cat and folder.upper() == "INBOX" and str(idx.get("folder") or "").upper() == "INBOX"
            and not idx.get("category") and default_category(db)):
        idx["category"] = default_category(db)
        idx.setdefault("lists", {}).setdefault(list_key("INBOX", idx["category"]), {})["viewed_at"] = time.time()
        ask(db, "INBOX", category=idx["category"])


def view(db: dict) -> dict:
    """What the email section shows. `rows` carry `pending` when the same mail is waiting in the home's list."""
    idx = _idx(db)
    folder = str(idx.get("folder") or "INBOX")
    cat = (idx.get("category") or None) if folder.upper() == "INBOX" else None
    lst = (idx.get("lists") or {}).get(list_key(folder, cat)) or {}
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
            "category": cat, "categories": categories(db), "counts": dict(idx.get("counts") or {}),
            "rules": _listing(),
            "unread": unread(db, folder, cat),
            "rows": rows, "loading": _fresh(lst.get("asked_at")), "asked": bool(lst.get("answered_at")
                                                                                or lst.get("asked_at")),
            "more": not lst.get("complete") and bool(lst.get("cursor")), "error": lst.get("error") or "",
            "open": opened, "draft": draft, "back_to": idx.get("back_to") if draft else None,
            "note": n if (n := idx.get("note")) and _fresh_note(n) else None}


def _listing() -> list[dict]:
    from . import mail_rules
    return mail_rules.listing()


def unread(db: dict, folder: str, category: str | None = None) -> int | None:
    """The provider's own unread figure for a list: a category's, or a folder's. An Inbox the provider sorts counts
    its first category (Gmail's Inbox badge is Primary's, not every category's). None = not measured."""
    idx = _idx(db)
    if str(folder).upper() == "INBOX":
        cats = {str(c["key"]): c.get("unread") for c in categories(db)}
        key = category or default_category(db)
        if key in cats:
            return cats[key]
    n = (idx.get("counts") or {}).get(folder)
    return int(n) if isinstance(n, int) else None


def _fresh_note(n) -> bool:
    try:
        return time.time() - float(n.get("at") or 0) < NOTE_S
    except (TypeError, ValueError, AttributeError):
        _log.debug("mailbox: unreadable note time — the note is not shown")
        return False


def take_pending(db: dict) -> list[dict]:
    pending = list(db.get("pending_mail") or [])
    if pending:
        db["pending_mail"] = []
    return pending
