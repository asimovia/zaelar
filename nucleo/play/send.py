"""nucleo/play/send.py — the hands of a send, and its walk as the owner of the row (stage `own`).

With the stage on, a send task that may run is walked by the driver (`run.run`) instead of being scheduled on its own:

  · resolve — the slots the row retained, with where each came from (`send_task.artefact`);
  · execute — the task's one act, unchanged: the exit door, then the card's door (`send_task_run.run`). The door is
    still the one place that asks for his consent; when it asks, the walk parks on the row and his yes walks it on;
  · look    — the row's declared end state, read from the card's return (the send is only QUEUED then) for as long
    as the circuit owes it; when it is there the row is settled by the one writer (`circuit.settle`). When the
    circuit ends the row first, the walk ends `unverified` and says nothing: whoever settled it said its line;
  · say     — ONE report: the sent line, by the circuit's own out-of-turn mouth, only when the look found it. A
    failure is told by the card's failure path and an unconfirmed send by the circuit's; the walk repeats neither.

While a walk is live, no line of a turn may claim an outcome for it (`live`): the row has none yet.
"""
from __future__ import annotations

import asyncio
import time

from loguru import logger

from . import programme as _programme
from . import run as _run
from . import state as _st
from . import switch as _switch

KEEP = 64
LOOK_EVERY_S = 0.4
_walks: dict[str, dict] = {}        # uid → the programme's state
_running: set[str] = set()


def enabled() -> bool:
    return _switch.stage("own")


def _slots(art: dict) -> dict:
    payload = art.get("payload") or {}
    return {str(slot): {"value": payload.get(str(d.get("key") or slot)), "source": str(d.get("source") or "unknown")}
            for slot, d in (art.get("slots") or {}).items() if isinstance(d, dict)}


def _entry(uid: str) -> dict | None:
    """The row's end state still owed, as the card's door opened it."""
    from nucleo.circuit import spec
    return next((e for e in spec.open_specs() if str(e.get("row") or "") == uid), None)


class Hands:
    def __init__(self, uid: str):
        self.uid, self.entry, self.told = uid, None, False

    async def resolve(self, state):
        from nucleo.request import send_task
        art = send_task.artefact(self.uid)
        if not art or send_task.missing(art)[0]:
            return {"fail": "the row holds no act that may run"}
        return {"slots": _slots(art)}

    async def answer(self, state, slot):
        return None

    async def consent(self, state):
        return "yes"            # the exit door, inside `execute`, is the one that asks him

    async def execute(self, state):
        from nucleo.request import send_task_run
        res = await send_task_run.run(self.uid)
        if isinstance(res, dict) and res.get("asked"):
            return {"parked": True}
        return res

    async def look(self, state):
        from nucleo import circuit
        from nucleo.circuit import ledger, spec
        limit = float(_st._TABLE["deadline_s"]["verifying"]) - LOOK_EVERY_S
        t_end = time.monotonic() + limit
        while True:
            e = _entry(self.uid)
            if e is None:                                   # nothing owed any more: the row says how it ended
                row = ledger.get(self.uid) or {}
                self.told = True                            # whoever settled it said its line
                return True if str(row.get("verdict") or "") == "met" else None
            if spec.attest(e) is True:
                circuit.settle(e, verdict="met")
                self.entry = e
                return True
            if time.monotonic() >= t_end:
                return None                                 # not there yet: the circuit keeps the row
            await asyncio.sleep(LOOK_EVERY_S)

    def say(self, kind, value, state):
        if kind != "report" or value != "done" or self.told or self.entry is None:
            return
        from nucleo import circuit
        circuit._say_now(self.entry, "", fact=circuit.SENT, verdict="met")
        self.entry["reported"] = True


def _moved(uid: str):
    def on_move(event: str, state: dict) -> None:
        _walks[uid] = state
        try:
            from voice import observer
            observer.emit("play", "step", text=f"{state['wid']}:{state['action']} · {state['step']}", role="system",
                          extra={"cat": "system", "task_id": uid, "event": event, "step": state["step"],
                                 "outcome": state["outcome"], "own": True})
        except Exception as e:  # noqa: BLE001 — the trace never decides the walk
            logger.debug(f"play/send: step not emitted — {e!r}")
    return on_move


async def walk(uid: str) -> dict | None:
    """Walk the row's send from where it stands to its report (or to where it parks). One walk per row at a time."""
    if uid in _running:
        return None
    _running.add(uid)
    try:
        state = _walks.get(uid)
        if state is None or state["step"] in _st.ENDS or state["step"] == _st.LAST:
            from nucleo.request import send_task
            art = send_task.artefact(uid)
            wid, action = str(art.get("widget") or ""), str(art.get("action") or "")
            state = _st.new(wid, action, _programme.of(wid, action), now=time.monotonic())
        _walks[uid] = state
        while len(_walks) > KEEP:
            _walks.pop(next(iter(_walks)))
        _walks[uid] = await _run.run(state, Hands(uid), on_move=_moved(uid))
        return _walks[uid]
    except Exception as e:  # noqa: BLE001 — a walk that broke leaves the row to the circuit, which still ends it
        logger.warning(f"play/send: the walk of {uid} broke — {e!r}")
        _walks.pop(uid, None)
        return None
    finally:
        _running.discard(uid)


def start(uid: str) -> None:
    """Schedule the walk off the turn's stream (the mouth never waits for a connector)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(walk(uid))
        return
    task = loop.create_task(walk(uid))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


_tasks: set = set()


def live(wid: str, action: str) -> bool:
    """Is a walk of this card's act under way with no outcome yet? Then no line may claim one for it."""
    from nucleo.request import base
    now = time.monotonic()
    return any(base(s["wid"]) == base(wid) and s["action"] == str(action) and not s["outcome"]
               and not _st.due(s, now)            # a walk past its step's deadline protects nothing any more
               for s in _walks.values())
