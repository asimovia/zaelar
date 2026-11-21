"""The steps of a send, as declared data (`steps.json`), read over its draft's own fields (C2 P3): a step is done when
its field holds — an attribute, `a.b` for a field inside one, `state=x` for a state. No label and no word is read."""
from __future__ import annotations

import json
from pathlib import Path

_STEPS = json.loads((Path(__file__).with_name("steps.json")).read_text(encoding="utf-8"))["steps"]


def _holds(d, cond: str) -> bool:
    if "=" in cond:
        field, _, want = cond.partition("=")
        return str(getattr(d, field.strip(), "") or "") == want.strip()
    v = d
    for part in cond.split("."):
        v = v.get(part) if isinstance(v, dict) else getattr(v, part, None)
    return bool(v)


def plan(d) -> list[dict]:
    """`[{id, what, done, skipped}]` for this draft, in order."""
    out = []
    for s in _STEPS:
        skipped = bool(s.get("skipped_when")) and _holds(d, s["skipped_when"]) and not _holds(d, s["done_when"])
        out.append({"id": s["id"], "what": s["what"], "done": _holds(d, s["done_when"]), "skipped": skipped})
    return out


# ── the send, seen as a playbook in its order's flow (the shape of a worker's `task` events, `runner: send`) ────────
#: the owner's steps that end a send — its receipt read, or nothing to wait for
#: `ok` is said only of what it is: True sent (or held to leave later), False only a send that FAILED; «unconfirmed» says
#: nothing — no receipt is no failure (a failed task is counted, `observability/flows.FAILED_TASK_WHERE`)
ENDS = {"sent": True, "failed": False, "unconfirmed": None, "held for later": True}
_started: set = set()


def _task(label: str, d, text: str = "", **more) -> None:
    from voice.observer import emit
    p = plan(d)
    emit("task", label, text=(text or d.said or d.text)[:160], role="system",
         extra={"id": f"send:{d.id}", "done": sum(1 for s in p if s["done"] or s["skipped"]), "total": len(p),
                "plan": [{"id": s["id"], "what": s["what"], "done": s["done"], "skipped": s["skipped"]} for s in p],
                "trace": d.trace, "span": f"send:{d.id}", "runner": "send", **more})


def report(label: str, d) -> None:
    """Each step the owner emits moves its card: `start` and `plan` once, `progress` every time, `end` at its end."""
    try:
        if d.id not in _started:
            _started.add(d.id)
            _task("start", d)
            _task("plan", d, " · ".join(s["what"] for s in plan(d)))
        _task("progress", d, label)
        if label in ENDS:
            _end(d, ENDS[label], label)
    except Exception as e:  # noqa: BLE001 — the record never decides the send
        __import__("loguru").logger.debug(f"send.steps: not reported ({e!r})")


def _end(d, ok: bool | None, outcome: str) -> None:
    if d.id in _started:
        _started.discard(d.id)
        _task("end", d, outcome=outcome, **({} if ok is None else {"ok": ok}))


def ended(d, state: str) -> None:
    """A draft ended with nothing left to wait for (all but SENT, whose end is its receipt): its card ends — failed only
    when it FAILED; dropped, idle or replaced is an ending he chose or let be, never a failed task."""
    from nucleo.send import draft
    if state != draft.SENT:
        from voice import trace
        with trace.scope(d.trace or trace.current()):
            _end(d, state != draft.FAILED, state)
