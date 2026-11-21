"""nucleo/queue — the orchestrator: his real tasks are ONE queue in the task table, and this is its ONE writer (INI-078).

A row of the queue is a row of `tasks` with an `owner` (`worker` · `send` · `processor`): only work of several steps
that one of them runs. What is conversation is never a task, and a row without an owner is not in the queue (a cron's
mirror, an event flow, an inline row). A task of the queue is `pending`, `running` or `waiting`, nothing else: when it
ends it LEAVES — its row is archived, and there is no «finished» state.

Every change is a SIGNAL (`signal(task_id, what, by=…)`) from the pulse, its owner or him. Each one is applied whole
under one lock, in the order they take it, so when two touch the same field the last one wins; a jump `JUMPS` does not
list is refused (`queue/refused`), and so is any signal for a task that already left. Every applied signal is said
once, `queue/<what>`, in the task's own flow. Everyone else READS the row by id.
"""
from __future__ import annotations

import threading
import time

from loguru import logger

#: who runs a task of the queue; each one is a lane
OWNERS = ("worker", "send", "processor")
#: who may send a signal
SENDERS = ("pulse", "owner", "him")
PENDING = "pending"
RUNNING = "running"
WAITING = "waiting"
#: the task leaves the queue (`done`/`failed`/`cancelled`): its row is archived
ARCHIVE = "archive"
#: state → the signals it accepts → the state they lead to; anything else is refused
JUMPS = {
    PENDING: {"start": RUNNING, "priority": PENDING, "move": PENDING, "progress": PENDING, "cancelled": ARCHIVE,
              "wait": WAITING,       # its start gate asks him first (the confirmation): it waits, never started
              "failed": ARCHIVE},    # it could not start (a provider asleep, a gate that refused it)
    RUNNING: {"wait": WAITING, "progress": RUNNING, "back": PENDING,
              "done": ARCHIVE, "failed": ARCHIVE, "cancelled": ARCHIVE},
    WAITING: {"back": PENDING, "progress": WAITING, "cancelled": ARCHIVE},   # a parked worker still beats
}
#: the columns each signal may carry; the rest of what a caller passes is not the signal's to write
FIELDS = {
    "wait": ("ask", "ask_id", "waiting_for", "deadline"),
    "progress": ("phase", "progress", "heartbeat_at", "reported_at", "error_class", "attempts", "session_id", "cwd",
                 "playbook", "sheet", "title", "deadline"),
}
#: …and what a task is born with besides its words: where it shows and whose it is (read by the board and the sheets)
BIRTH = FIELDS["progress"] + ("surface", "visible", "parent_id", "started_at")

#: reentrant: a listener of a `queue/*` event that sends a signal of its own queues behind, never deadlocks
_lock = threading.RLock()


def _store():
    from nucleo.circuit import ledger
    return ledger.store()


def _say(what: str, row: dict, by: str, **extra) -> None:
    """The one event of a signal, in the task's flow. Never raises: an event never decides the queue."""
    try:
        from voice import observer
        trace = str(row.get("trace_id") or "")
        observer.emit("queue", f"queue/{what}", role="system",
                      extra={"what": what, "task_id": str(row.get("id") or ""), "by": by,
                             "owner": str(row.get("owner") or ""), "num": row.get("num"), **extra,
                             **({"trace": trace} if trace else {})})
    except Exception as e:  # noqa: BLE001
        logger.debug(f"queue: queue/{what} not emitted — {type(e).__name__}: {e}")


def _pending(owner: str, but: str = "") -> list[dict]:
    """The lane's pending tasks in their order (priority first, then position), without `but`."""
    return [r for r in _store().queue_rows(owner) if r.get("state") == PENDING and r.get("id") != but]


#: the one rule of «it's urgent» (Q-5): the highest priority, before every pending task of its lane
URGENT = 1


def _head(owner: str, but: str) -> tuple[int, float]:
    """Priority and position that put a task FIRST in its lane — the one rule an urgent task, a raised one and one
    his answer brings back all follow: `URGENT`, and a position under every pending one, so the last put first is."""
    rows = _pending(owner, but)
    return URGENT, (min(float(r.get("position") or 0) for r in rows) - 1.0) if rows else float(time.time())


def _moved(row: dict, before: str) -> tuple[int, float] | None:
    """Priority and position that put `row` before the task `before` (`first`, `last` or an id of its lane); None when
    `before` is not a pending task of its lane. It takes its new neighbour's priority, so it lands where he said."""
    rows = _pending(str(row["owner"]), str(row["id"]))
    ids = [str(r["id"]) for r in rows]
    if before == "first":
        i = 0
    elif before == "last":
        i = len(rows)
    elif before in ids:
        i = ids.index(before)
    else:
        return None
    prev, nxt = (rows[i - 1] if i > 0 else None), (rows[i] if i < len(rows) else None)
    if nxt is None:
        return ((int(prev.get("priority") or 0), float(prev.get("position") or 0) + 1.0) if prev
                else (int(row.get("priority") or 0), float(row.get("position") or 0)))
    p = int(nxt.get("priority") or 0)
    pos = float(nxt.get("position") or 0)
    if prev is not None and int(prev.get("priority") or 0) == p:
        return p, (float(prev.get("position") or 0) + pos) / 2.0
    return p, pos - 1.0


