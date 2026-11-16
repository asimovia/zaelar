"""nucleo/pulse/voice_rooms.py — no voice room outlives a freeze, and a room the token door mints is owed its agent
(V2-910).

THE CLASS. A host that is suspended with a voice room open (a phone put in a pocket keeps its connection for a
while; the engine idles out and goes to sleep with the room live) wakes with a LiveKit job that still believes it is
in that room. LiveKit ended that job during the freeze. On the resume the worker reconnects, registers, reports the
job it still holds (`MigrateJobRequest`), the server drops the connection, and the worker reconnects at once — a
loop several times a second, never registered long enough to be given a room. Measured on a hosted Machine: rooms
asked for after the resume were never joined, the job kept «speaking» into the dead room, and the page asked for a
new room 26 times in silence. A voice process that was fresh at the freeze survived the same resume.

THE GUARANTEE, in two places on purpose:
  * BEFORE THE SLEEP (`before_sleep`, called by `nucleo/suspend.py`) — a live room is closed and its close waited for
    `room_close_wait_s`, so the job is gone before the host freezes. This is the one that prevents the loop.
  * ON THE RESUME (`note_resumed` → the next pulse beat) — a freeze the engine did not ask for (the platform suspended
    it on its own) skips the first place. A room still live after a resume is closed; one that will not close in
    `room_close_wait_s` gets the voice process recycled (a fresh process registers with no job).
And one check that does not depend on knowing the cause:
  * OWED ROOMS (`note_minted` / `note_served` / `tick`) — every room the token door mints is owed its agent within
    `room_owed_s`. `rooms_unserved_cure` owed rooms in a row and the voice process is recycled (at most once every
    `room_cure_cooldown_s`), with an event: whatever keeps the worker from being dispatched, the person who keeps
    asking is not left asking.

Every step is an event with `kind_diag` voice_room_closed (`kind homeostasis`, routine) or voice_room_survived_freeze |
voice_rooms_unserved | voice_room_cure (`kind voice_fault`, shown whatever the viewer's filters, here and in any viewer
that mirrors the catalogue). A person in the live room is never cut by the cure (`held`). Every number is declared in
`config/resources.default.json`.
"""
from __future__ import annotations

import asyncio
import logging
import time

log = logging.getLogger(__name__)

_DEFAULTS = {"room_close_wait_s": 5.0, "room_owed_s": 30.0, "rooms_unserved_cure": 2.0, "room_cure_cooldown_s": 120.0}
_state: dict = {"minted": {}, "resumed_at": 0.0, "last_cure": 0.0, "busy": None}


def policy() -> dict:
    try:
        from nucleo.workers import envelope
        pol = envelope.policy()
    except Exception:  # noqa: BLE001 — an unreadable policy keeps the declared defaults
        pol = {}
    return {k: float(pol.get(k, v)) for k, v in _DEFAULTS.items()}


#: What the voice owed and did not do is a `voice_fault` (never hidden in the engine's viewer nor in the Master); the
#: routine close before a sleep is the heartbeat's own `homeostasis`.
_FAULTS = frozenset({"voice_room_survived_freeze", "voice_rooms_unserved", "voice_room_cure"})


def _emit(step: str, text: str = "", **extra) -> None:
    try:
        from voice import observer
        observer.emit("voice_fault" if step in _FAULTS else "homeostasis", step, text,
                      extra={"cat": "voice", "kind_diag": step, **extra})
    except Exception as e:  # noqa: BLE001 — the guarantee never dies of its own report
        log.warning("voice_rooms: %s not emitted (%r)", step, e)


# ── the voice process as this module sees it ─────────────────────────────────────────────────────────────────────
def _voice():
    """The voice's own process (V2-891), or None (embedded, or not started)."""
    try:
        from voice import child_process
        return child_process.current()
    except Exception:  # noqa: BLE001
        return None


def has_listener(voice=None) -> bool:
    """The live room has a person in it (the voice process says so in its status, V2-910)."""
    v = _voice() if voice is None else voice
    return bool(v is not None and getattr(v, "live", lambda: False)()
                and (getattr(v, "status", {}) or {}).get("listener"))


def live_room(voice=None) -> str:
    """The room the voice process holds a live session in ('' when none)."""
    v = _voice() if voice is None else voice
    if v is None or not getattr(v, "live", lambda: False)():
        return ""
    return str((getattr(v, "status", {}) or {}).get("room") or "?")


async def _wait_closed(voice, wait_s: float, step_s: float = 0.25) -> bool:
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        try:
            await voice._read_status()             # fresh, not the last reading of its own poll
        except Exception as e:  # noqa: BLE001 — unreadable this instant: the next reading says
            log.debug("voice_rooms: status not read (%r)", e)
        if not voice.live():
            return True
        await asyncio.sleep(step_s)
    return not voice.live()


