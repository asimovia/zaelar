"""nucleo/suspend.py — once the idle stop has decided, how the engine goes to sleep, and how it notices it woke.

`nucleo/idle_stop.py` decides WHETHER an idle engine stops; this carries the stop out and reads the resume. Its state
is the one sleep under way (asked, accepted, refused) and the clock pair the pulse leaves on every beat.

HOW IT STOPS. First the pending wake report goes out (`wake.flush(force=True)`): a stop with a stale report would
sleep through the next notice, so a report that fails keeps the engine up and the stop is tried again later. Then
the goodnight: `engine.sleep` on every open stream, and one beat (`SLEEP_FLUSH_S`) so it is delivered; the client
covers its screen and waits for a gesture. Then:
  * with a SLEEP ENDPOINT (`ZAELAR_SLEEP_URL`, else `CONTROL_PLANE_URL` + `/sleep` when `CONTROL_PLANE_SERVICE_TOKEN`
    is set — the same header `wake.py` sends), it POSTs there and asks the deployment to SUSPEND this process's host.
    The contract, from the engine's side:
      - 202 — accepted; the suspend fires shortly after the answer. If the process is still running
        `SLEEP_CONFIRM_S` later WITHOUT having been suspended, the suspend failed: the clean exit below.
      - 200 — suspended inline: the answer arrives after the resume.
      - anything else, or no answer — refused: the clean exit, at once.
    The answer may never be seen at all (the host froze mid-request). That is why every one of these decisions is
    taken on the pulse (`step`), AFTER the pulse has looked for a resume (`note_tick`): a suspend followed by a resume
    is never read as a failure, and a resumed engine never exits.
  * with none (self-hosted, or a host too large to suspend), or when the deployment refuses: the server's own
    graceful shutdown (`request_exit`, set by `server/__main__.py`), never a signal to itself. The process ends with
    status 0, which a platform with an on-failure restart policy reads as "stopped on purpose".

RESUME. A suspended process simply continues later. The pulse notices it from the clocks (`resumed_between`): the
wall clock moved far more (or less) than the monotonic one (a frozen guest), or — after a sleep was asked for — the
gap between two beats is far longer than a beat. On a resume the idle state starts over from that instant (the short
grace again: whoever woke it must show up), the wake report is marked stale, and `engine.resumed` goes out as a
`session` event — a system event, so it never counts as real activity. Connectors reconnect on their own: each one's
loop already survives a dead socket.
"""
from __future__ import annotations

import asyncio
import os
import time

from loguru import logger

_state = {"requested": False, "since_ms": None, "clock": None, "sleep": None, "exit_pending": False,
          "resumes": 0, "hold_until": 0.0}
_exit_hook = {"fn": None}
#: How long the stop waits after `engine.sleep` is published, so the open streams carry it before they close.
SLEEP_FLUSH_S = 1.0
#: After a 202 from the sleep endpoint, how long the process may still run unsuspended before the suspend is read as
#: failed and the engine exits instead.
SLEEP_CONFIRM_S = 20.0
#: How long the POST to the sleep endpoint may take. No answer is a refusal, unless the pulse saw a resume meanwhile.
SLEEP_POST_TIMEOUT_S = 10.0
#: A failed wake report keeps the engine up; the stop is tried again this much later.
WAKE_RETRY_S = 120.0
#: Resume detection. The wall clock moved this much more (or less) than the monotonic clock between two beats…
RESUME_SKEW_S = 10.0
#: …or, after a sleep was asked for, the gap between two beats exceeded the beat by this much.
SLEEP_GAP_S = 5.0


def sleep_url() -> tuple[str, str]:
    """(endpoint, token) of the deployment's sleep endpoint — ("", "") when it has none. Mirrors `wake.url()`."""
    explicit = (os.getenv("ZAELAR_SLEEP_URL") or "").strip()
    token = (os.getenv("CONTROL_PLANE_SERVICE_TOKEN") or "").strip()
    if explicit:
        return explicit, token
    cp = (os.getenv("CONTROL_PLANE_URL") or "").strip().rstrip("/")
    if cp and token:
        return cp + "/sleep", token
    return "", ""


def request_exit(fn) -> None:
    """Registered by the entrypoint: the callable that asks the server to shut down gracefully."""
    _exit_hook["fn"] = fn


def can_exit() -> bool:
    return _exit_hook["fn"] is not None


def resumed_at_ms() -> int | None:
    """The instant of the last resume, or None when this process never resumed — the idle state counts from it."""
    return _state["since_ms"]


def resumed_between(wall_gap_s: float, mono_gap_s: float, tick_s: float, *, sleeping: bool = False) -> bool:
    """Whether the process was frozen between two beats. Pure.

    A frozen guest's monotonic clock stands still while its wall clock is corrected on resume (or the other way round
    until the correction lands): a skew of `RESUME_SKEW_S` either way is a freeze, whenever it happens. After a sleep
    was asked for, a gap longer than the beat by `SLEEP_GAP_S` is one too, whichever clock shows it: the host may
    count the frozen time on both. Without a sleep asked for, a long gap on both clocks is a slow beat (a
    consolidation, a stall), never a resume."""
    if abs(wall_gap_s - mono_gap_s) > RESUME_SKEW_S:
        return True
    return sleeping and max(wall_gap_s, mono_gap_s) > tick_s + SLEEP_GAP_S


