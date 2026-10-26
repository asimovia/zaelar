"""connectors/email/folders.py — the mailbox as a mail CLIENT sees it: its folders, one page of a folder's headers,
and one message read whole.

The widget's triage list answers «what wants my attention»; this answers «what is in my Inbox / Sent / Drafts», the
first screen of any mail client. Its own module because `mailbox.py` is over the file ceiling: it uses the
mailbox's connection and the header helpers, and adds nothing to that file.

Every read here is READ-ONLY (folders selected with `readonly=True`, bodies fetched with BODY.PEEK): browsing a
folder must never mark a message read — that stays an explicit order.
"""
from __future__ import annotations

import base64
import email as email_lib
import json
import logging
import re
from pathlib import Path

from connectors.email.headers import (decode_header_value, display_name, extract_email_address,
                                      extract_text_body)

_log = logging.getLogger("zaelar.email.folders")

#: RFC 6154 special-use attributes, in the order a mail client lists them after the Inbox (`special_use.json`, a
#: declared datum). The ROLE is the attribute's own name, DECLARED by the server — Gmail, Outlook, iCloud and Dovecot
#: announce it — so nothing here reads a folder's name: a localised «Enviados» and a «Sent Items» are the same folder
#: because the server says so. A folder with no role is listed by its own name after these.
_SPECIAL = json.loads((Path(__file__).with_name("special_use.json")).read_text(encoding="utf-8"))["order"]


def _mutf7(name: str) -> str:
    """IMAP's modified UTF-7 (RFC 3501 §5.1.3) → text: «Enviados» arrives as itself, «Papelería» as
    `Papeler&AO0-a`."""
    def dec(m):
        chunk = m.group(1)
        if not chunk:
            return "&"
        b = chunk.replace(",", "/")
        b += "=" * (-len(b) % 4)
        try:
            return base64.b64decode(b).decode("utf-16-be")
        except Exception:  # noqa: BLE001 — an undecodable name is shown as the server sent it
            return m.group(0)
    return re.sub(r"&([^-]*)-", dec, name)


def parse_list(pairs) -> list[dict]:
    """The mailbox's LIST, as `Mailbox._folders` parses it (`[(attrs lowercase, name)]`) → [{name, label, role}], in
    client order: Inbox, the special folders, then the rest by name. `name` is what SELECT needs (raw, still
    encoded); `label` is what a person reads. \\Noselect containers are left out — they hold folders, not mail."""
    out, seen = [], set()
    for attrs, name, *sep in pairs or []:
        name = str(name).strip()
        sep = sep[0] if sep else "/"
        if "\\noselect" in attrs or "\\nonexistent" in attrs or name in seen:
            continue
        seen.add(name)
        label = _mutf7(name)
        leaf = (label.split(sep)[-1] if sep else label).strip()
        if name.upper() == "INBOX":
            role = "inbox"
        else:
            role = next((a.lstrip("\\") for a in _SPECIAL if a in attrs.split()), "")
        out.append({"name": name, "label": leaf or label, "role": role})
    # One folder per role: a server listing both «Sent» and «[Gmail]/Sent Mail» keeps the one with the attribute.
    taken, uniq = set(), []
    for f in out:
        if f["role"] and f["role"] in taken:
            f = {**f, "role": ""}
        taken.add(f["role"])
        uniq.append(f)
    rank = {"inbox": 0, **{a.lstrip("\\"): i + 1 for i, a in enumerate(_SPECIAL)}}
    return sorted(uniq, key=lambda f: (rank.get(f["role"], len(rank)), f["label"].lower()))


def _quote(folder: str) -> str:
    return f'"{folder}"' if (" " in folder or not folder) and not folder.startswith('"') else folder


def _addr_list(raw: str) -> list[str]:
    from email.utils import getaddresses
    return [a for _n, a in getaddresses([raw or ""]) if a]


