"""nucleo/pulse/voice_recycle.py — a LiveKit recycle is bounded and verified; a dead voice never stays dead quietly
(V2-871).

Measured on a hosted Machine: the heartbeat read the embedded worker as degraded and recycled it «cold». The recycle
awaited the old server's `aclose()` with no bound — and that close cancels the worker's LiveKit connection FIRST
(the worker is gone from dispatch) and then waits for the job executor, which is the very thing that was stuck —
reproduced twice right after boot: «job did not ack shutdown in time», and the close never returned: no new server was made, the heartbeat itself stayed parked in that await, and the voice was dead for
the rest of the process while HTTP, the health check and the text path stayed green. Nothing retried, nothing said so.

The mechanism, every number declared in `config/resources.default.json`:
  * `recycle()` — the old server's close is waited for `recycle_close_s`, then ABANDONED (its close and run tasks
    cancelled, its fixed health port released) and the new server is made anyway; the new one must be REGISTERED with
    LiveKit within `recycle_verify_s`, else it is retried with a doubling `recycle_backoff_s`, up to
    `recycle_attempts`. Every step is an event (`cat: voice`, `kind_diag` recycle_start|ok|failed|gave_up).
  * `check_dead()` — a recycle that gave up, or no live worker `voice_dead_s` after a voice session was asked for:
    an alert (the timeline attaches the memory `pressure` block) and, under a supervisor (`ZAELAR_SUPERVISED=1`), the
    process exits the way the self watchdog does so it is started again; without one, it keeps retrying every
    `recycle_retry_s` and says it once through the out-of-turn mouth.
  * `in_boot_grace()` — the first `boot_grace_s` after the process started pay the warm-up (models, the browser,
    the first connection): a reading from that window is the cold start, not a degraded engine.
"""
from __future__ import annotations

import asyncio
import logging
import time

log = logging.getLogger(__name__)

_DEFAULTS = {"recycle_close_s": 10.0, "recycle_verify_s": 30.0, "recycle_attempts": 3, "recycle_backoff_s": 5.0,
             "recycle_retry_s": 120.0, "voice_dead_s": 120.0, "boot_grace_s": 300.0}
_state: dict = {"requested": 0.0, "gave_up": False, "told": False, "retry_at": 0.0}


def policy() -> dict:
    from nucleo.workers import envelope
    pol = envelope.policy()
    return {k: float(pol.get(k, v)) for k, v in _DEFAULTS.items()}


def grace_end() -> float:
    """Wall-clock end of the cold-start window: a reading stamped before it is the warm-up."""
    from nucleo import runtime_ids
    return runtime_ids.boot_wall() + policy()["boot_grace_s"]


def in_boot_grace(now: float | None = None) -> bool:
    return (time.time() if now is None else now) < grace_end()


def note_session_requested(now: float | None = None) -> None:
    """A voice session was asked for (a room token was minted): from now on a missing worker is a dead voice."""
    _state["requested"] = time.time() if now is None else now


_app: dict = {"app": None}


def use_app(app) -> None:
    """The process that runs the EMBEDDED worker hands its app over (its `state` holds the worker and its task)."""
    _app["app"] = app


def starting() -> bool:
    """V2-873 — this process embeds a voice worker that is not REGISTERED with LiveKit yet. A room made now is never
    dispatched an agent (the server dispatches a room when it is born, to the workers registered then), so the token
    door holds the room back until the worker can take it. No embedded worker → False (nothing to wait for here)."""
    st = getattr(_app["app"], "state", None)
    if st is None or getattr(st, "lk_task", None) is None:
        return False
    return not worker_alive(getattr(st, "lk_server", None), getattr(st, "lk_task", None))


def worker_alive(server, task) -> bool:
    """The embedded worker is running AND registered with LiveKit (it has a worker id and is not reconnecting)."""
    if server is None or task is None or task.done():
        return False
    if getattr(server, "_closed", True) or getattr(server, "_connecting", False):
        return False
    return str(getattr(server, "id", "") or "unregistered") != "unregistered"


def _emit(step: str, text: str = "", **extra) -> None:
    try:
        from voice import observer
        observer.emit("homeostasis", step, text, extra={"cat": "voice", "kind_diag": step, **extra})
    except Exception as e:  # noqa: BLE001 — the recycle never dies of its own report
        log.warning("voice_recycle: %s not emitted (%r)", step, e)


