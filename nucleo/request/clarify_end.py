"""A clarification ends with its conversation (V2-886 D1, second half): answered, moved on, or expired.

A clarify (`asker.KIND_CLARIFY` — a fact or a choice the work needs) is dialogue, never a card, and it never outlives
the conversation that asked it. Answered, its row goes on (`worker_api.answer`). Moved on — his turn surely answers
none of the waiting questions (the binding verdict `none` at VETO) while a clarify asked him in our last reply, by its
id (`circuit.asked_last`), never by its words — it closes now. Expired — no answer within `clarify_wait_minutes` (a
rule, like `answer_wait_days` for the rest) — the pulse closes it. Every close is the row's cancel (a parked worker is
told) and ONE `ask_closed` event with its reason: nothing is said, and nothing asks it again.
"""
from __future__ import annotations

import time

from nucleo.request import note

EV = "ask_closed"
MOVED_ON, EXPIRED = "moved_on", "expired"
WAIT_KEY, WAIT_MINUTES = "clarify_wait_minutes", 30.0


def is_clarify(task_id: str) -> bool:
    from nucleo.circuit import asker
    return asker.kind_of(asker.artefact(str(task_id or ""))) == asker.KIND_CLARIFY


def close(task_id: str, ask_id: str, reason: str, emit=None) -> bool:
    """End the row that still waits on this clarify (its worker told), and say so in ONE event. True when closed."""
    try:
        from nucleo.circuit import asker
        from nucleo.dispatch import control
        if not asker.row_waits(str(task_id), str(ask_id)):
            return False
        control.cancel_row(str(task_id), outcome=f"the clarification closed: {reason}")
        if emit is None:
            from voice.observer import emit
        emit("task", "🧹 clarification closed with its conversation", role="system", text=reason,
             extra={"kind_diag": EV, "task_id": str(task_id), "ask_id": str(ask_id), "reason": reason})
        return True
    except Exception as e:  # noqa: BLE001 — a close that failed leaves the wait to its own deadline
        note(e)
        return False


def moved_on(brief, emit=None) -> list[str]:
    """His turn surely answers NONE of the waiting questions: every clarify that asked him in our last reply closes."""
    try:
        from nucleo.circuit import asked_last
        from nucleo.cli import worker_api, worker_api_bind as bind
        from nucleo.turn import verdicts
        choice, _info = verdicts.read(brief, bind.KEY, None, min_confidence=verdicts.VETO)
        if str(choice) != bind.NONE:
            return []
        return [a["ask_id"] for a in worker_api.open_asks() if asked_last.asked_since(a) and is_clarify(a["task_id"])
                and close(a["task_id"], a["ask_id"], MOVED_ON, emit)]
    except Exception as e:  # noqa: BLE001
        note(e)
        return []


def wait_s(now: float | None = None) -> float:
    try:
        import rules
        minutes = float(rules.value([(0, rules.GLOBAL)], WAIT_KEY, WAIT_MINUTES, now=now))
    except Exception as e:  # noqa: BLE001 — an unreadable rule keeps the default
        note(e)
        minutes = WAIT_MINUTES
    return max(0.0, minutes) * 60.0


def expired(now: float | None = None) -> list[str]:
    """The pulse's sweep: a clarify unanswered past `wait_s` closes (its event, no line)."""
    now = time.time() if now is None else now
    try:
        from nucleo.circuit import ledger
        period, out = wait_s(now), []
        for row in ledger.store().tasks_where(states=("waiting",), visible_only=False, limit=500):
            since = int(row.get("waiting_since") or 0)
            if (row.get("waiting_for") == ledger.USER_ANSWER and since and now >= since + period
                    and is_clarify(row["id"]) and close(row["id"], str(row.get("ask_id") or ""), EXPIRED)):
                out.append(str(row["id"]))
        return out
    except Exception as e:  # noqa: BLE001
        note(e)
        return []
