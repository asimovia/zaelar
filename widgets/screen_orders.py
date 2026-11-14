"""widgets/screen_orders.py — the ledger of canvas orders and the screens' answers to them (V2-907 §3.2).

An order to the canvas (show, close, minimise…) is not done because it was emitted: it is done when the screens it
was sent to SAY so. Here each order gets a `seq` and waits for its screens:

  · `issue(op, cid, targets)` — the order door (`nucleo/acts/canvas.apply`) records `{seq, op, id, targets, born}`
    and stamps `seq` on the event. `targets` are the screens that must answer.
  · `ack(dev, acks)` — the screen's report door hands over the `{seq, ok, why}` its report carries. Only a target
    answers for itself; a second answer of the same screen changes nothing; `why` is a closed set (`WHY`).
  · `outcome(seq, wait_s)` — `confirmed` (every target answered and one of them did it) · `noop:<why>` (every target
    answered and none had anything to do: `not_open`, `already_front`, …) · `refused` · `pending` (a target has not
    answered yet, inside `PENDING_S`) · `unconfirmed` (a target never answered within `PENDING_S`, or nobody was there
    to answer) · `unknown` (no such order). `wait_s` is how long the caller may block for the answers.
  · `pending(dev)` — the orders a screen has not answered yet, still inside the window.

The window is V2-884's ack clock (`state_render.PENDING_S`): one clock for «did the app confirm» and «did the screen
confirm». Process memory, bounded (`KEEP`, `KEEP_S`): a restart forgets every order, and an order nobody can find is
`unknown`, never confirmed.
"""
from __future__ import annotations

import threading
import time

from loguru import logger

from widgets.state_render import PENDING_S

#: The answers a screen may give, and whether each one means the order changed the screen.
WHY = {"done": True, "not_open": False, "already_front": False, "already_closed": False, "elsewhere": False,
       "refused": False}
KEEP = 512
KEEP_S = 600.0

_COND = threading.Condition()
_ORDERS: dict[int, dict] = {}
_SEQ = {"n": 0}


def issue(op, cid, targets) -> int:
    """Record an order to the canvas and return its `seq` (process-monotonic)."""
    devs = tuple(dict.fromkeys(str(t) for t in (targets or ()) if t))
    now = time.time()
    with _COND:
        _SEQ["n"] += 1
        seq = _SEQ["n"]
        _ORDERS[seq] = {"seq": seq, "op": str(op or ""), "id": str(cid or ""), "targets": devs, "born": now,
                        "acks": {}}
        if len(_ORDERS) > KEEP or (_ORDERS and now - _ORDERS[min(_ORDERS)]["born"] > KEEP_S):
            for old in [s for s, o in _ORDERS.items() if now - o["born"] > KEEP_S or s <= seq - KEEP]:
                _ORDERS.pop(old, None)
    return seq


def ack(dev, acks) -> int:
    """Take screen `dev`'s answers; returns how many were new and taken (a non-target, a repeat or a malformed
    answer is dropped and logged)."""
    dev = str(dev or "")
    taken = 0
    with _COND:
        for a in acks if isinstance(acks, list) else []:
            seq = a.get("seq") if isinstance(a, dict) else None
            o = _ORDERS.get(seq) if isinstance(seq, int) and not isinstance(seq, bool) else None
            why = a.get("why") if isinstance(a, dict) else None
            why = why if why in WHY else ("done" if isinstance(a, dict) and a.get("ok") is True else "refused")
            if o is None or dev not in o["targets"] or dev in o["acks"]:
                logger.debug(f"screen_orders: answer from {dev} to {seq!r} dropped")
                continue
            o["acks"][dev] = why
            taken += 1
        if taken:
            _COND.notify_all()
    return taken


def _resolved(o: dict, now: float) -> str:
    answers = o["acks"]
    if not o["targets"]:
        return "unconfirmed"
    if len(answers) < len(o["targets"]):
        return "pending" if now - o["born"] < PENDING_S else "unconfirmed"
    whys = list(answers.values())
    if "refused" in whys:
        return "refused"
    if any(WHY[w] for w in whys):
        return "confirmed"
    return f"noop:{whys[0]}"


def outcome(seq, wait_s: float = 0.0) -> str:
    """What became of order `seq`, waiting at most `wait_s` seconds for its screens' answers."""
    deadline = time.time() + max(0.0, float(wait_s or 0.0))
    with _COND:
        while True:
            o = _ORDERS.get(seq)
            if o is None:
                return "unknown"
            now = time.time()
            got = _resolved(o, now)
            if got != "pending" or now >= deadline:
                return got
            _COND.wait(min(deadline, o["born"] + PENDING_S) - now)


def pending(dev) -> list[dict]:
    """The orders screen `dev` has not answered yet, inside the window: `[{seq, op, id, age}]`, oldest first."""
    dev, now = str(dev or ""), time.time()
    with _COND:
        return [{"seq": o["seq"], "op": o["op"], "id": o["id"], "age": round(now - o["born"], 2)}
                for o in sorted(_ORDERS.values(), key=lambda o: o["seq"])
                if dev in o["targets"] and dev not in o["acks"] and now - o["born"] < PENDING_S]


def _reset_for_tests() -> None:
    with _COND:
        _ORDERS.clear()
        _SEQ["n"] = 0