def add(owner: str, title: str, *, goal: str = "", kind: str = "", origin: str = "voz", trace: str = "",
        urgent: bool = False, task_id: str = "", **fields) -> str:
    """A new task of the queue, `pending` at the END of its lane (or first, `urgent`). Returns its id ("" if refused)."""
    if owner not in OWNERS:
        _say("refused", {"id": task_id, "owner": owner}, "owner", why=f"unknown owner «{owner}»")
        return ""
    import secrets
    tid = str(task_id or f"q-{int(time.time())}-{secrets.token_hex(3)}")
    with _lock:
        rows = _store().queue_rows(owner)
        last = max((float(r.get("position") or 0) for r in rows), default=0.0)
        row = {"id": tid, "title": str(title or goal)[:200], "goal": str(goal or title)[:8000],
               "kind": str(kind or owner), "state": PENDING, "origin": str(origin or "voz"), "trace_id": str(trace or ""),
               "owner": owner, "priority": 0, "position": last + 1.0, "created_at": int(time.time()),
               **{k: v for k, v in fields.items() if k in BIRTH}}
        row["num"] = _store().queue_insert(row)
        if not row["num"]:
            _say("refused", row, "owner", why="the task is already in the queue")
            return ""
        if urgent:
            row["priority"], row["position"] = _head(owner, tid)
            _store().queue_patch(tid, priority=row["priority"], position=row["position"])
        _say("add", row, "owner")
    return tid


def signal(task_id: str, what: str, *, by: str, **fields) -> bool:
    """Apply one signal to one task of the queue. True when applied; False (and `queue/refused`) when refused."""
    tid = str(task_id or "")
    with _lock:
        row = _store().task_get(tid) if tid else None
        if not row or not row.get("owner"):
            _say("refused", {"id": tid}, by, signal=what, why="not in the queue")
            return False
        to = JUMPS.get(str(row.get("state") or ""), {}).get(what)
        if to is None or by not in SENDERS:
            _say("refused", row, by, signal=what, why=f"no jump «{what}» from «{row.get('state')}» by «{by}»")
            return False
        if to == ARCHIVE:
            _remember(row, what, str(fields.get("outcome") or ""))   # once: an archived task takes no more signals
            _store().queue_archive(tid)
            _say(what, row, by, outcome=str(fields.get("outcome") or "")[:400])
            from nucleo.queue import lanes
            lanes.left(tid)                      # an owner still waiting for its turn is never left waiting
            _next()
            return True
        put = {k: v for k, v in fields.items() if k in FIELDS.get(what, ())}
        now = int(time.time())
        if what == "start":
            put["started_at"] = now
        elif what == "wait":
            put["waiting_since"] = now
        elif what == "back":
            put.update(waiting_for="", waiting_since=None, deadline=None, ask="", ask_id="")
            put["priority"], put["position"] = _head(str(row["owner"]), tid)
        elif what == "priority":
            put["priority"], put["position"] = (_head(str(row["owner"]), tid) if fields.get("urgent")
                                                else (0, float(row.get("position") or 0)))
        elif what == "move":
            got = _moved(row, str(fields.get("before") or ""))
            if got is None:
                _say("refused", row, by, signal=what, why=f"«{fields.get('before')}» is not a pending task of its lane")
                return False
            put["priority"], put["position"] = got
        _store().queue_patch(tid, state=PENDING if to == PENDING else (RUNNING if to == RUNNING else WAITING), **put)
        _say(what, row, by, state=to,          # inside the lock: the events come out in the order signals applied
             changed={k: str(v)[:160] for k, v in put.items() if k != "progress"})
    if to == WAITING and what == "wait":
        _next()                                  # a task that waits for him leaves its place: the next one starts now
    return True


def wrote(task_id: str, what: str, **fields) -> bool:
    """The door the old writers of a task row take: when the row is a task of the queue, the change goes to it as a
    signal from its owner and True is returned (the caller writes nothing); False for a row that is not one."""
    row = _store().task_get(str(task_id or "")) if task_id else None
    if not row or not row.get("owner"):
        return False
    signal(str(task_id), what, by="owner", **fields)
    return True


def _remember(row: dict, what: str, outcome: str) -> None:
    """What a task that leaves the queue leaves behind: ONE short-lived pill — what it was and how it ended — that names
    its row and the result kept in its artifacts (`task_artifacts`, which stay). REM forgets it. Never raises."""
    tid = str(row.get("id") or "")
    try:
        from memory import api as _memory
        name = str(row.get("title") or row.get("goal") or tid).strip()[:200]
        _memory.write(f"{name}: {(outcome or what).strip()[:600]}", kind="task", level="short", importance=0.3,
                      ttl_days=7, meta={"task_id": tid, "owner": str(row.get("owner") or ""), "state": what,
                                        "num": row.get("num"), "trace": str(row.get("trace_id") or ""),
                                        "artifacts": sorted(_store().artifacts_of(tid))})
    except Exception as e:  # noqa: BLE001 — a task that ended is not kept in the queue over its pill
        logger.debug(f"queue: the pill of {tid} not written ({e!r})")


def _next() -> None:
    """Its lane's running place is free: the next task starts now, not at the next beat (Q-5)."""
    try:
        from nucleo.queue import lanes
        lanes.tick()
    except Exception as e:  # noqa: BLE001 — the beat starts it anyway
        logger.debug(f"queue: the next task not started now ({e!r})")


def view() -> dict:
    """The queue as both views read it: per lane, the task that runs, then the pending ones in order, and the ones
    waiting for him apart."""
    out = {o: {RUNNING: [], PENDING: [], WAITING: []} for o in OWNERS}
    for r in _store().queue_rows():
        lane = out.get(str(r.get("owner") or ""))
        if lane is not None and r.get("state") in lane:
            lane[r["state"]].append(r)
    return out
