"""nucleo/pulse/wake.py — tell the deployment when this engine must be awake next (V2-796, V2-872 F2).

The loop that fires notices lives inside this process. A deployment that stops an idle engine (scale-to-zero
containers) would otherwise sleep straight through a reminder set for next Tuesday: the job is stored correctly
and never fires, because nothing is running to fire it.

So the engine reports its NEXT due instant to a wake endpoint, and the deployment starts the process a little before
it. ONE instant, the earliest of:

  * the scheduler's next job (`scheduler.next_due`);
  * the other clocks the pulse acts on by itself — an errand's expiry, a waiting row's deadline, an owed notice's retry
    (`deadlines.upcoming`, only instants still ahead);
  * when something LISTENS to an inbound channel (`listeners.active_listeners`: a connected channel that can be caught
    up AND a rule, a waiting row, an errand or his preference that reacts to it), the next listen pass — a fixed grid of
    `listen_every_min` (resources policy), so the instant is stable between passes.
With no job, no deadline and no listener the report is `null`: the engine may sleep until a person comes back.

The mechanism, nothing more:

  * `ZAELAR_WAKE_URL` — POST `{"next_due": <epoch s | null>}` there;
  * otherwise `CONTROL_PLANE_URL` + `/wake`, when `CONTROL_PLANE_SERVICE_TOKEN` is set too (same `X-Service-Token`
    header the engine already sends there).
With neither, this module does nothing — a self-hosted engine that is always on has no use for it.

Debounced: `note_changed()` only marks the report as stale; `flush()` (one call per loop pulse) sends at most one
report every `_MIN_GAP_S`, and only when the value changed. The report is ALSO stale, with nobody noting it, once the
instant it named has passed and every `_RECHECK_S` — a writer that forgets `note_changed()` delays a report by at
most that long, never loses it. A failed report is retried on the next pulse that is due — never raised into the loop.
"""
from __future__ import annotations

import logging
import os
import time

logger = logging.getLogger("zaelar.wake")

_MIN_GAP_S = 10.0
_RETRY_S = 120.0
#: However quiet the writers, the instant is recomputed at least this often while awake.
_RECHECK_S = 60.0
_UNSET = object()
_state = dict(dirty=True, sent=_UNSET, last=0.0, checked=0.0, why={})


def url() -> tuple[str, str]:
    """(endpoint, token) — ("", "") when this deployment has nowhere to report to."""
    explicit = (os.getenv("ZAELAR_WAKE_URL") or "").strip()
    token = (os.getenv("CONTROL_PLANE_SERVICE_TOKEN") or "").strip()
    if explicit:
        return explicit, token
    cp = (os.getenv("CONTROL_PLANE_URL") or "").strip().rstrip("/")
    if cp and token:
        return cp + "/wake", token
    return "", ""


def note_changed() -> None:
    _state["dirty"] = True


def next_due(now: float) -> tuple[float | None, dict]:
    """(the earliest instant this engine must be awake for, `{source: instant}` of every candidate).

    Raises only when the scheduler cannot be read — the one source whose loss must not report a false `null`."""
    from nucleo.pulse import scheduler
    candidates: dict[str, float] = {}
    nxt = scheduler.next_due()
    if nxt and float(nxt) <= now:
        # An overdue job is one the pulse could not fire (⏻ off, no device for the notice): it waits for a person,
        # whose return starts the engine anyway. Reporting it would wake the engine every minute for nothing.
        from nucleo.pulse import due
        nxt = due.next_owed(now)
    if nxt:
        candidates["scheduler"] = float(nxt)
    try:
        from nucleo.pulse import deadlines
        candidates.update(deadlines.upcoming(now))
    except Exception as e:  # noqa: BLE001
        logger.debug(f"wake: deadlines unreadable: {e!r}")
    try:
        from nucleo.pulse import listeners
        heard = listeners.active_listeners()
        if heard:
            candidates["listen:" + ",".join(sorted(heard))] = listeners.next_listen(now, listeners.listen_every_s())
    except Exception as e:  # noqa: BLE001
        logger.debug(f"wake: listeners unreadable: {e!r}")
    return (min(candidates.values()) if candidates else None), candidates


def _stale(now: float) -> bool:
    if _state["dirty"] or now - _state["checked"] >= _RECHECK_S:
        return True
    sent = _state["sent"]
    return isinstance(sent, (int, float)) and now >= sent      # the instant it named has come: the next one is new


def pending() -> bool:
    """True while a change of the schedule has not been reported (or its report failed)."""
    return bool(_state["dirty"])


async def flush(now: float | None = None, *, force: bool = False) -> bool:
    """Send the next due instant if it is stale. True when a report was sent and accepted. `force` skips the
    debounce: the idle stop flushes once right before the engine stops (`nucleo/idle_stop.py`)."""
    now = time.time() if now is None else now
    if not (_stale(now) or force) or (not force and now - _state["last"] < _MIN_GAP_S):
        return False
    endpoint, token = url()
    if not endpoint:
        _state["dirty"] = False
        _state["checked"] = now
        return False
    try:
        nxt, why = next_due(now)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"wake: next_due unreadable: {e!r}")
        return False
    _state["checked"] = now
    value = int(nxt) if nxt else None
    if value == _state["sent"]:
        _state["dirty"] = False
        return False
    _state["last"] = now
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.post(endpoint, json={"next_due": value},
                             headers={"X-Service-Token": token} if token else {})
        ok = r.status_code < 300
    except Exception as e:  # noqa: BLE001
        logger.warning(f"wake: report failed, retried later: {e!r}")
        ok = False
    if ok:
        _state.update({"dirty": False, "sent": value, "why": why})
        logger.info(f"wake: next due {value} ({', '.join(sorted(why)) or 'nothing'})")
    else:
        _state["last"] = now - _MIN_GAP_S + _RETRY_S     # back off a couple of minutes, stay dirty
    return ok


def _reset_for_tests() -> None:
    _state.update(dirty=True, sent=_UNSET, last=0.0, checked=0.0, why={})
