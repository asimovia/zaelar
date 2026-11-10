"""nucleo/circuit/waits.py — a task that WAITS, durably, and the pulse's reads of the waits that are due (V2-851 §3).

A row waits for his answer (`user_answer`, until `answer_wait_s` closes it), for its worker after a process died
(`worker`, resumed by id after a pause), or for anything else its writer names. The row says what for, since when
and until when, so a restart rehydrates the wait instead of burying it, and every change of what a row waits for
re-marks the wake report (the next wake instant may move). Re-exported by `nucleo/circuit/ledger.py`, the one door
callers use to the task rows.
"""
from __future__ import annotations

import time

from loguru import logger

from memory import tasks_store as _ts
from nucleo.circuit import progress as _progress


def _settle(**kw) -> None:
    """A wait that ends is written by `circuit.settle`, the one writer of `done|failed|cancelled` (V2-851 §3b)."""
    from nucleo import circuit
    circuit.settle(**kw)


#: What a task can wait for (V2-851 §3): `user_answer` (his answer), `worker`, `send_echo`, `time` or `event:<topic>`.
#: The engine is the only writer of this field, so it is named by its writers, not filtered through a list here.
USER_ANSWER = "user_answer"
#: The states a row ENDS in — the store's own, read through the ledger (the memory boundary), never a second copy.
ENDINGS = _ts.DONE_STATES


def waiting(task_id: str, waiting_for: str, ask_id: str = "", ask: str = "", *, now: float | None = None,
            quiet: bool = False) -> bool:
    """The task WAITS, and the row says so durably (V2-851 §3): `state=waiting`, what for, since when, until when, and
    the question with its id when it waits for his answer — what a restart rehydrates instead of burying. The ask path
    calls this; the pulse's beat re-writes it for a worker parked on a question. While it waits for the same thing its
    clock is kept (a beat never restarts it); an ended row is never re-opened. True when the row waits now."""
    uid, wf = str(task_id or "").strip(), str(waiting_for or "").strip()
    if not uid or not wf:
        return False
    row = _ts.task_get(uid)
    if row is None or str(row.get("state") or "") in _ts.DONE_STATES:
        return False
    now = time.time() if now is None else now
    same = (row.get("state") == "waiting" and row.get("waiting_for") == wf
            and (not ask_id or str(row.get("ask_id") or "") == ask_id))
    since = int(row.get("waiting_since") or 0) if same and row.get("waiting_since") else int(now)
    _ts.task_patch(uid, state="waiting", waiting_for=wf, waiting_since=since,
                   **({"deadline": since + int(answer_wait_s(now))} if wf == USER_ANSWER else {}),
                   **({"ask_id": ask_id} if ask_id else {}), **({"ask": ask[:600]} if ask else {}))
    if not quiet:                        # `quiet`: a caller that says the whole move itself (`worker_died`)
        _progress.changed(uid, "waiting", row)
    if not same:
        _wake_changed()                  # what it waits for, and until when, may move the next wake instant
    return True


def resumed(task_id: str) -> None:
    """The wait is over and the task works again: `running`, nothing to wait for. The question and its id stay on the
    row as the record of what was last asked."""
    uid = str(task_id or "").strip()
    row = _ts.task_get(uid) if uid else None
    if row and row.get("state") == "waiting" and row.get("waiting_for"):
        _ts.task_patch(uid, state="running", waiting_for="", waiting_since=None, deadline=None)
        _progress.changed(uid, "resumed", row)
        _wake_changed()


def _wake_changed() -> None:
    try:
        from nucleo.pulse import wake
        wake.note_changed()
    except Exception as e:  # noqa: BLE001 — the row is written; only the wake report may lag its recheck
        logger.debug(f"ledger: wake note failed: {e!r}")