async def close_live(reason: str, voice=None, wait_s: float | None = None) -> str:
    """Close the live room, if any, and wait for it: `none` · `closed` · `stuck` (still live after the wait)."""
    v = _voice() if voice is None else voice
    room = live_room(v)
    if not room:
        return "none"
    wait = policy()["room_close_wait_s"] if wait_s is None else wait_s
    try:
        await v.client.post("/voice/close", {"reason": reason}, timeout_s=wait)
    except Exception as e:  # noqa: BLE001 — the wait below reads whether it closed anyway
        log.warning("voice_rooms: close request failed (%r)", e)
    closed = await _wait_closed(v, wait)
    _emit("voice_room_closed", f"{reason}: {'closed' if closed else 'still live'}", reason=reason, room=room[-12:],
          closed=closed)
    return "closed" if closed else "stuck"


# ── 1 · before the sleep ─────────────────────────────────────────────────────────────────────────────────────────
async def before_sleep() -> str:
    """No room crosses a freeze: close the live one before the host is suspended."""
    return await close_live("sleep")


# ── 2 · on the resume ────────────────────────────────────────────────────────────────────────────────────────────
def note_resumed(now: float | None = None) -> None:
    """`nucleo/suspend.py` saw a resume: the next beat checks the voice. Owed rooms from before the freeze are void."""
    _state["resumed_at"] = time.time() if now is None else now
    _state["minted"].clear()


async def after_resume(app, recycle_fn) -> str:
    """`ok` (no room crossed the freeze) · `closed` · `recycled` (a room that would not close)."""
    v = _voice()
    room = live_room(v)
    if not room:
        return "ok"
    _emit("voice_room_survived_freeze", f"a room was live across the freeze ({room[-12:]})", room=room[-12:])
    if await close_live("resumed", v) == "closed":
        return "closed"
    await _cure(app, recycle_fn, "a room that crossed the freeze did not close")
    return "recycled"


# ── 3 · owed rooms ───────────────────────────────────────────────────────────────────────────────────────────────
def note_minted(room: str, now: float | None = None) -> None:
    """The token door minted `room`: it is owed its agent from now."""
    if room:
        _state["minted"][str(room)] = time.time() if now is None else now


def note_served(room: str) -> None:
    """The agent's session started in `room` (`voice/remote_session.py`): owed no more, and the run of unserved rooms
    is broken — every room minted before it is forgiven too."""
    t = _state["minted"].pop(str(room or ""), None)
    if t is not None:
        for r, at in list(_state["minted"].items()):
            if at <= t:
                _state["minted"].pop(r, None)


def unserved(now: float | None = None, owed_s: float | None = None) -> list[str]:
    """The rooms past their due time with no agent, oldest first."""
    now = time.time() if now is None else now
    owed = policy()["room_owed_s"] if owed_s is None else owed_s
    return [r for r, at in sorted(_state["minted"].items(), key=lambda kv: kv[1]) if now - at >= owed]


async def _cure(app, recycle_fn, why: str) -> bool:
    _state["last_cure"] = time.time()
    _emit("voice_room_cure", why, why=why)
    try:
        return bool(await recycle_fn(app))
    except Exception as e:  # noqa: BLE001
        log.warning("voice_rooms: recycle failed (%r)", e)
        return False


async def check_owed(app, recycle_fn, now: float | None = None) -> str:
    """`ok` · `wait` (owed rooms, inside the cooldown) · `held` (a person is in the live room) · `recycled`."""
    now = time.time() if now is None else now
    pol = policy()
    late = unserved(now, pol["room_owed_s"])
    if len(late) < int(pol["rooms_unserved_cure"]):
        return "ok"
    if now - _state["last_cure"] < pol["room_cure_cooldown_s"]:
        return "wait"
    for r in late:
        _state["minted"].pop(r, None)
    held = has_listener()
    _emit("voice_rooms_unserved", f"{len(late)} rooms asked for, no agent joined"
          + (" — a live room with a person in it is not cut" if held else ""),
          rooms=len(late), live_room=live_room()[-12:], held=held)
    if held:                                       # a conversation going on elsewhere is never the price of the cure
        return "held"
    await _cure(app, recycle_fn, f"{len(late)} rooms without the agent")
    return "recycled"


# ── the pulse ────────────────────────────────────────────────────────────────────────────────────────────────────
def tick(app, recycle_fn, now: float | None = None) -> None:
    """One pulse beat (`nucleo/pulse/loop.py`): never awaited there — a close or a recycle runs as ONE task at a time,
    so the beat stays a beat."""
    if app is None:
        return
    busy = _state["busy"]
    if busy is not None and not busy.done():
        return
    now = time.time() if now is None else now
    resumed = _state["resumed_at"]

    async def _run():
        if resumed:
            _state["resumed_at"] = 0.0
            await after_resume(app, recycle_fn)
        await check_owed(app, recycle_fn, now)
    if not resumed and len(unserved(now)) < int(policy()["rooms_unserved_cure"]):
        return
    _state["busy"] = asyncio.get_running_loop().create_task(_run(), name="nucleo:voice-rooms")


def _reset_for_tests() -> None:
    _state.update(minted={}, resumed_at=0.0, last_cure=0.0, busy=None)
