"""nucleo/request/stop_row.py — a stop told by the ROW, never by the model's account of it (V2-852 T03/T04/T05).

Three facts of one stop, beside the verdict that decides it (`stop.py`): which thing it stops (a STEP parked on his OK is
not its task: `parked_step`, `decline_step`), what the turn may say about it (only what its door did: `in_play`,
`say_the_row`), and why the row ended (his words of the stopping turn on the record: `stopped_by_his_turn`).
"""
from __future__ import annotations

import re as _re

from loguru import logger


DECLINE_STEP = "decline_step"
STEP_CHOICE = "he refuses or cancels only the STEP the task is waiting for his OK on; the task itself goes on"

#: Offered only while a step of a running task is parked on his OK (`parked_step`): with none, it names nothing.
_STEP_INSTRUCTIONS = ("Answer 'decline_step' when what he refuses, cancels or closes is that STEP and not the task: the "
                      "task goes on without it.")


def parked_step() -> dict | None:
    """V2-852 T03 — a STEP of a running task waiting for his OK: `{"step", "question", "task", "uid"}`, or None.

    One identity per task: a worker drives tools whose own registries number their steps (a browser tab is «2»). A
    stop said while such a step waits may be about the step — the question then offers that reading, and the stop
    of a step declines the step, never the row (`repair`). Only a step a LIVE row owns counts: a tab he drives
    himself is his own task. Never raises."""
    try:
        from widgets.navegador import tasks as _nav
        step = _nav.waiting_id()
        q = str(((_nav.get(step) or {}).get("question") or "")).strip() if step else ""
        if not q:
            return None
        row = _nav.row_of(step)
        return {"step": step, "question": q, "task": row["title"], "uid": row["uid"]} if row.get("uid") else None
    except Exception as e:  # noqa: BLE001
        return logger.debug(f"stop_decision: parked step unreadable: {e!r}") or None


def decline_step(step: dict, acted: dict | None = None) -> bool:
    """The stop of a STEP: its question is answered NO and the row runs on. True when the answer reached it."""
    try:
        from widgets.navegador import tasks as _nav
        _nav.answer(str(step["step"]), "no")
        if acted is not None:
            acted["declined_step"] = str(step["step"])
        return True
    except Exception as e:  # noqa: BLE001
        return logger.debug(f"stop_decision: the step could not be declined: {e!r}") or False


# ── V2-852 T05 · an ending carries its cause, so «why did it end» is read, never recalled ──────────────────
def stopped_by_his_turn(tids, words: str | None = None) -> None:
    """The stop door records WHO ended these errands: his words of the turn running now (`words`, else `model.heard`),
    on each record's outcome — the row's `outcome` when it settles, the line `ledger.recent` gives the prompt.

    Measured in session c8a307fd: the search row read «CANCELADA · hace 8 min» and nothing else, so asked what
    happened the model invented the cause («I closed it when you said "No"»); it had been cancelled by «yes, close
    task 2», another utterance minutes earlier. An outcome already written (his pick, a failure's reason) is kept. A
    stop with no turn of his (a reset, a button, a cron) writes nothing here: its own door names its cause."""
    try:
        from nucleo import dispatch
        from nucleo.request import model as _model
        words = " ".join(str(_model.heard() if words is None else words).split())[:200]
        if not words:
            return
        from i18n import langs
        line = str(langs.current_language().errand_stopped_by or "").format(words=words)
        for t in tids or ():
            r = dispatch.get_record(t)
            if r is not None and line and not str(getattr(r, "result_summary", "") or "").strip():
                r.result_summary = line
    except Exception as e:  # noqa: BLE001 — a cause that cannot be written never blocks the stop
        logger.debug(f"stop_decision: the stop's cause not recorded: {e!r}")


# ── V2-852 T03 · a stop names ROWS: «task N» and a title resolve against the rows, never a worker's number ─────
_NUMBER = _re.compile(r"(?<![\w-])(\d{1,4})(?![\w-])")

