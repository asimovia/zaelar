"""Who opened the turns of a session switched on — the proof that the manager is the one owner (V2-941, the F1 plan
§6 and §8). Per session, counters the old path's doors and the manager's telemetry add to:

  manager_runs          runs the manager started                              (the manager's `conv_run/started`)
  livekit_turns         requests to the old turn stream                       (its door, in a switched session)
  legacy_prompts        prompts of the old turn with this session's trace     (its door, in a switched session)
  commit_user_turn      calls to the speech session's own turn commit         (the voice adapter)
  effects_outside_read  anything but a read the manager's gateway let through (its `conv_effect` events)
  held_dispatch_attempts outside writes the hold stopped                      (the exit's own counter, by session)
  legacy_turn_attempts  a line that reached the old turn's reply in a switched session (the net, B5)
  legacy_jev_calls      the old turn's brief (a Jev call) asked while the manager held the voice (`switch.legacy_call`)

The exit gate: `manager_runs > 0` and every one that would mean another owner (`MUST_BE_ZERO`) at 0. `GET
/api/debug/conversation/<session>` answers with `report(session)`; it reads only.
"""
from __future__ import annotations

import threading

from nucleo.conversation_host.declared import declared

COUNTERS = tuple(declared()["proof"]["counters"])           # declared data (`declared.json`)
#: the gateway's labels for an effect that got past it: reserved, or sent (a read is `read`; a refusal, `refused`)
REACHED_OUT = ("claimed", "submitted")
MUST_BE_ZERO = tuple(declared()["proof"]["must_be_zero"])

_lock = threading.Lock()
_by_session: dict[str, dict[str, int]] = {}


def note(session: str, counter: str, n: int = 1) -> None:
    if counter not in COUNTERS:
        raise ValueError(f"{counter} is not a counter of the proof")
    with _lock:
        row = _by_session.setdefault(session, dict.fromkeys(COUNTERS, 0))
        row[counter] += n


def report(session: str) -> dict:
    with _lock:
        row = dict(_by_session.get(session) or dict.fromkeys(COUNTERS, 0))
    fails = [f"{k} = {row[k]}" for k in MUST_BE_ZERO if row[k]]
    if not row["manager_runs"]:
        fails.insert(0, "manager_runs = 0")
    return {"session": session, "on": session in _by_session, "counters": row, "passes": not fails, "fails": fails}


class Counting:
    """The `Telemetry` port of a switched session: every event goes on to `inner`, and the ones the proof reads are
    counted — a run the manager started, and any effect its gateway let through that is not a read."""

    def __init__(self, inner, session: str) -> None:
        self._inner, self._session = inner, session

    def emit(self, kind: str, label: str, body: dict) -> None:
        if kind == "conv_run" and label == "started":
            note(self._session, "manager_runs")
        elif kind == "conv_effect" and label in REACHED_OUT:
            note(self._session, "effects_outside_read")
        self._inner.emit(kind, label, body)


def forget(session: str) -> None:
    with _lock:
        _by_session.pop(session, None)


def _reset_for_tests() -> None:
    with _lock:
        _by_session.clear()