#: What a task waits for when its worker process DIED before finishing: the pulse resumes it by id (V2-851 §3).
WORKER = "worker"
#: How long a died worker's row waits before the pulse resumes it — a pause, so a process that dies at birth is not
#: relaunched in a tight loop; and how many deaths a row survives (`attempts`): the next one fails it, with its reason.
WORKER_RESUME_AFTER_S, WORKER_DEATHS_RESUMED = 60.0, 1


def worker_died(rec, *, now: float | None = None) -> bool:
    """A worker process that ended WITHOUT finishing (no result) and has a resumable session id is not failed: its row
    WAITS for the worker (`waiting_for=worker`), keeping its phase and progress, with `deadline` = when the pulse
    resumes it. Bounded by `attempts`: past `WORKER_DEATHS_RESUMED` it returns False and the ending fails it.
    True when the row now waits."""
    uid = str(getattr(rec, "uid", "") or "")
    row = _ts.task_get(uid) if uid else None
    if not row or not str(row.get("session_id") or getattr(rec, "native_sid", "") or ""):
        return False
    if int(row.get("attempts") or 0) >= WORKER_DEATHS_RESUMED or str(row.get("state") or "") in _ts.DONE_STATES:
        return False
    now = time.time() if now is None else now
    _ts.task_patch(uid, phase=str(getattr(rec, "phase", "") or row.get("phase") or "")[:160],
                   attempts=int(row.get("attempts") or 0) + 1)
    if ok := waiting(uid, WORKER, now=now, quiet=True):
        _ts.task_patch(uid, deadline=int(now + WORKER_RESUME_AFTER_S))
    _progress.changed(uid, "worker_died", row)
    return ok


def worker_resumes_due(now: float | None = None) -> list[dict]:
    """The rows whose died worker is due to be resumed now — each moved back to `running` here, ONCE."""
    now = time.time() if now is None else now
    out = []
    for row in _ts.tasks_where(states=("waiting",), modes=("now",), visible_only=False, limit=100):
        if row.get("waiting_for") == WORKER and now >= int(row.get("deadline") or 0):
            resumed(row["id"])
            out.append(row)
    return out


#: How long a task waits for his answer before the pulse closes it — a RULE (scope `global`, key below) with
#: readers, not a constant: genesis `tasks` gives the default, a row of his own at the same key wins (V2-851 §11.1).
ANSWER_WAIT_KEY, ANSWER_WAIT_DAYS = "answer_wait_days", 7.0


def answer_wait_s(now: float | None = None) -> float:
    try:
        import rules
        days = float(rules.value([(0, rules.GLOBAL)], ANSWER_WAIT_KEY, ANSWER_WAIT_DAYS, now=now))
    except Exception as e:  # noqa: BLE001 — an unreadable rule never ends a wait early: the default stands
        logger.debug(f"ledger: {ANSWER_WAIT_KEY} unreadable ({e}) — {ANSWER_WAIT_DAYS} days")
        days = ANSWER_WAIT_DAYS
    return max(0.0, days) * 86400.0


def expired_waits(now: float | None = None) -> list[dict]:
    """Close every task that waited for his answer past `waiting_since + answer_wait_s()` — `cancelled`, through
    `settle` — and return the rows it closed, so the pulse says each ONE line (V2-851 §11.1: «7 days, then cancel»,
    never silently). The period is read NOW: a rule he changes applies to the waits already open."""
    now = time.time() if now is None else now
    period, out = answer_wait_s(now), []
    for row in _ts.tasks_where(states=("waiting",), modes=("now",), visible_only=False, limit=500):
        since = int(row.get("waiting_since") or 0)
        if row.get("waiting_for") != USER_ANSWER or not since or now < since + period:
            continue
        _settle(row=row["id"], state="cancelled", now=now,
                outcome=f"closed: no answer in {period / 86400:g} days" + (f" to «{row['ask'][:160]}»" if row.get("ask") else ""))
        out.append({**row, "days": round(period / 86400.0, 1)})
    return out
