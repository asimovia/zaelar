"""nucleo/idle_stop.py — an engine nobody is using goes to sleep, or ends its own process, cleanly.

A deployment that runs one engine per account and pays for it by the minute relies on its platform to stop an idle
one. The platform decides "idle" from network traffic, and a half-open connection (a laptop that went to sleep with a
tab open) can look like traffic for hours. The engine knows better: it keeps a clock of REAL activity
(`observability/identity.py` — voice, workers, memory, widgets; never the pulse, a heartbeat or a widget's own
background tick) and a clock of PRESENCE (`voice/screens.py`).

So, when enabled, the pulse asks `maybe_stop()` once per tick, and the engine stops when ALL hold:
  * no real activity and nobody present for `ZAELAR_IDLE_STOP_MIN` minutes (counted from the later of those and the
    process start — or the last resume);
  * no Brain Worker session is active;
  * the next scheduled notice the engine can still fire is not due within that same window (a deployment that wakes
    engines for notices starts it again before it — `nucleo/pulse/wake.py`). A job already past due when the pulse
    reaches this check is one this tick could not fire (⏻ off and no device to push to, or work that waits for ⏻):
    it waits for a person, not for the clock, so it vetoes nothing (`nucleo/pulse/due.py::next_owed`).

PRESENCE IS A CONNECTED PERSON. A screen's input (a touch, a typed line, a spoken turn) is presence, and so is a
VISIBLE tab whose stream is open: it says so with a beat every minute (`frontend/app/services/presence.js`), which
the server records as `screens.present()`. A stream open alone never is — a reconnecting tab is a request, not a
person — and a tab with no input for `tab_sleep_min` stops beating and closes its stream. Until someone is present
after boot (or after a resume) the window is the short `wake_grace_min`: an engine woken by a request that brought
nobody stops again in about a minute instead of a full window. Workers and due notices keep their veto in both.

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
    taken on the pulse, AFTER the pulse has looked for a resume (`note_tick`): a suspend followed by a resume is
    never read as a failure, and a resumed engine never exits.
  * with none (self-hosted, or a host too large to suspend), or when the deployment refuses: the server's own
    graceful shutdown (`request_exit`, set by `server/__main__.py`), never a signal to itself. The process ends with
    status 0, which a platform with an on-failure restart policy reads as "stopped on purpose".

RESUME. A suspended process simply continues later. The pulse notices it from the clocks (`resumed_between`): the
wall clock moved far more (or less) than the monotonic one (a frozen guest), or — after a sleep was asked for — the
gap between two beats is far longer than a beat. On a resume the idle state starts over from that instant (the short grace again: whoever woke it must show up),
the wake report is marked stale, and `engine.resumed` goes out as a `session` event — a system event, so it never
counts as real activity. Connectors reconnect on their own: each one's loop already survives a dead socket.

Off by default: with `ZAELAR_IDLE_STOP_MIN` unset or 0 nothing here ever runs — a self-hosted engine stays up.
"""
from __future__ import annotations

import asyncio
import os
import time

from loguru import logger

_STARTED_MS = round(time.time() * 1000)
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
#: Fallbacks when the resources policy cannot be read (its keys `wake_grace_min` and `tab_sleep_min`).
_POLICY_FALLBACK = {"wake_grace_min": 1, "tab_sleep_min": 10}


def window_min() -> int:
    try:
        return max(0, int(os.getenv("ZAELAR_IDLE_STOP_MIN", "0") or 0))
    except ValueError:
        return 0


def _policy_min(key: str) -> float:
    """A minutes value declared in the resources policy (`nucleo/workers/envelope.policy`); never negative."""
    try:
        from nucleo.workers import envelope
        return max(0.0, float(envelope.policy().get(key, _POLICY_FALLBACK[key])))
    except Exception:  # noqa: BLE001 — an unreadable policy keeps the declared default
        return float(_POLICY_FALLBACK[key])


