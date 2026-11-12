"""nucleo/request/inline_answer.py — his answer resumes the inline row that asked: the kept act re-runs, bound.

The second half of `nucleo/request/inline_ask` (split by concern, 2026-11-12 A5: the ask door stays there — the row
waits, the answering call is claimed —, the ANSWER's re-run lives here). `rerun` is the one door every bound or
screen answer to an inline row crosses (`worker_api_answer.answer`): a task matter, a notice, a send task's slot, a
«for X or new?», a parked errand, a card's consent act, our own question about an act of a card (`answered_offer`), an
answer that needs composing about an act that leaves (`answered_task`), and the plain re-run of the kept act with the
answer bound into its slot through the card's own door.
"""
from __future__ import annotations

from nucleo.request import acts_of, base, note


def bound(retained: dict, text: str, choice: int | None) -> dict | None:
    """The retained payload with his answer in its slot: the candidate the verdict chose, else his text (a fact, or
    the screen's option). None when there is nothing to bind."""
    slot = str(retained.get("slot") or "")
    cands = list(retained.get("candidates") or [])
    payload = dict(retained.get("payload") or {})
    if not slot:
        return payload                           # ASK_CONSENT: the act as it was, on his yes
    if choice is not None and 0 <= int(choice) < len(cands):
        payload[slot] = cands[int(choice)]
    elif str(text or "").strip():
        payload[slot] = " ".join(str(text).split())
    else:
        return None
    return payload


async def rerun(uid: str, entry: dict, text: str, choice: int | None = None):
    from nucleo.request import inline_ask   # the ask door (its once-per-answer lock, its recent acts); imports this module last
    """Resume inline row `uid`: the retained act through the same door with the answer bound. The door's echo settles
    the row through `circuit.settle`; a door that asks again makes the SAME row wait on a new question."""
    from nucleo.circuit import ledger
    retained = entry.get("retained") or {}
    if retained.get("kind") == "matter":         # a task matter's question (V2-857 P0-2): his answer is on the row
        if inline_ask.take(str(entry.get("ask_id") or "")):
            ledger.resumed(uid)                  # the turn that bound it reads the answer off the row and acts
        return {"ok": True, "row": uid, "answered": True}
    if retained.get("kind") == "notice":         # a scheduled notice's question (V2-878 §4): his answer ends it
        return __import__("nucleo.pulse.notice_ask", fromlist=["x"]).answered(uid, entry, text)
    if retained.get("kind") == "send":           # a send task's slot (`nucleo/request/send_task`): his answer fills it
        return __import__("nucleo.request.send_task_answer", fromlist=["x"]).answered(uid, entry, text, choice)
    if retained.get("kind") == "which":          # «for X, or something new?» (V2-878 §3 e): his answer routes it
        return __import__("nucleo.turn.which_flow", fromlist=["x"]).answered(uid, entry, text, choice)
    if retained.get("kind") == "start":          # a parked errand's question (V2-857 P0-1): its yes relaunches it
        from nucleo.dispatch import confirm as _dc
        return _dc.rerun_start(uid, entry, text, choice)
    from nucleo.request import consent_ask as _ca
    if retained.get("kind") in _ca.ACTS:         # a card's delete/restore, a cluster connect or send (phase 3)
        from nucleo.cli.worker_api_answer import decision
        said = decision(str(entry.get("question") or ""), text, choice, entry.get("options"))
        if said is None:                         # not a decision: the question stays open, the row waits
            return {"ok": False, "row": uid, "unclear": True}
        if not inline_ask.take(str(entry.get("ask_id") or "")):
            return None
        yes = said == "yes"
        from nucleo import circuit
        if not yes:
            circuit.settle(row=uid, state="cancelled", outcome="he did not confirm it")
            return {"ok": False, "row": uid}
        ledger.resumed(uid)
        res = await _ca.ACTS[str(retained["kind"])](retained)
        ok = bool(isinstance(res, dict) and res.get("ok", True))
        circuit.settle(row=uid, state="done" if ok else "failed",
                       outcome=f"{retained['kind']} {'ran' if ok else 'failed'} on his yes")
        return {"ok": ok, "row": uid, "result": res}
    from nucleo.request import answered_task
    try:   # is this kept question about an act that leaves the machine? Read off the card's declared effects
        from widgets import effects
        card = base(retained.get("widget"))
        leaves = bool(card) and any(effects.leaves(card, a) for a in acts_of(retained))
    except Exception as e:  # noqa: BLE001
        note(e)
        leaves = False
    if retained.get("kind") == inline_ask.UTTERANCE and not leaves:
        # A5 — our own question about an act of the CARD: his yes or his fact composes the act on this row
        from nucleo.request import answered_offer
        return await answered_offer.run(uid, entry, text, choice)
    if leaves and not answered_task.deterministic(entry, choice):
        # F2e — an answer that needs composing (our own question, a fact, a free answer) about an act that LEAVES is
        # an identified task: a worker takes it on this row. A plain pick or a yes re-runs the kept act below.
        return {"ok": True, "worker": answered_task.start(uid, entry, text, choice), "row": uid}
    wid, action = str(retained.get("widget") or ""), str(retained.get("action") or "")
    if not inline_ask.take(str(entry.get("ask_id") or entry.get("corr_id") or "")):
        return None                              # this answer's act already ran (the model's own call took it)
    if entry.get("consent") == "ask_consent":
        # his answer is the candidate the brief (or the screen) chose — `#0` yes, `#1` no; only with no choice at
        # all are his words read by the confirmation recogniser
        if choice is not None:
            yes = int(choice) == 0
        else:
            from nucleo.cli.worker_api_answer import _says_yes
            yes = _says_yes(str(entry.get("question") or ""), text, entry.get("options"))
        payload = dict(retained.get("payload") or {}) if yes else None
        if payload is None:
            from nucleo import circuit
            circuit.settle(row=uid, state="cancelled", outcome="he did not confirm it")
            return None
    else:
        payload = bound(retained, text, choice)
    if not (wid and action) or payload is None:
        return None
    slot = str(retained.get("slot") or "")
    if slot and (dup := inline_ask._recent(wid, action, payload, slot)) and dup != uid:
        # The same turn's own act already REACHED exactly this candidate on another row: one answer, one act.
        from nucleo import circuit
        circuit.settle(row=uid, state="done", outcome=f"the same act already left on row {dup}")
        return {"ok": True, "already": True, "row": dup}
    ledger.resumed(uid)
    inline_ask._remember(wid, action, slot, str(payload.get(slot) or "") if slot else "", uid)
    row = ledger.get(uid) or {}
    from nucleo.flash import data_ops
    return await data_ops.dispatch_and_report(wid, action, payload, row=uid,
                                              text=str(row.get("goal") or row.get("title") or ""))
