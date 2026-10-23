"""connectors/email/search.py — find mail in the REAL mailbox, on demand (demo pass 30, 2026-09-28): by sender,
recipient, subject or text, in the INBOX and the mailbox's archive folder. Nothing is ever copied wholesale.

Its own module because `mailbox.py` is over the architecture ratchet's ceiling: a new capability goes where it
can live, not into the file the ratchet is asking to shrink. It uses the mailbox's own connection and parser.
"""
from __future__ import annotations

import logging

from connectors.email.mailbox import parse_message

_log = logging.getLogger("zaelar.email.search")


#: Special-use folders (RFC 6154) that hold mail no longer in the INBOX: Gmail's «All Mail», an «Archive».
_ARCHIVE_FLAGS = ("\\All", "\\Archive")


def _archive_folder(im) -> str | None:
    """The mailbox's «everything» or «archive» folder, if the server names one. Mail the operator archived is
    still his mail; searching only the INBOX said «nothing from them» about every message he had filed away."""
    try:
        st, rows = im.list()
    except Exception as e:  # noqa: BLE001 — a server that will not list is searched in its INBOX only
        _log.warning(f"email search: folder list unavailable: {type(e).__name__}")
        return None
    found = {}
    for row in (rows or []) if st == "OK" else []:
        # `(\HasNoChildren \All) "/" "[Gmail]/All Mail"` — flags in parentheses, the delimiter, the name.
        line = row.decode("utf-8", "replace") if isinstance(row, bytes) else str(row)
        head, sep, rest = line.partition(") ")
        parts = rest.split(" ", 1)
        if not sep or len(parts) < 2:
            continue
        flags, name = head.lstrip("(").split(), parts[1].strip().strip('"')
        for flag in _ARCHIVE_FLAGS:
            if flag in flags:
                found.setdefault(flag, name)
    return next((found[f] for f in _ARCHIVE_FLAGS if f in found), None)


def _criteria(term: str) -> list:
    """Sender, recipient, subject OR the text of the message — a person, a word they wrote, a reference number."""
    t = f'"{term}"'
    return ["OR", "OR", "FROM", t, "TO", t, "OR", "SUBJECT", t, "TEXT", t]


def search_text(mb, terms: list[str], limit: int = 5, media_dir: str | None = None) -> list[dict]:
    """Mail whose sender, recipient, subject or TEXT contains any of `terms`, newest first, parsed, at most
    `limit` — searched in the INBOX and then in the mailbox's archive folder.

    Demo pass 30 (2026-09-28, E1): «did inworld send me something?» — the receipt was the 34th newest unread,
    the card backfills 30, and after a reset the archive held nothing older, so the answer was «nothing from
    Inworld». The mailbox itself answers that question in one SEARCH. This is the ON-DEMAND mode of
    `connectors/messaging/history.py`: the mailbox is never copied, only what a search returns is. Folders are
    selected READ-ONLY and fetched with BODY.PEEK: looking for a mail must never mark it read. A hit outside the
    INBOX is keyed by its Message-ID, never by its UID — UIDs are per folder, and the INBOX's are what mark-seen
    acts on."""
    terms = [str(t).replace('"', "").strip() for t in (terms or []) if str(t).strip()][:4]
    results: list[dict] = []
    if not terms:
        return results
    try:
        im = mb._imap()
    except Exception:
        return results
    seen: set = set()
    try:
        folders = ["INBOX"]
        extra = _archive_folder(im)
        if extra and extra.upper() != "INBOX":
            folders.append(extra)
        for folder in folders:
            if len(results) >= limit:
                break
            st, _ = im.select(f'"{folder}"' if " " in folder else folder, readonly=True)
            if st != "OK":
                continue
            uids: set[int] = set()
            for t in terms:
                st, data = im.uid("search", None, *_criteria(t))
                if st == "OK" and data and data[0]:
                    uids |= {int(u) for u in data[0].split()}
            for uid in sorted(uids, reverse=True):
                if len(results) >= limit:
                    break
                st2, msg_data = im.uid("fetch", str(uid), "(BODY.PEEK[])")
                if st2 != "OK" or not msg_data or not msg_data[0]:
                    continue
                try:
                    parsed = parse_message(str(uid), msg_data[0][1], media_dir=media_dir if folder == "INBOX" else None)
                except Exception:
                    parsed = None
                if parsed is None:
                    continue
                mid = str(parsed.get("msgid") or "").strip()
                if mid and mid in seen:
                    continue                      # the INBOX copy of a message the archive folder also holds
                seen.add(mid)
                if folder != "INBOX":
                    parsed["messageId"] = f"mid:{mid}" if mid else f"{folder}:{uid}"
                    parsed["folder"] = folder
                results.append(parsed)
    except Exception:
        pass
    finally:
        try:
            im.logout()
        except Exception:
            pass
    return results
