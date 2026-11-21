"""The lanes of the queue: ONE task at a time per owner, in order (INI-078 Q-5, `LANES`).

A task of the queue does not start by itself. Its owner waits for its TURN (`my_turn`), and the pulse's beat (`tick`)
gives it: in every lane with nothing `running`, the first `pending` task whose owner is waiting for it is started — a
`start` signal, by the pulse — unless the lane's gate says why not now (the worker lane's is the resource envelope: the
voice never starves). A task that leaves its lane running (it waits for him, or it ends) lets the next one start at once.
"""
from __future__ import annotations

import asyncio
import threading
from typing import Callable

from loguru import logger

from nucleo import queue as _q

#: one lane per owner: one task of each runs at a time (a message is never held behind a long search)
LANES = _q.OWNERS

_lock = threading.Lock()
#: task id → (its loop, its event, what to tell while it is held) — the owners waiting for a task's turn
_waiters: dict[str, tuple] = {}
#: task id → the last reason told while it waits (told once per change)
_told: dict[str, str] = {}
#: lane → why a task of it cannot start NOW ("" when it can): declared by the lane's owner
_gates: dict[str, Callable[[], str]] = {}


def gate(lane: str, why_not: Callable[[], str]) -> None:
    """The lane's owner declares what may hold its next task (read at every tick)."""
    _gates[lane] = why_not


class Left(Exception):
    """The task left the queue while its owner waited for its turn (cancelled, or archived): it never runs."""


async def my_turn(task_id: str, held: Callable[[str], None] | None = None) -> None:
    """Wait until the queue gives this task its turn (`running`). Returns at once when it already has it (a relay, or
    a session resumed on a task that never left its lane). Raises `Left` when the task leaves the queue while it waits:
    a waiter is never left waiting for good."""
    row = _q._store().task_get(task_id) or {}
    if row.get("state") == _q.RUNNING:
        return
    ev = asyncio.Event()
    with _lock:
        _waiters[task_id] = (asyncio.get_running_loop(), ev, held)
    try:
        tick()
        if not ev.is_set() and task_id not in _told:
            _held(task_id, "queued_behind")          # behind the task its lane runs (a gate that held it said why)
        await ev.wait()
        if (_q._store().task_get(task_id) or {}).get("state") != _q.RUNNING:
            raise Left(task_id)
    finally:
        with _lock:
            _waiters.pop(task_id, None)
            _told.pop(task_id, None)


def is_task(task_id: str) -> bool:
    """Is this id a task of the queue (a row with an owner)? Internal work is not, and never waits for a turn."""
    return bool(task_id and (_q._store().task_get(task_id) or {}).get("owner"))


def not_tasks(sessions: list[dict]) -> list[dict]:
    """The sessions that are not tasks of the queue: the queue takes its own back at boot (`queue/boot`)."""
    return [s for s in sessions if not is_task(str(s.get("uid") or ""))]


def waiting(task_id: str) -> bool:
    with _lock:
        return task_id in _waiters


def left(task_id: str) -> None:
    """The task left the queue: whoever waited for its turn is woken, to find it gone (`Left`)."""
    _wake(task_id)


def _wake(task_id: str) -> None:
    with _lock:
        got = _waiters.get(task_id)
    if got is not None:
        loop, ev, _held = got
        loop.call_soon_threadsafe(ev.set)


def _held(task_id: str, why: str) -> None:
    with _lock:
        got = _waiters.get(task_id)
        if got is None or _told.get(task_id) == why:
            return
        _told[task_id] = why
    if got[2] is not None:
        try:
            got[2](why)
        except Exception as e:  # noqa: BLE001 — telling why it waits never decides whether it starts
            logger.debug(f"queue: the held reason of {task_id} not told ({e!r})")


def tick() -> list[str]:
    """Start, in each lane with nothing running, its first pending task whose owner waits for it. Returns the ids
    started. Called on the pulse's beat and whenever a task leaves its lane's running place."""
    started = []
    lanes = _q.view()
    for lane in LANES:
        if lanes[lane][_q.RUNNING]:
            continue
        nxt = next((r for r in lanes[lane][_q.PENDING] if waiting(str(r["id"]))), None)
        if nxt is None:
            continue
        why = ""
        try:
            why = str((_gates.get(lane) or (lambda: ""))() or "")
        except Exception as e:  # noqa: BLE001 — a gate that cannot be read holds nothing
            logger.debug(f"queue: the {lane} lane's gate unread ({e!r})")
        if why:
            _held(str(nxt["id"]), why)
            continue
        if _q.signal(str(nxt["id"]), "start", by="pulse"):
            _wake(str(nxt["id"]))
            started.append(str(nxt["id"]))
    return started
