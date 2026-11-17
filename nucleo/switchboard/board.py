"""The ONE list of what is open: every process that runs and every row that waits on his answer.

Until now these lived in three worlds (live worker sessions, rows waiting on a question, parked errands) and each
reader saw one of them. A process here is keyed by its ROW (the durable identity); a live session adds its dispatch id.
"""
from __future__ import annotations

from loguru import logger

RUNNING, WAITING = "running", "waiting"


def _note(what: str, e: Exception) -> None:
    logger.debug(f"switchboard.board: {what} unread — {type(e).__name__}: {e}")


def open_processes() -> list[dict]:
    """`[{key, dispatch, title, state, question, ask_id, since}]`, oldest first. `key` is the row id; `dispatch` the
    live session's id ("" when the process ended after asking); `state` is `waiting` while a question of it is open.
    Never raises: an unreadable source is left out."""
    out: dict[str, dict] = {}
    try:
        from nucleo.cli import worker_api
        for a in worker_api.open_asks():
            key = str(a.get("task_id") or "")
            if key:
                out[key] = {"key": key, "dispatch": "", "title": str(a.get("title") or "")[:160], "state": WAITING,
                            "question": str(a.get("question") or "")[:300], "ask_id": str(a.get("ask_id") or ""),
                            "since": int(a.get("since") or 0)}
    except Exception as e:  # noqa: BLE001
        _note("waiting rows", e)
    try:
        from nucleo import dispatch as _d
        for s in _d.pending_summaries() or []:
            rec = _d.get_record(s.get("id"))
            key = str(getattr(rec, "uid", "") or "") or f"session:{s.get('id')}"
            title = str(s.get("heard") or s.get("request") or "")[:160]
            if key in out:
                out[key]["dispatch"] = str(s.get("id") or "")
                out[key]["title"] = out[key]["title"] or title
                continue
            out[key] = {"key": key, "dispatch": str(s.get("id") or ""), "title": title, "state": RUNNING,
                        "question": "", "ask_id": "", "since": 0, "phase": str(s.get("phase") or "")[:120]}
    except Exception as e:  # noqa: BLE001
        _note("live sessions", e)
    return sorted(out.values(), key=lambda p: (p["since"] or 0, p["key"]))


def line(n: int, p: dict) -> str:
    """One process as the decision reads it: its number, what he asked, its state and — when it waits — its question."""
    state = (f"WAITING for his answer to: «{p['question']}»" if p["state"] == WAITING
             else f"running{(' — ' + p['phase']) if p.get('phase') else ''}")
    return f"{n}. «{p['title'] or '(untitled)'}» — {state}"