def wake_grace_min() -> float:
    """The window for an engine nobody has come to since boot or resume. `ZAELAR_WAKE_GRACE_MIN` overrides the
    policy for one deployment; the policy's value is the default."""
    raw = (os.getenv("ZAELAR_WAKE_GRACE_MIN") or "").strip()
    if raw:
        try:
            return max(0.0, float(raw))
        except ValueError:
            logger.warning(f"idle stop: ZAELAR_WAKE_GRACE_MIN={raw!r} is not a number — the policy's value holds")
    return _policy_min("wake_grace_min")


def tab_sleep_min() -> float:
    """How long a visible tab with no input keeps its stream (the client reads it from the stream's hello). An engine
    that never stops (no idle stop: a self-hosted laptop) never puts a tab to sleep — an open stream costs it nothing,
    and a wall display is read without being touched — so it tells the tab 0."""
    return _policy_min("tab_sleep_min") if window_min() > 0 else 0.0


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


def decide(now_ms: int, last_real_ms: int | None, started_ms: int, workers_active: bool,
           next_due_s: float | None, window_ms: int, *, last_presence_ms: int | None = None,
           grace_ms: int = 0) -> str | None:
    """Why the engine should stop now, or None. Pure — the clock and every reading come in as arguments.

    `last_presence_ms` is the last moment a person was present (input, or a visible connected screen's beat); nothing
    else is presence. Until one lands after `started_ms` (the boot or the last resume), the window is `grace_ms`
    counted from that start alone (`last_real_ms` is not read: a boot moves it with nobody there); after it, the full
    window from the latest activity of either kind."""
    if window_ms <= 0:
        return None
    present = last_presence_ms is not None and last_presence_ms >= started_ms
    if not present and 0 < grace_ms < window_ms:
        quiet_ms, win, what = now_ms - started_ms, grace_ms, "nobody present since boot or resume"
    else:
        quiet_ms = now_ms - max(last_real_ms or 0, last_presence_ms or 0, started_ms)
        win, what = window_ms, "no real activity and nobody present"
    if quiet_ms < win:
        return None
    if workers_active:
        return None
    if next_due_s is not None and next_due_s * 1000 - now_ms < window_ms:
        return None
    return f"{what} for {quiet_ms // 60000} min, no worker running, no notice due within {window_ms // 60000} min"


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


def note_tick(wall: float | None = None, mono: float | None = None, tick_s: float = 1.0) -> bool:
    """The pulse's first call on every beat: True when the process was suspended and has just resumed."""
    wall = time.time() if wall is None else wall
    mono = time.monotonic() if mono is None else mono
    prev, _state["clock"] = _state["clock"], (wall, mono)
    if prev is None or not window_min():
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


def _since_ms() -> int:
    return _state["since_ms"] or _STARTED_MS


def _readings(now: float) -> tuple[int | None, bool, float | None]:
    from observability import identity
    last = identity.last_real_activity_ms()
    try:
        from nucleo.dispatch import registry
        workers = registry.has_active()
    except Exception:  # noqa: BLE001 — unreadable counts as busy: never stop on a guess
        workers = True
    try:
        from nucleo.pulse import due
        nxt = due.next_owed(now)
    except Exception:  # noqa: BLE001
        return last, workers, 0.0                      # unreadable schedule: treat a notice as imminent
    return last, workers, nxt


def _last_presence() -> int | None:
    """The last moment a person was present on any screen (`voice/screens.py`) — input or a visible connected beat."""
    try:
        from voice import screens
        return screens.last_presence_ms()
    except Exception as e:  # noqa: BLE001 — unreadable: nobody counted as present, the grace holds
        logger.warning(f"idle stop: screen presence unreadable, nobody counted as present: {e!r}")
        return None


def maybe_stop(now: float | None = None) -> bool:
    """One pulse's check, called after `note_tick`. True when it started a stop, or carried one out."""
    window = window_min() * 60_000
    if not window or _exit_hook["fn"] is None:
        return False
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
    now = time.time() if now is None else now
    now_ms = round(now * 1000)
    last, workers, nxt = _readings(now)
    why = decide(now_ms, last, _since_ms(), workers, nxt, window, last_presence_ms=_last_presence(),
                 grace_ms=round(wake_grace_min() * 60_000))
    if not why:
        return False
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
