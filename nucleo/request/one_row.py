"""nucleo/request/one_row.py — ONE row per intent: a new call of the same leaving act replaces the row that waited.

The fourth piece of `nucleo/request/send_task` (V2-887 step 7). An intention is the card, the act AND the person: a
send to somebody else is another intention, with a row of its own (`people`)."""
from __future__ import annotations

from nucleo.request import base, note


def people(uid: str) -> set[str]:
    """The folded words of whom the send on row `uid` is about: the value of its person slot, the candidates its
    question offered and the word of his sentences that names people of his. Empty while it names nobody — only two
    rows that both name somebody and share no word are about DIFFERENT people (identity of names, never phrasing)."""
    from nucleo.acts.message_names import TOK, fold
    from nucleo.circuit import asker
    from nucleo.request import send_task, send_task_words
    art = send_task.artefact(uid)
    held = [str((art.get("payload") or {}).get(str(d.get("key") or s)) or "")
            for s, d in (art.get("slots") or {}).items() if d.get("rule") == "his_words"]
    held += (asker.artefact(uid).get("retained") or {}).get("candidates") or []
    held.append(send_task_words.his_word_for_people(" ".join(art.get("heard") or []))[0])
    return set(TOK.findall(fold(" ".join(map(str, held)))))


def superseded(uid: str, wid: str, action: str, *, emit=None) -> list[str]:
    """ONE row per intent (V2-887 step 7): a new send row ends every row of that act, about the same person, still
    WAITING for his answer — his new order is the task now, never a second one beside the first. Measured 2026-11-11:
    four rows for one message (each rephrasing opened another), and the engine then asked «which of these tasks is your
    answer?». A call that ANSWERS the waiting row never reaches here (`send_task_answer.take_call` fills that row first)."""
    ended = []
    try:
        from nucleo import circuit
        from nucleo.cli import worker_api
        mine = people(uid)
        for a in worker_api.open_asks():
            old = str(a.get("task_id") or "")
            art = __import__("nucleo.request.send_task", fromlist=["x"]).artefact(old) if old and old != uid else {}
            if base(art.get("widget")) == base(wid) and str(art.get("action")) == str(action) and (
                    not (mine and (theirs := people(old))) or mine & theirs):
                circuit.settle(row=old, state="cancelled", outcome=f"superseded by {uid}")
                ended.append(old)
    except Exception as e:  # noqa: BLE001
        note(e)
    if ended:
        from nucleo.request.send_task import _emit
        _emit(emit, "🔁 send task: his new order replaces the one that waited", f"{wid}:{action}",
              {"cat": "flash", "task_id": uid, "superseded": ended})
    return ended
