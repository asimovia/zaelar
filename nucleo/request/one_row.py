"""nucleo/request/one_row.py — ONE row per intent: a new call of the same leaving act replaces the row that waited.

The fourth piece of `nucleo/request/send_task` (V2-887 step 7)."""
from __future__ import annotations

from nucleo.request import base, note


def superseded(uid: str, wid: str, action: str, *, emit=None) -> list[str]:
    """ONE row per intent (V2-887 step 7): a new call of the same act ends every row of that act still WAITING for his
    answer — his new order is the task now, never a second one beside the first. Measured 2026-11-11: four rows for
    one message (each rephrasing opened another), and the engine then asked «which of these tasks is your answer?».
    A call that ANSWERS the waiting row never reaches here (`send_task_answer.take_call` fills that row first)."""
    ended = []
    try:
        from nucleo import circuit
        from nucleo.cli import worker_api
        for a in worker_api.open_asks():
            old = str(a.get("task_id") or "")
            art = __import__("nucleo.request.send_task", fromlist=["x"]).artefact(old) if old and old != uid else {}
            if base(art.get("widget")) == base(wid) and str(art.get("action")) == str(action):
                circuit.settle(row=old, state="cancelled", outcome=f"superseded by {uid}")
                ended.append(old)
    except Exception as e:  # noqa: BLE001
        note(e)
    if ended:
        from nucleo.request.send_task import _emit
        _emit(emit, "🔁 send task: his new order replaces the one that waited", f"{wid}:{action}",
              {"cat": "flash", "task_id": uid, "superseded": ended})
    return ended