def _header_row(uid: int, flags: str, head: bytes) -> dict:
    msg = email_lib.message_from_bytes(head or b"")
    from_raw = msg.get("From", "")
    from_addr = extract_email_address(from_raw)
    to_raw = decode_header_value(msg.get("To", ""))
    row = {"uid": str(uid), "from": from_addr, "fromName": display_name(from_raw, from_addr),
           "to": ", ".join(_addr_list(to_raw))[:200],
           "subject": decode_header_value(msg.get("Subject", "")) or "",
           "seen": "\\seen" in flags, "answered": "\\answered" in flags, "flagged": "\\flagged" in flags}
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(msg.get("Date", ""))
        if dt is not None:
            row["ts"] = dt.timestamp()
    except Exception as e:  # noqa: BLE001 — a malformed Date leaves the row undated, never drops it
        _log.debug(f"email folders: undated row {uid} ({type(e).__name__})")
    return row


def _fetch_meta(meta: bytes) -> tuple[int | None, str]:
    """`12 (UID 345 FLAGS (\\Seen \\Answered) BODY[…] {123}` → (345, "\\seen \\answered"), in either item order."""
    toks = meta.decode("ascii", "ignore").replace("(", " ( ").replace(")", " ) ").split()
    up = [t.upper() for t in toks]
    uid = int(toks[up.index("UID") + 1]) if "UID" in up and up.index("UID") + 1 < len(toks) \
        and toks[up.index("UID") + 1].isdigit() else None
    flags = ""
    if "FLAGS" in up and up.index("FLAGS") + 1 < len(toks) and toks[up.index("FLAGS") + 1] == "(":
        start = up.index("FLAGS") + 2
        end = toks.index(")", start) if ")" in toks[start:] else start
        flags = " ".join(toks[start:end]).lower()
    return uid, flags


_HEADERS = "(UID FLAGS BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE)])"


def _fetch_rows(im, which, *, by_uid: bool = False) -> list[dict]:
    """Header rows for a sequence range (`"16:45"`) or a list of UIDs, newest first. Headers only, PEEK."""
    if by_uid:
        if not which:
            return []
        st, data = im.uid("FETCH", ",".join(str(u) for u in which), _HEADERS)
    else:
        st, data = im.fetch(which, _HEADERS)
    rows = {}
    for part in data or []:
        if not isinstance(part, tuple) or len(part) < 2:
            continue
        uid, flags = _fetch_meta(part[0] if isinstance(part[0], (bytes, bytearray)) else b"")
        if uid is not None:
            rows[uid] = _header_row(uid, flags, part[1])
    return [rows[u] for u in sorted(rows, reverse=True)]


def list_page(mb, folder: str = "INBOX", before: str | None = None, limit: int = 30, *,
              category: str | None = None, routes=None) -> dict:
    """One page of `folder`'s headers, newest first: `{folders, rows, nextBefore, complete, exists, error}` — and,
    with the first page, `counts` (each folder's unread, as the server counts it) and, for an Inbox the provider
    sorts, `categories` (`[{key, unread}]`, `categories.py`). With `category`, the page is that category's, paged by
    UID with his `routes` applied; a server that sorts nothing ignores `category` and lists the folder.

    Paged by SEQUENCE number, not by searching: SELECT already says how many messages the folder holds, and the
    newest are the last numbers — so a page is one FETCH of `limit` headers whatever the size of the folder (a
    `UID SEARCH ALL` over a 200 000-message Gmail inbox took 23 s just to list the ids). `before` is the lowest
    number already shown. New mail is appended at the end, so the older numbers a cursor points at do not move;
    a message deleted meanwhile can shift a page by one, which the card absorbs by deduplicating on UID."""
    out = {"folders": [], "rows": [], "nextBefore": None, "complete": False, "error": ""}
    try:
        im = mb._imap()
    except Exception as e:  # noqa: BLE001
        out["error"] = f"IMAP: {type(e).__name__}"
        return out
    try:
        from connectors.email import categories as _cats
        from connectors.email.mailbox import Mailbox
        out["folders"] = parse_list(Mailbox._folders(im, delimiter=True))
        if before is None:
            out["counts"] = _cats.unseen_counts(im, out["folders"])
        st, data = im.select(_quote(folder), readonly=True)
        if st != "OK":
            out["error"] = "folder_unavailable"
            return out
        exists = int((data or [b"0"])[0] or 0)
        out["exists"] = exists      # what the folder held when this page was read: a later tick that sees another
                                    # number re-reads the first page (mail arrived, or came back from elsewhere)
        ext = _cats.supported(im) if folder.upper() == "INBOX" else None
        if ext and before is None:
            out["categories"] = _cats.summary(im, ext, routes)
        if ext and category in ext["keys"]:
            out["category"] = category
            uids, out["nextBefore"], out["complete"] = _cats.page_uids(im, ext, category, routes, before, limit)
            out["rows"] = _fetch_rows(im, uids, by_uid=True)
            return out
        try:
            hi = min(exists, int(str(before)) - 1) if before else exists
        except (TypeError, ValueError):
            hi = exists
        lo = max(1, hi - max(1, int(limit)) + 1)
        out["complete"] = lo <= 1
        out["nextBefore"] = None if out["complete"] else str(lo)
        if hi < 1:
            out["complete"] = True
            return out
        out["rows"] = _fetch_rows(im, f"{lo}:{hi}")
    except Exception as e:  # noqa: BLE001 — the card says why the folder is short; it never looks empty
        _log.warning(f"email folders: page of {folder!r} failed: {type(e).__name__}")
        out["error"] = type(e).__name__
    finally:
        try:
            im.logout()
        except Exception as e:  # noqa: BLE001 — the page is already in hand
            _log.debug(f"email folders: logout failed ({type(e).__name__})")
    return out


