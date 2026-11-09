"""nucleo/workers/room.py — a browser launch asks the worker envelope for room first (V2-867 F2).

A Chromium is the heaviest thing the engine starts besides a worker, and the two places that launch one (the operator's
window, `widgets/navegador/owner_page.py`; the search module's headless browser, `search/browser.py`) used to launch it
outside the envelope: on a small host three of them plus one worker left 45 MB free and the voice broke.

The rule, as mechanism (every threshold is the envelope's own declared data — `admits`, `shedding`):
  · with room (over the floor and the voice not shedding) the launch goes at once;
  · without room the NEWEST running worker that nobody else paused is paused (the same reversible pause `relieve`
    and the ⏻ use, marked `paused_by = "room"`), then the host is measured again;
  · the operator's own window is never refused: it waits at most one poll for the pause to take effect and launches
    (`patient=False`); a background browser waits for room as long as it takes, like a worker (`patient=True`) — its
    caller's own timeout is the exit, never a deadline start here;
  · after the launch a poll resumes what THIS module paused once room returns — never a pause of the operator's ⏻
    or of the envelope's, and nothing at all while the agent is stopped (the ⏻'s own resume owns them then).

A running worker is only ever paused and resumed here, never killed.
"""
from __future__ import annotations

import asyncio
import contextlib

from loguru import logger

from nucleo.workers import envelope

MARK = "room"                 # the `paused_by` this module writes, and the only one it ever undoes
_resumer: asyncio.Task | None = None


def _records() -> list:
    from nucleo import dispatch
    return list(dispatch._SESSIONS.values())


def has_room() -> bool:
    return not envelope.shedding() and envelope.admits(*envelope.measured())


def _live(records) -> list:
    """Running workers with a session, oldest first — the same reading of «newest» as `envelope.relieve`."""
    return sorted((r for r in records if getattr(r, "status", "") == "running" and getattr(r, "session", None)),
                  key=lambda r: float(getattr(r, "started", 0) or 0))


def _stopped() -> bool:
    try:
        from nucleo import runstate
        return runstate.stopped()
    except Exception:  # noqa: BLE001 — unreadable: do not resume anything on a guess
        return True


def _say(key: str, default: str, what: str, **extra) -> None:
    """One observability line per decision; its words come from the voice pack (`alerts.*`), English by default."""
    try:
        from i18n import langs
        text = str(langs.words(f"alerts.{key}", default=default))
    except Exception:  # noqa: BLE001
        text = default
    text = text.replace("{what}", what).replace("{task}", str(extra.get("task", "")))
    logger.info(f"room: {text}")
    try:
        from voice.observer import emit
        emit("task", text, role="system", extra={"cat": "worker", "kind_diag": key, "what": what, **extra})
    except Exception as e:  # noqa: BLE001 — a notice never blocks the launch
        logger.debug(f"room: notice not emitted: {e!r}")


def _pause_newest(what: str):
    """Pause the newest running worker nobody has paused; returns its record, or None when there is none to pause."""
    candidates = [r for r in _live(_records()) if not getattr(r, "paused", False)]
    if not candidates:
        return None
    newest = candidates[-1]
    try:
        ok = bool(newest.session.pause())
    except Exception as e:  # noqa: BLE001
        logger.warning(f"room: pause of {getattr(newest, 'task_id', '?')} failed: {e!r}")
        ok = False
    if not ok:
        return None
    newest.paused_by = MARK
    _say("room_paused", "Worker {task} paused to open the browser.", what, task=newest.task_id)
    return newest


def resume_ours() -> list[str]:
    """Resume every worker THIS module paused, if there is room now. Returns the task ids resumed."""
    out: list[str] = []
    ours = [r for r in _records() if getattr(r, "paused_by", "") == MARK]
    if not ours:
        return out
    if _stopped():
        # the ⏻ owns every paused worker now: its own resume continues them; our mark would only fight it
        for r in ours:
            r.paused_by = ""
        return out
    if not has_room():
        return out
    for r in ours:
        if getattr(r, "status", "") != "running" or not getattr(r, "paused", False) or not r.session:
            r.paused_by = ""                       # ended, or resumed by someone else: nothing of ours to undo
            continue
        try:
            ok = bool(r.session.resume())
        except Exception as e:  # noqa: BLE001
            logger.warning(f"room: resume of {r.task_id} failed: {e!r}")
            ok = False
        if ok:
            r.paused_by = ""
            out.append(r.task_id)
            _say("room_resumed", "Worker {task} resumed: there is room again.", "browser", task=r.task_id)
    return out


async def _resume_when_room(poll_s: float) -> None:
    while any(getattr(r, "paused_by", "") == MARK for r in _records()):
        resume_ours()
        if not any(getattr(r, "paused_by", "") == MARK for r in _records()):
            return
        await asyncio.sleep(poll_s)


def _schedule_resume(poll_s: float) -> None:
    global _resumer
    if not any(getattr(r, "paused_by", "") == MARK for r in _records()):
        return
    loop = asyncio.get_running_loop()
    if _resumer is not None and not _resumer.done() and _resumer.get_loop() is loop:
        return
    _resumer = loop.create_task(_resume_when_room(poll_s))


async def _make_room(what: str, patient: bool, poll_s: float) -> str:
    """Hold until the launch may go. Returns `"room"`, `"made"` (a pause gave it room) or `"anyway"`."""
    if has_room():
        _say("room_ok", "Room for the {what}: it opens now.", what)
        return "room"
    paused = _pause_newest(what)
    said = False
    while True:
        await asyncio.sleep(poll_s)
        if has_room():
            return "made" if paused is not None else "room"
        if not patient:
            _say("room_anyway", "Little room, but it is your window: the {what} opens anyway.", what)
            return "anyway"
        if not said:
            _say("room_wait", "Waiting for room to open the {what}.", what)
            said = True
        if paused is None:
            paused = _pause_newest(what)


@contextlib.asynccontextmanager
async def room_for(what: str, *, patient: bool = True, poll_s: float = 2.0):
    """`async with room_for("browser"):` around a Chromium launch. See the module docstring for the rule."""
    try:
        try:
            await _make_room(what, patient, poll_s)
        except Exception as e:  # noqa: BLE001 — an unreadable host never keeps a browser shut; it says so
            logger.warning(f"room: could not measure the host ({e!r}) — the {what} opens")
        yield
    finally:
        with contextlib.suppress(RuntimeError):     # no running loop: nothing to schedule on
            _schedule_resume(poll_s)