async def _close_bounded(old, old_task, close_s: float) -> bool:
    """Close the old server for at most `close_s`. True if it closed; False if it was abandoned."""
    if old is None:
        return True
    closing = asyncio.ensure_future(old.aclose())
    done, _ = await asyncio.wait({closing}, timeout=close_s)
    if closing in done:
        if not closing.cancelled() and closing.exception() is not None:
            log.warning("voice_recycle: old server close failed: %r", closing.exception())
        return True
    closing.cancel()                       # abandoned: never awaited again
    if old_task is not None and not old_task.done():
        old_task.cancel()
    port = getattr(old, "_http_server", None)   # the health port is FIXED: the new server must be able to bind it
    if port is not None:
        try:
            await asyncio.wait_for(port.aclose(), timeout=close_s)
        except Exception as e:  # noqa: BLE001 — the new server's bind says the rest
            log.warning("voice_recycle: old health port not released: %r", e)
    return False


async def _verify(server, task, verify_s: float, step_s: float = 0.25) -> str:
    """'' once the new worker is registered; else why not, within `verify_s`."""
    deadline = time.monotonic() + verify_s
    while time.monotonic() < deadline:
        if task.done():
            exc = None if task.cancelled() else task.exception()
            return f"run ended: {exc!r}"[:200]
        if worker_alive(server, task):
            return ""
        await asyncio.sleep(step_s)
    return f"not registered within {verify_s:g}s"


async def recycle(app, make_server, devmode: bool) -> bool:
    """Replace the embedded worker: bounded close, new server, verified registration, retried with backoff."""
    pol = policy()
    attempts = max(1, int(pol["recycle_attempts"]))
    for n in range(1, attempts + 1):
        _emit("recycle_start", f"{n}/{attempts}", attempt=n, of=attempts)
        st = app.state
        closed = await _close_bounded(getattr(st, "lk_server", None), getattr(st, "lk_task", None),
                                      pol["recycle_close_s"])
        try:
            new = make_server()
            st.lk_server = new
            st.lk_task = asyncio.create_task(new.run(devmode=devmode))
            why = await _verify(new, st.lk_task, pol["recycle_verify_s"])
        except Exception as e:  # noqa: BLE001 — a failed attempt is reported and retried
            why = f"build: {e!r}"[:200]
        if not why:
            _emit("recycle_ok", f"{n}/{attempts}", attempt=n, old_close="closed" if closed else "abandoned")
            _state.update(gave_up=False, told=False, retry_at=0.0)
            return True
        _emit("recycle_failed", why, attempt=n, of=attempts, old_close="closed" if closed else "abandoned")
        if n < attempts:
            await asyncio.sleep(pol["recycle_backoff_s"] * (2 ** (n - 1)))
    _emit("recycle_gave_up", f"{attempts} attempts", attempts=attempts)
    _state["gave_up"] = True
    return False


def _tell(supervised: bool) -> None:
    """The alert on his wall (with the timeline's pressure block) and, unsupervised, one line out of turn."""
    key = "voice_dead_exit" if supervised else "voice_dead"
    try:
        from i18n import langs
        from voice.observer import emit
        line = str(langs.words(f"alerts.{key}", default=key))
        emit("alert", line, role="system", extra={"cat": "voice", "kind_diag": key, "supervised": supervised})
    except Exception as e:  # noqa: BLE001
        log.warning("voice_recycle: %s alert not emitted (%r)", key, e)
        return
    if supervised:
        return
    try:
        from nucleo.pulse import notices
        asyncio.get_running_loop().create_task(notices.notify(
            "zaelar", line, key=f"voice_dead:{time.time_ns()}", kind="info", push_=False, about="voice_dead"))
    except Exception as e:  # noqa: BLE001 — the alert above still stands
        log.warning("voice_recycle: voice_dead notice not delivered (%r)", e)


async def check_dead(app, recycle_fn, now: float | None = None) -> str:
    """One reading: `ok` · `exit` (supervised: restart the process) · `retry` · `wait` (unsupervised, between tries)."""
    now = time.time() if now is None else now
    st = app.state
    if worker_alive(getattr(st, "lk_server", None), getattr(st, "lk_task", None)):
        _state.update(gave_up=False, told=False, retry_at=0.0)
        return "ok"
    pol = policy()
    asked = _state["requested"] and now - _state["requested"] >= pol["voice_dead_s"] and not in_boot_grace(now)
    if not (_state["gave_up"] or asked):
        return "ok"
    from nucleo.pulse import self_watchdog
    supervised = self_watchdog.supervised()
    if not _state["told"]:
        _state["told"] = True
        _tell(supervised)
    if supervised:
        self_watchdog.exit_for_restart("voice_dead")
        return "exit"
    if now < _state["retry_at"]:
        return "wait"
    _state["retry_at"] = now + pol["recycle_retry_s"]
    await recycle_fn(app)
    return "retry"
