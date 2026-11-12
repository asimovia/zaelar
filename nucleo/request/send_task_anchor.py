"""nucleo/request/send_task_anchor.py — a second question about the same send is asked on the row that WAITS.

THE CLASS (group A6, 2026-11-12; the multi-turn bench, `cual-*` 3/6, two Raquels in the directory). Turn 1: «mándale un
whatsapp a Raquel diciendo que llego tarde» → the model asked «¿a cuál Raquel?» and the question was made durable on
a send row (`ask_outside_door.held` → `send_task_words.hold`). Turn 2: «A Raquel Jofre» → the model asked AGAIN in
prose («¿qué le digo?») and the close opened a SECOND row for the same send: two questions waited, his next words fit
both, the binding read `several` and the engine asked «which task is your answer for?» — nothing left.

ONE row per intention (V2-887 step 7 said it of a new CALL, `one_row.superseded`; this says it of a new QUESTION): a
prose question about a card whose send already waits on its row is that row's question — unless his words name
SOMEBODY ELSE than the row is about (`one_row.people`): that is another send, and it opens its own row. His words of this turn fill
what they resolve by IDENTITY — the one declared candidate they name (the same reading as `inline_ask._named`), never
a reading of phrasing — and the question is asked for the slot that still lacks, on THAT row; when nothing lacks the
question was the model's, not the task's, and the task runs. Never a second row.
"""
from __future__ import annotations

from nucleo.request import base, note


def _waiting_sends(wid: str) -> list[tuple[str, dict]]:
    """`(row, ask artefact)` of this card's send tasks still waiting for his answer, newest first."""
    from nucleo.circuit import asker
    from nucleo.cli import worker_api
    from nucleo.request.send_task import KIND
    out = []
    for a in worker_api.open_asks():
        art = asker.artefact(str(a.get("task_id") or ""))
        ret = art.get("retained") or {}
        if art.get("inline") and ret.get("kind") == KIND and base(ret.get("widget")) == base(wid):
            out.append((str(a["task_id"]), art))
    return sorted(out, key=lambda x: -float(x[1].get("created") or 0))


def to_waiting(wid: str, said: str, question: str, *, emit=None) -> str:
    """Anchor the turn's prose question about `wid`'s send to the send row that already waits: the `ask_id` of the
    question now on that row ("" when no send of this card waits — the caller opens the row as before)."""
    try:
        from nucleo.acts.message_names import fold
        from nucleo.request import one_row, send_task, send_task_words
        from nucleo.turn import brief as _tb, verdicts
        word, people = send_task_words.his_word_for_people(said)
        order = verdicts.to_act(_tb.of_this_turn(), _tb.REQUEST_KEY, "")[0] == "order"
        # a send to SOMEBODY ELSE never lands on this row: his word names other people, or nobody of his in a sure NEW order
        rows = [r for r in _waiting_sends(wid) if not ((held := one_row.people(r[0])) and (word not in held if word else order))]
        if not rows:
            return ""
        named = str(people[0].get("name") or "") if word and len(people) == 1 else ""
        uid, ask = next(((u, a) for u, a in rows
                         if named and fold(named) in {fold(c) for c in (a.get("retained") or {}).get("candidates") or []}),
                        rows[0])
        art = send_task.artefact(uid)
        filled = ""
        ret = ask.get("retained") or {}
        if named and fold(named) in {fold(c) for c in ret.get("candidates") or []} and ret.get("slot"):
            key = str(ret["slot"])
            slot_name = str(ret.get("slot_name") or "recipient")
            art.setdefault("payload", {})[key] = named
            art.setdefault("slots", {}).setdefault(slot_name, {"key": key, "rule": "his_words"})["source"] = send_task.HIS
            art.setdefault("heard", []).append(" ".join(str(said or "").split()))
            send_task._keep(uid, art)
            send_task._end_state(uid, str(art.get("widget") or ""), str(art.get("action") or ""),
                                 art.get("payload") or {}, send_task._words_of(uid))
            from nucleo import his_words
            his_words.note(named)
            filled = key
        slot, key = send_task.missing(art)
        if slot:
            # the slot still lacking is the one the row already asked about: its declared candidates stay the answers
            cands = list(ret.get("candidates") or []) if str(ret.get("slot") or "") == key else []
            ask_id = send_task._question(uid, art, slot, key, question, cands)
        else:
            ask_id = uid
            send_task._schedule(uid)          # nothing lacks: the question was the model's, not the task's
        send_task._emit(emit, "📨 a second question about the same send is asked on its row", f"{wid} · {slot or 'runs'}",
                        {"cat": "flash", "task_id": uid, "filled": filled, "slot": slot, "ask_id": ask_id})
        return ask_id
    except Exception as e:  # noqa: BLE001 — unread: the caller opens the row as before
        note(e)
        return ""