def note_tick(wall: float | None = None, mono: float | None = None, tick_s: float = 1.0, *,
              enabled: bool = True) -> bool:
    """The pulse's first call on every beat: True when the process was suspended and has just resumed."""
    wall = time.time() if wall is None else wall
    mono = time.monotonic() if mono is None else mono
    prev, _state["clock"] = _state["clock"], (wall, mono)
    if prev is None or not enabled:
        return False
    wall_gap, mono_gap = wall - prev[0], mono - prev[1]
    if not resumed_between(wall_gap, mono_gap, tick_s, sleeping=_state["requested"]):
        return False
    _on_resume(wall, wall_gap)
    return True


def _on_resume(wall: float, gap_s: float = 0.0) -> None:
    """Awake again: the idle state starts over from now, the wake report is stale, and the stream says so."""
    asked = _state["requested"]
    _state.update(requested=False, sleep=None, exit_pending=False, since_ms=round(wall * 1000), clock=None,
                  hold_until=0.0, resumes=_state["resumes"] + 1)
    logger.info(f"idle stop: resumed after {gap_s:.0f} s ({'asked to sleep' if asked else 'not asked to sleep'})")
    try:
        from nucleo.pulse import wake
        wake.note_changed()
    except Exception as e:  # noqa: BLE001 — the next schedule change marks it again
        logger.warning(f"idle stop: wake report not marked stale on resume: {e!r}")
    try:
        from voice.observer import emit
        emit("session", "engine.resumed", extra={"gap_s": round(gap_s, 1), "asked": asked})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"idle stop: engine.resumed not published: {e!r}")


def step() -> bool | None:
    """One pulse's turn for a sleep already under way, taken after `note_tick`: True when it carried out the exit,
    False while the sleep is pending (or held after a failed report), None when none is under way."""
    if _state["exit_pending"]:                          # the deployment refused the sleep, or never answered
        _state["exit_pending"] = False
        logger.info("idle stop: the sleep was refused or unanswered — exiting cleanly instead")
        return _exit()
    pending = _state["sleep"]
    if pending is not None:
        if time.monotonic() < pending["deadline"]:
            return False
        _state["sleep"] = None
        logger.warning(f"idle stop: the sleep was accepted but no suspend came in {SLEEP_CONFIRM_S:.0f} s — exiting")
        return _exit()
    if _state["requested"] or time.monotonic() < _state["hold_until"]:
        return False
    return None


def begin(why: str) -> bool:
    """Start the sleep the idle stop decided (`why` is its reason). True when it started, or carried out the exit."""
    _state["requested"] = True
    logger.info(f"idle stop: {why} — going to sleep")
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:                                # no loop (a script, a test): goodnight and the clean exit
        _say_goodnight()
        return _exit()
    loop.create_task(_go_to_sleep(), name="nucleo:idle-stop")
    return True


async def _go_to_sleep() -> None:
    """Report → goodnight → sleep endpoint (or the clean exit). See the module docstring for the contract."""
    try:
        if not await _flush_wake():
            _state.update(requested=False, hold_until=time.monotonic() + WAKE_RETRY_S)
            logger.warning("idle stop: the wake report failed — staying up so the next notice is not slept "
                           f"through; trying again in {WAKE_RETRY_S:.0f} s")
            return
        _say_goodnight()
        await asyncio.sleep(SLEEP_FLUSH_S)              # one beat for `engine.sleep` to reach the open streams
        endpoint, token = sleep_url()
        if not endpoint:
            _exit()
            return
        epoch = _state["resumes"]
        status = await _post_sleep(endpoint, token)
        if _state["resumes"] != epoch:
            return                                      # suspended and resumed meanwhile: awake, nothing to do
        if status == 200:
            _on_resume(time.time())                     # suspended inline: this answer arrived after the resume
        elif status is not None and 200 <= status < 300:
            _state["sleep"] = {"deadline": time.monotonic() + SLEEP_CONFIRM_S}
            logger.info(f"idle stop: sleep accepted ({status}) — waiting to be suspended")
        else:
            logger.info(f"idle stop: sleep refused ({status}) — the clean exit on the next beat")
            _state["exit_pending"] = True               # decided on the pulse, after it has looked for a resume
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001 — a stop that broke falls back to the clean exit on the next beat
        logger.warning(f"idle stop: the sleep sequence failed: {e!r}")
        _state["exit_pending"] = True


async def _flush_wake() -> bool:
    """Send a stale wake report now. True when nothing is left unreported (or there is nowhere to report to)."""
    from nucleo.pulse import wake
    if not wake.url()[0]:
        return True
    await wake.flush(force=True)
    return not wake.pending()


async def _post_sleep(endpoint: str, token: str) -> int | None:
    """The HTTP status of the sleep request, or None when it could not be made or answered."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=SLEEP_POST_TIMEOUT_S) as c:
            r = await c.post(endpoint, json={}, headers={"X-Service-Token": token} if token else {})
        return r.status_code
    except Exception as e:  # noqa: BLE001
        logger.warning(f"idle stop: the sleep request failed: {e!r}")
        return None


def _say_goodnight() -> None:
    """`engine.sleep` on every open stream: the client covers its screen and waits for a gesture instead of
    reconnecting (a reconnect is a request, and a request starts a stopped engine again)."""
    try:
        from voice.observer import emit
        emit("session", "engine.sleep")
    except Exception as e:  # noqa: BLE001 — a lost goodnight never keeps the engine up
        logger.warning(f"idle stop: engine.sleep not published: {e!r}")


def _exit() -> bool:
    try:
        _exit_hook["fn"]()
    except Exception as e:  # noqa: BLE001
        _state["requested"] = False
        logger.warning(f"idle stop: the exit request failed: {e!r}")
        return False
    return True


def _reset_for_tests() -> None:
    _state.update(requested=False, since_ms=None, clock=None, sleep=None, exit_pending=False, resumes=0,
                  hold_until=0.0)
    _exit_hook["fn"] = None
