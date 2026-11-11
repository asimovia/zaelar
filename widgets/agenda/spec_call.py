"""widgets/agenda/spec_call.py — the end state an agenda call owes, as the card STORES it (V2-886 fila 5).

`nucleo.circuit.spec.render` asks every card's data module for `spec_call(action, payload)` before it fills the
action's `done_when`. Here: the dates and hours a call carries in his words («jueves», «a las 8 de la tarde») are
resolved by the same resolvers the act uses, so the clause compares like with like; and an `update_meeting` that
carries a WHEN owes the end state of the move that `data.apply_action` hands it to (V2-770). Measured 2026-11-11 in a
scratch store: a move to «jueves» landed on the right day and the spec `date=jueves` judged it unmet; the circuit then
said «could not be completed» over a move that had happened.
"""
from __future__ import annotations

from . import edit
from .when import _resolve_date, _resolve_time

def spec_call(action: str, payload: dict) -> tuple[str, dict]:
    p = dict(payload or {})
    if action == "update_meeting" and any(str(p.get(k) or "").strip() for k in edit.TIME_KEYS):
        action = "move_meeting"
    for k in ("startTime", "newTime", "endTime", "newEndTime"):     # the act's own fields
        if isinstance(p.get(k), str) and p[k].strip():
            p[k] = _resolve_time(p[k])
    at = str(p.get("newTime") or p.get("startTime") or "")
    for k in ("date", "newDate"):
        if isinstance(p.get(k), str) and p[k].strip():
            p[k] = _resolve_date(p[k], at=at)
    return action, p
