"""nucleo/pulse/notice_claim.py — a notice CLAIMED for the conversation manager's voice (V2-941, v3.1 §1.7, B6).

While a session of the manager holds the voice, `notices.notify` paints the line and claims it here — no push, no
`shown` — so the retry and the drain to the next screen, which read `owed`, never touch it: one consumer at a time.
The manager says it and the row is `spoken`; or it does not, and the row goes back to `owed`, for its other ways. A
claim past its deadline goes back by itself on the retry pulse. Every move compares the state. `notices` stays the
one writer's module; this one moves only what is claimed.
"""
from __future__ import annotations

import sys
import time


def _n():
    from nucleo.pulse import notices
    return notices


CLAIM_S = 120       # a line claimed for the conversation's voice and not said by then goes back to `owed`


def held_for_the_manager() -> bool:
    """Is a session of the conversation manager holding the voice? Read only if its host is loaded: switched off, the
    host is never imported and this is today's path, byte for byte."""
    import sys
    owed = sys.modules.get("nucleo.conversation_host.owed")
    return bool(owed is not None and owed.voice_live())


def claim_for_voice(row: dict) -> dict:
    """The manager says it, by voice, when it is free and nobody speaks, and its mouth writes the line on the wall —
    `notify` paints nothing, so the line is one. The row is CLAIMED — no push, no `shown` — so the retry and the drain
    to the next screen, which read `owed`, never touch it. One consumer at a time; a claim past its deadline goes back
    to `owed` (`release_expired`), and then the retry shows it."""
    N = _n()
    N._set(row["id"], state="claimed", channel="", next_try_at=N._now() + CLAIM_S)
    N._observe(row, "claimed", "voice")
    return {"id": row["id"], "state": "claimed", "channel": "voice", "duplicate": False}


def spoken(key: str) -> bool:
    """The manager said a claimed line: `spoken`. Only from `claimed`."""
    N = _n()
    row = N.by_key(key)
    if row is None or not N._store.move(row["id"], "claimed", "spoken", channel="voice", delivered_at=N._now()):
        return False
    N._observe(row, "spoken", "voice")
    return True


def release(key: str) -> bool:
    """A claimed line that did not sound goes back to `owed`, for its other ways (retry, push, the next screen)."""
    N = _n()
    row = N.by_key(key)
    if row is None or not N._store.move(row["id"], "claimed", "owed", next_try_at=N._now()):
        return False
    N._observe(row, "owed", "released")
    return True


def release_expired(now: float | None = None) -> int:
    """Every claim past its deadline goes back to `owed`: no row stays claimed for ever. Only the manager's host
    claims, so with it not loaded there is nothing to look for — not even a query on the retry's tick."""
    if "nucleo.conversation_host.owed" not in sys.modules:
        return 0
    N, n = _n(), 0
    try:
        rows = N._store.claims_expired(int(time.time() if now is None else now))
    except Exception as e:  # noqa: BLE001 — the retry goes on; the claims wait for its next turn
        N.logger.warning(f"notices: expired claims unreadable: {e!r}")
        return 0
    for r in rows:
        if N._store.move(r["id"], "claimed", "owed", next_try_at=N._now()):
            N._observe(N._row(r), "owed", "claim_expired")
            n += 1
    return n
