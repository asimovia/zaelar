"""connectors/email/membership.py — which of the messages the card shows are STILL in their folder (V2-807 T-04).

The card mirrors the server's membership, not only its flags. A mail archived, deleted or moved in the operator's own
client leaves the folder it came from; `flags_for` simply has no answer for its UID, and an absent answer used to
change nothing — the row stayed on the card as if it were still waiting. Here the question is asked the other way:
of these UIDs, which does the folder still hold? What it no longer holds has left.

One login answers both questions for a folder: `UID SEARCH UID <set>` (membership) and `UID FETCH <set> (FLAGS)`
(read / answered). A failure answers `None`, never an empty set — «I could not ask» must not read as «they are all
gone», which would empty the card on the first network hiccup.

Cost, chosen on purpose (the initiative's open question on IMAP IDLE): no connection is held open. The check rides
the connector's poll tick (`config.poll_interval()`, 20 s by default), costs one login and two commands per folder,
and is asked only for what is on screen — the pending Inbox items and the first page of a folder he looked at
recently. A mail he archives in Gmail leaves the card within one tick.
"""
from __future__ import annotations

import logging
import re

_log = logging.getLogger("zaelar.email.membership")

_FLAG_RE = re.compile(rb"UID (\d+) FLAGS \(([^)]*)\)", re.I)
MAX_UIDS = 200


def _quote(folder: str) -> str:
    return f'"{folder}"' if (" " in folder or not folder) and not folder.startswith('"') else folder


def check(mb, folder: str, uids) -> dict | None:
    """`{"present": {uid}, "flags": {uid: {"\\Seen", …}}, "exists": n}` for the UIDs asked, or None when the server
    could not be asked. `exists` is how many messages the folder holds now. Read-only: the folder is selected with `readonly=True`, so asking never marks anything."""
    uids = [str(u) for u in (uids or []) if str(u).isdigit()][:MAX_UIDS]
    if not uids:
        return {"present": set(), "flags": {}, "exists": None}
    try:
        im = mb._imap()
    except Exception as e:  # noqa: BLE001 — no login, no answer: the caller changes nothing
        _log.info(f"email membership: no login ({type(e).__name__})")
        return None
    try:
        st, sel = im.select(_quote(folder), readonly=True)
        if st != "OK":
            return None
        try:
            exists = int((sel or [b"0"])[0] or 0)
        except (TypeError, ValueError):
            exists = None
        st, data = im.uid("SEARCH", "UID", ",".join(uids))
        if st != "OK":
            return None
        found = set()
        for chunk in data or []:
            raw = chunk.decode("ascii", "ignore") if isinstance(chunk, (bytes, bytearray)) else str(chunk or "")
            found.update(t for t in raw.split() if t.isdigit())
        # Only what was asked can be present: a server is free to answer a UID set with more than it was asked.
        present = found & set(uids)
        flags: dict[str, set[str]] = {}
        if present:
            st, data = im.uid("FETCH", ",".join(sorted(present, key=int)), "(FLAGS)")
            for row in (data or []) if st == "OK" else []:
                raw = row[0] if isinstance(row, tuple) else row
                m = _FLAG_RE.search(raw) if isinstance(raw, (bytes, bytearray)) else None
                if m:
                    flags[m.group(1).decode()] = {f.decode(errors="replace") for f in m.group(2).split()}
        return {"present": present, "flags": flags, "exists": exists}
    except Exception as e:  # noqa: BLE001 — a half answer is no answer
        _log.warning(f"email membership: check of {folder!r} failed: {type(e).__name__}")
        return None
    finally:
        try:
            im.logout()
        except Exception:  # noqa: BLE001
            pass


def gone(asked, answer: dict | None) -> list[str]:
    """The asked UIDs the folder no longer holds — empty when there was no answer."""
    if answer is None:
        return []
    have = set(answer.get("present") or ())
    return sorted({str(u) for u in asked or [] if str(u).isdigit()} - have, key=int)
