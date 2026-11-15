"""nucleo/play/state.py — the state of one programme and its only writer, `advance`.

The state is a plain dict, so it can live on the request's row:

    {step, outcome, wid, action, programme: {confirm, leaves, verify}, slots: {name: {value, source}},
     said: {kind: [value, …]}, tries, at, refused}

`advance(state, event, now=…)` returns a `Move`: the NEW state when the table allows the event in the current step,
the SAME state and the reason when it does not. Nothing else writes `step`.
"""
from __future__ import annotations

import copy
import json
import pathlib
from typing import NamedTuple

from loguru import logger

_TABLE = json.loads((pathlib.Path(__file__).with_name("table.json")).read_text(encoding="utf-8"))
MOVES: dict = _TABLE["moves"]
STEPS: tuple = tuple(MOVES)
FIRST: str = _TABLE["first"]
ENDS: frozenset = frozenset(_TABLE["ends"])
LAST: str = _TABLE["last"]
EVENTS: frozenset = frozenset(e for moves in MOVES.values() for e in moves)


class Move(NamedTuple):
    state: dict
    ok: bool
    why: str = ""


def new(wid: str, action: str, programme: dict | None = None, *, now: float = 0.0) -> dict:
    """A programme at its first step. `programme` is `programme.of(wid, action)`; absent, the strictest one."""
    prog = dict(programme or {"confirm": True, "leaves": True, "verify": "check"})
    return {"step": FIRST, "outcome": "", "wid": str(wid), "action": str(action), "programme": prog, "slots": {},
            "said": {}, "tries": 0, "at": float(now), "refused": 0}


def needs_consent(state: dict) -> bool:
    """Does this programme ask before it executes? When its action declares it, or when it leaves the machine with a
    slot the agent chose (`asks_consent`: a source that is not his words, his reading, the row he saw or the card)."""
    prog = state.get("programme") or {}
    if prog.get("confirm"):
        return True
    if not prog.get("leaves"):
        return False
    return any(str((s or {}).get("source") or "unknown") in _TABLE["asks_consent"]
               for s in (state.get("slots") or {}).values())


def _refuse(state: dict, event: str, why: str) -> Move:
    logger.debug(f"play/refused {state.get('wid')}:{state.get('action')} step={state.get('step')} "
                 f"event={event} — {why}")
    kept = dict(state)
    kept["refused"] = int(state.get("refused") or 0) + 1
    return Move(kept, False, why)


def advance(state: dict, event: str, *, now: float = 0.0, slots: dict | None = None) -> Move:
    """One event against the table. `slots` ({name: {value, source}}) are merged on a legal move only."""
    step = str(state.get("step") or "")
    target = (MOVES.get(step) or {}).get(str(event))
    if target is None:
        return _refuse(state, event, f"{event!r} is not an event of step {step!r}")
    out = copy.deepcopy(state)
    if slots:
        out["slots"].update({str(k): dict(v) for k, v in slots.items() if isinstance(v, dict)})
    retry = _TABLE["retries"].get(step) or {}
    if retry.get("event") == event and int(out.get("tries") or 0) < int(retry.get("times") or 0):
        out["tries"] = int(out.get("tries") or 0) + 1      # one more look at the end state, same step
        out["at"] = float(now)
        return Move(out, True)
    if target in _TABLE["passes"] and not needs_consent(out):
        target = _TABLE["passes"][target]                  # nothing to ask: straight to the next step
    if target != step:
        out["tries"] = 0
    out["step"], out["at"] = target, float(now)
    if target in ENDS:
        out["outcome"] = target
    return Move(out, True)


def due(state: dict, now: float) -> str:
    """`"timeout"` when the current step has outlived its deadline, else "". A step with no deadline never is."""
    limit = _TABLE["deadline_s"].get(str(state.get("step") or ""))
    if limit is None:
        return ""
    return "timeout" if float(now) - float(state.get("at") or 0.0) >= float(limit) else ""


def say(state: dict, kind: str, value: str = "", *, now: float = 0.0) -> Move:
    """May this line be spoken now? Each kind belongs to its steps (`says`) and is said once per value. A `report`
    exists only when the outcome does, and saying it is the programme's last move."""
    step = str(state.get("step") or "")
    if step not in (_TABLE["says"].get(str(kind)) or ()):
        return _refuse(state, f"say:{kind}", f"a {kind!r} line is not said in step {step!r}")
    already = (state.get("said") or {}).get(str(kind)) or []
    if str(value) in already:
        return _refuse(state, f"say:{kind}", f"{kind!r} was already said for {value!r}")
    if kind == "report":
        moved = advance(state, "report", now=now)
        out = moved.state
    else:
        out = copy.deepcopy(state)
    out.setdefault("said", {}).setdefault(str(kind), []).append(str(value))
    return Move(out, True)
