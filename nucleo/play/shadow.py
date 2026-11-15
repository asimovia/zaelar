"""nucleo/play/shadow.py — the programme recorded BESIDE the send path, changing nothing (stage `shadow`).

The send path reports what it really does — the task is commissioned, the exit door asks or refuses or lets it pass,
the card's door returns, the row ends — and each report is one event against the programme's table. The path is never
steered: a report the table refuses in the current step is a `play/drift` event, the evidence that the path did
something out of order. A line that claims an outcome while the programme has none is a drift too (`line`).

Every entry point is a no-op with the stage off and never raises: the shadow cannot fail a send.
"""
from __future__ import annotations

import functools
import time

from loguru import logger

from . import programme as _programme
from . import state as _st
from . import switch as _switch

SLOT = "play"            # the row artefact that holds the programme's state
KEEP = 64                # programmes held in memory; the row's artefact is the durable copy
_live: dict[str, dict] = {}


def _quiet(fn):
    @functools.wraps(fn)
    def inner(*a, **k):
        try:
            if _switch.stage("shadow"):
                return fn(*a, **k)
        except Exception as e:  # noqa: BLE001 — the shadow never fails the path it watches
            logger.debug(f"play/shadow: {fn.__name__} skipped — {e!r}")
        return None
    return inner


def _emit(label: str, state: dict, uid: str, **extra) -> None:
    from voice import observer
    observer.emit("play", label, text=f"{state.get('wid')}:{state.get('action')} · {state.get('step')}", role="system",
                  extra={"cat": "system", "task_id": uid, "step": state.get("step"), "outcome": state.get("outcome"),
                         **extra})


def _keep(uid: str, state: dict) -> None:
    _live[uid] = state
    while len(_live) > KEEP:
        _live.pop(next(iter(_live)))
    try:
        from nucleo.circuit import ledger
        ledger.store().artifact_put(uid, SLOT, state)
    except Exception as e:  # noqa: BLE001 — the copy in memory still serves this run
        logger.debug(f"play/shadow: state of {uid} not kept on its row — {e!r}")


def of(uid: str) -> dict | None:
    return _live.get(str(uid or ""))


def _feed(uid: str, event: str, *, slots: dict | None = None, legacy: str = "") -> bool:
    """One report of the path as one event of the table; refused → `play/drift`. True when the table took it."""
    state = of(uid)
    if state is None:
        return False
    m = _st.advance(state, event, now=time.monotonic(), slots=slots)
    _keep(uid, m.state)
    if m.ok:
        _emit("step", m.state, uid, event=event)
    else:
        _emit("drift", m.state, uid, event=event, legacy=legacy or event, why=m.why)
    return m.ok


def _slots(art: dict) -> dict:
    payload = art.get("payload") or {}
    return {str(slot): {"value": payload.get(str(d.get("key") or slot)), "source": str(d.get("source") or "unknown")}
            for slot, d in (art.get("slots") or {}).items() if isinstance(d, dict)}


@_quiet
def commissioned(uid: str, art: dict, missing: str = "") -> None:
    """The send task was born on its row with its slots; `missing` = the slot it asks him for, or ""."""
    wid, action = str(art.get("widget") or ""), str(art.get("action") or "")
    _arm()
    _keep(uid, _st.new(wid, action, _programme.of(wid, action), now=time.monotonic()))
    _feed(uid, "start")
    _feed(uid, "missing" if missing else "resolved", slots=_slots(art))


@_quiet
def door(uid: str, outcome: str, art: dict | None = None) -> None:
    """The exit door answered for this row: `asked` (it waits for his yes), `refused`, or `passed` (it runs now)."""
    state = of(uid)
    if state is None:
        return
    if state["step"] == "asking" and outcome != "refused":       # his answer filled the slot: the task goes on
        _feed(uid, "answer", slots=_slots(art or {}), legacy="door")
        _feed(uid, "resolved", slots=_slots(art or {}), legacy="door")
        state = of(uid)
    if outcome == "refused":
        _feed(uid, "fail" if state["step"] == "resolving" else "cancel", legacy="door.refused")
    elif outcome == "asked":
        if state["step"] != "confirming":                          # the door asks where the programme owed no question
            _emit("drift", state, uid, event="asked", legacy="door.asked",
                  why=f"the exit door asks in step {state['step']!r}")
    elif outcome == "passed" and state["step"] == "confirming":
        _feed(uid, "yes", legacy="door.passed")


@_quiet
def returned(uid: str, res) -> None:
    """The card's door returned: the executor's own answer."""
    ok = isinstance(res, dict) and res.get("ok") is not False and not res.get("error")
    if _feed(uid, "returned" if ok else "error", legacy="card.return") and ok:
        _feed(uid, "check")


@_quiet
def ended(uid: str, state_name: str, verdict: str = "") -> None:
    """The row moved into its ending (`circuit.settle`): what the look at the end state found."""
    state = of(uid)
    if state is None or state["step"] in _st.ENDS or state["step"] == _st.LAST:
        return
    v = str(verdict or "").lower()
    if state_name == "cancelled":
        event = "cancel"
    elif v == "met" or (not v and state_name == "done"):
        event = "landed"
    elif v == "unverifiable":
        event = "unreadable"
    else:
        event = "absent"
    if _feed(uid, event, legacy=f"settle.{v or state_name}") and event == "absent" and of(uid)["step"] == "verifying":
        _feed(uid, "absent", legacy=f"settle.{v or state_name}")      # an ending is final: no second look follows it


@_quiet
def line(wid: str, action: str, verdict: str) -> None:
    """A line of the turn claims an outcome (`verdict`) for an act of this card. With a live programme of that act
    that has no outcome yet, the claim came before the end: a drift."""
    from nucleo.request import base
    for uid in reversed(list(_live)):
        state = _live[uid]
        if base(state["wid"]) == base(wid) and state["action"] == str(action) and state["step"] != _st.LAST:
            if not _st.say(state, "report", str(verdict)).ok:
                _emit("drift", state, uid, event="say:report", legacy=f"line.{verdict}",
                      why=f"an outcome is claimed in step {state['step']!r}")
            return


def _on_bus(ev: dict) -> None:
    if not isinstance(ev, dict) or ev.get("topic") != "task.ended":
        return
    p = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
    uid = str(p.get("task_id") or "")
    if uid not in _live:
        return
    verdict = ""
    try:
        from nucleo.circuit import ledger
        verdict = str((ledger.get(uid) or {}).get("verdict") or "")
    except Exception as e:  # noqa: BLE001 — the row's state alone still names the ending
        logger.debug(f"play/shadow: verdict of {uid} unread — {e!r}")
    ended(uid, str(p.get("state") or ""), verdict)


def _arm() -> None:
    """Listen to `task.ended` once; a sink does not survive `bus.reset()`, so a commission after one arms it again."""
    import bus
    bus.add_sink(_on_bus)          # idempotent
