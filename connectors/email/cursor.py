"""connectors/email/cursor.py — where this engine left each mailbox, durable across processes (V2-872 F2).

The connector's memory of what it already handed over (`service._seen`) lives in the process. An engine that sleeps
between uses starts a new process every time, and every start used to re-seed from the server's flags alone: the same
newest unread were handed over again and classified again by a model, on every boot, to be dropped as duplicates only
AFTER the model had been paid. A message the server still calls unread is not a message this engine has not seen.

The cursor is IMAP's own: per account and folder, the folder's `UIDVALIDITY` and the highest `UID` every message at or
under which this engine has dealt with (delivered, or deliberately left in the mailbox by the first seeding). UIDs are
strictly ascending within one `UIDVALIDITY`, so «above the cursor» is exactly «arrived since» — including everything
that arrived while the engine was asleep. A changed `UIDVALIDITY` means the server renumbered the folder: the cursor is
void and the first-connect seeding applies again.

Stored in the engine's own key-value table (the data volume), never in the connector's session folder.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("zaelar.email.cursor")

_PREFIX = "email:cursor:"


def _key(address: str, folder: str) -> str:
    return f"{_PREFIX}{str(address or '').strip().lower()}:{folder}"


def _kv():
    from memory import api as memory
    return memory


def load(address: str, folder: str = "INBOX") -> dict | None:
    """`{"validity": int, "uid": int}` or None when this mailbox was never left anywhere."""
    if not str(address or "").strip():
        return None
    try:
        got = _kv().kv_get(_key(address, folder))
        if isinstance(got, dict) and int(got.get("validity")) and int(got.get("uid", -1)) >= 0:
            return {"validity": int(got["validity"]), "uid": int(got["uid"])}
    except Exception as e:  # noqa: BLE001 — unreadable is «never left»: the first-connect seeding applies
        logger.debug(f"email cursor unreadable: {e!r}")
    return None


def save(address: str, validity: int, uid: int, folder: str = "INBOX") -> dict | None:
    """Move the cursor forward (never back within one `UIDVALIDITY`; a new one replaces it). Returns what is stored."""
    if not str(address or "").strip() or not validity:
        return None
    cur = load(address, folder)
    if cur and cur["validity"] == int(validity) and cur["uid"] >= int(uid):
        return cur
    new = {"validity": int(validity), "uid": int(uid)}
    try:
        _kv().kv_set(_key(address, folder), new)
    except Exception as e:  # noqa: BLE001 — not saved: the next start re-delivers, and the consumers dedupe it
        logger.warning(f"email cursor not saved: {e!r}")
        return cur
    return new


def numeric(uids) -> list[int] | None:
    """The UIDs as integers, ascending — None when any is not one (then no cursor can be trusted over them)."""
    raw = [str(u).strip() for u in uids]
    return sorted(int(u) for u in raw) if all(u.isdigit() for u in raw) else None


def split(cursor: dict | None, validity: int | None, uids) -> tuple[list[str], list[str]] | None:
    """`(dealt with, arrived since)` — the mailbox's UIDs on either side of the cursor, both ascending — or None when
    the cursor does not apply (none stored, the folder renumbered, a UID that is not a number)."""
    if not cursor or not validity or int(validity) != cursor["validity"]:
        return None
    nums = numeric(uids)
    if nums is None:
        return None
    return ([str(u) for u in nums if u <= cursor["uid"]], [str(u) for u in nums if u > cursor["uid"]])
