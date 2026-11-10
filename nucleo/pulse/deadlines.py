"""nucleo/pulse/deadlines.py — the instants the pulse acts on by itself, besides the scheduler's jobs.

The scheduler's jobs were the only clock a sleeping engine reported (`wake.py`). Three other clocks run on the same
pulse and must fire while nobody is there, each owned elsewhere and only READ here:

  · an errand with a third party runs out of time at `expires_at` (`nucleo/errands`): the pulse closes it and tells him;
  · a task row that WAITS carries `deadline` — his unanswered question closes after the declared wait and is said once,
    a died worker is resumed by id after its pause (`nucleo/circuit/ledger`);
  · an owed notice is pushed again at `next_try_at` (`nucleo/pulse/notices`) — only when a device can take the push:
    with none, a retry only owes it again, and the next screen that opens drains it.

What runs only while awake and owes nobody anything is NOT here: light and deep sleep of the memory, the chat digest,
sparks. A sleeping engine has nothing new to consolidate, and the next start runs them when due.

Only instants AHEAD of `now` are reported: one already past is the awake pulse's to process now, and reporting it
would ask the deployment to wake an engine immediately, again and again, for something it already handles.
Each reading is fail-soft and independent: an unreadable source contributes nothing.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("zaelar.deadlines")


def _errand(now: float) -> float | None:
    from nucleo import errands
    return errands.next_expiry(now)


def _waiting_row(now: float) -> float | None:
    from nucleo.circuit import ledger
    ahead = [float(r.get("deadline") or 0) for r in
             ledger.store().tasks_where(states=("waiting",), visible_only=False, limit=500)]
    ahead = [t for t in ahead if t > now]
    return min(ahead) if ahead else None


def _owed_notice(now: float) -> float | None:
    from nucleo.pulse import notices
    if not notices.devices():
        return None
    from memory.api import notices as store
    t = store.owed_next_try(int(now))
    return float(t) if t else None


READERS = (("errand", _errand), ("waiting", _waiting_row), ("owed", _owed_notice))


def upcoming(now: float) -> dict[str, float]:
    """`{source: its earliest instant ahead of now}` for every source that has one."""
    out: dict[str, float] = {}
    for name, read in READERS:
        try:
            t = read(now)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"deadlines: {name} unreadable: {e!r}")
            continue
        if t is not None and t > now:
            out[name] = float(t)
    return out
