"""Pending work resumes from its own row, never from a glued utterance or a blind restart (V2-799).

What is pending is a set of durable rows (`nucleo/pending_work.py`); the model chooses among them by their ids
(`resume_task` in the conversation host, `acts_tasks._resume`). Each row resumes from itself:

  · a widget row (a draft held for his word) through its own declared action, so through its own confirm gate —
    when the caller hands the door that applies it (`apply_widget_data`);
  · an errand row from its own brief, sheet and outcome (`pending_work.errand_brief`, `task_uid` → the same row and
    the same sheet, CRIT-E16);
  · a live errand is not started twice: it is already running, or already waiting on his answer.
"""
from __future__ import annotations

from loguru import logger


def resume(rows, *, operator_text: str, apply_widget_data=None, emit=None) -> list[str]:
    """Resume each row from itself. Returns the ids resumed (live errands included: they need nothing started)."""
    done: list[str] = []
    for row in rows or []:
        try:
            if row.get("source") == "widget":
                if not callable(apply_widget_data):
                    continue
                r = row.get("resume") or {}
                apply_widget_data(row["widget"], str(r.get("action") or ""), dict(r.get("payload") or {}))
            elif str(row.get("state") or "") in ("pending", "running", "waiting"):
                pass                                  # alive: its worker already has it, or waits on his answer
            else:
                from nucleo import pending_work
                from nucleo.acts import errand as _esc
                _esc.escalate_to_slowbrain(pending_work.errand_brief(row, operator_text), context={
                    "src": "resume", "kind": str(row.get("kind") or "generic"), "task_uid": row["id"],
                    "sheet": str(row.get("sheet") or ""), "surface": str(row.get("surface") or "")})
            done.append(str(row["id"]))
            if callable(emit):
                emit("brain", "↩️ retomo lo pendiente desde su fila", text=f"{row.get('title')} · {row.get('state')}",
                     role="system", extra={"cat": "flash", "id": row["id"], "source": row.get("source")})
        except Exception as e:  # noqa: BLE001
            logger.warning(f"resume: could not resume {row.get('id')}: {e}")
    return done