def read_one(mb, folder: str, uid: str, media_dir: str | None = None) -> dict:
    """One message of `folder`, whole: headers, the text body and (for the Inbox) its attachments. Unlike triage's
    parser this keeps automated senders and the operator's own mail — in a folder, everything is his mail."""
    try:
        im = mb._imap()
    except Exception as e:  # noqa: BLE001
        return {"uid": str(uid), "folder": folder, "error": f"IMAP: {type(e).__name__}"}
    try:
        st, _ = im.select(_quote(folder), readonly=True)
        if st != "OK":
            return {"uid": str(uid), "folder": folder, "error": "folder_unavailable"}
        st, data = im.uid("fetch", str(uid), "(FLAGS BODY.PEEK[])")
        part = next((p for p in (data or []) if isinstance(p, tuple) and len(p) > 1), None)
        if st != "OK" or part is None:
            return {"uid": str(uid), "folder": folder, "error": "not_found"}
        msg = email_lib.message_from_bytes(part[1])
        from_raw = msg.get("From", "")
        from_addr = extract_email_address(from_raw)
        out = {"uid": str(uid), "folder": folder, "from": from_addr, "fromName": display_name(from_raw, from_addr),
               "to": ", ".join(_addr_list(decode_header_value(msg.get("To", "")))),
               "cc": ", ".join(_addr_list(decode_header_value(msg.get("Cc", "")))),
               "subject": decode_header_value(msg.get("Subject", "")) or "",
               "msgid": msg.get("Message-ID", ""),
               "body": (extract_text_body(msg) or "").strip()[:20000]}
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(msg.get("Date", ""))
            if dt is not None:
                out["ts"] = dt.timestamp()
        except Exception as e:  # noqa: BLE001 — a malformed Date leaves the message undated
            _log.debug(f"email folders: undated message {uid} ({type(e).__name__})")
        if media_dir and folder.upper() == "INBOX":
            try:
                from connectors.email.mailbox import extract_attachments
                mtype, paths = extract_attachments(msg, str(uid), media_dir)
                if mtype:
                    out["mediaType"], out["mediaUrls"] = mtype, paths
            except Exception as e:  # noqa: BLE001 — the text still reads without its files
                _log.info(f"email folders: attachments of {uid} unreadable: {type(e).__name__}")
        return out
    except Exception as e:  # noqa: BLE001
        _log.warning(f"email folders: read of {folder!r}/{uid} failed: {type(e).__name__}")
        return {"uid": str(uid), "folder": folder, "error": type(e).__name__}
    finally:
        try:
            im.logout()
        except Exception as e:  # noqa: BLE001 — the page is already in hand
            _log.debug(f"email folders: logout failed ({type(e).__name__})")
