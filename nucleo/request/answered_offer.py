"""nucleo/request/answered_offer.py — his answer to OUR question about an act of a card runs that act on its row.

THE CLASS (group A5, 2026-11-12). «Apúntame el gimnasio» → the model asked «¿a qué hora?» without calling; «¿qué
tengo mañana?» → «…¿te apunto el gimnasio?». The question was ours, and it was not a row: his «a las siete» or his
«sí» worked only if the model happened to call `add_meeting` on the next turn — and the `readable` hold, read at the
licence, ate the model's words when it did not (1 of 3 on the bench).

Now our question about a declared act the brief names is a row (`ask_outside_door.held`, kind `utterance` with the
card and the act), his answer binds to it through the brief's `answers_open_question` and lands here
(`inline_ask.rerun`):

  · a declared NO (`worker_api_answer.decision`) cancels the row — nothing runs;
  · a yes, or a fact («a las siete»), is his answer to the offer: the act's payload is COMPOSED from his request, our
    question and his answer — a bounded pass with the card's declared actions and nothing else (the fallback the
    operator kept, 2026-11-12: a payload only a model can write) — and the act runs through the card's own door on
    THIS row (`data_ops.dispatch_and_report`), whose echo settles it — unless the one consent rule asks about this
    call (`action_mode_now`, CRIT-C13): then the card's declared question waits on the row and his yes runs it;
  · the answering turn's own call of that act is the same answer (`inline_ask.claim` takes the question first): one
    answer, one act, whoever triggers it.

A leaving act keeps its path: `answered_task` (a worker on the row), never this.
"""
from __future__ import annotations

from nucleo.request import acts_of, base, event, note

#: The pass's brief: the offer, his request and his answer; the card's declared actions; one call or none.
_SYS_OFFER = (
    "You are the brain of a voice assistant. The operator asked «{request}». You answered with a question or an "
    "offer: «{question}». He has now answered: «{answer}». If his answer accepts or completes it, make NOW exactly one "
    "`widget_data` call with widget_id «{wid}» and action «{act}», its payload taken from his request, your question "
    "and his answer (a title, a person, a date, a time as they were said; the dates below). If he declined, or asks "
    "for something else, call nothing. Write any text you put in the payload in the OPERATOR's language.\n\n"
    "Actions of «{wid}»:\n{actions}{card}"
)


async def compose(wid: str, act: str, *, request: str, question: str, answer: str, spec=None) -> dict | None:
    """The act's payload from the offer and his answer, by one bounded pass; None when the pass made no such call."""
    try:
        from nucleo.acts import card_pass as _cp
        from widgets import runtime as _rt
        card = base(wid)
        manifest = _rt.get(card) or {}
        tool = _cp.widget_data_tool()
        if act not in (manifest.get("actions") or {}) or not tool:
            return None
        digest = ""
        try:
            from nucleo.flash import widget_read as _wr
            digest = str(_wr.read(card) or "").strip()[:1500]
        except Exception as e:  # noqa: BLE001
            note(e)
        held = (_cp._CARD.format(wid=card, digest=digest) if digest else "") + _cp.days()
        got: list[tuple[str, dict]] = []
        from nucleo.llm.fast_client import FastClient
        await FastClient().complete(
            [{"role": "system", "content": _cp.in_his_lang(_SYS_OFFER).format(
                request=request[:400], question=question[:300], answer=answer[:300], wid=card, act=act,
                actions=_cp.actions_block(manifest), card=held)},
             {"role": "user", "content": f"Operator: «{answer[:300]}»"}],
            spec=spec, max_tokens=400, tools=[tool], no_thinking=True,
            on_tool_call=lambda name, args: got.append((name, args if isinstance(args, dict) else {})))
        for name, args in got:
            if name == "widget_data" and base(args.get("widget_id")) == card and str(args.get("action") or "") == act:
                return dict(args["payload"]) if isinstance(args.get("payload"), dict) else {}
        _cp.note(card, "the pass made no call for the offer", action=act)
        return None
    except Exception as e:  # noqa: BLE001 — a pass that failed composes nothing; the row says so
        note(e)
        return None


async def run(uid: str, entry: dict, text: str, choice: int | None = None) -> dict | None:
    """His answer to our question about an act of a card (`retained.kind == utterance`, an act that stays on the
    machine): a declared no cancels the row; anything else composes the act and runs it on THIS row."""
    from nucleo import circuit
    from nucleo.circuit import ledger
    from nucleo.cli.worker_api_answer import decision
    from nucleo.request import inline_ask
    retained = entry.get("retained") or {}
    ask_id = str(entry.get("ask_id") or entry.get("corr_id") or "")
    wid, acts = str(retained.get("widget") or ""), acts_of(retained)
    question = str(entry.get("question") or "")
    said = decision(question, text, choice, entry.get("options"))
    if said == "no":
        if inline_ask.take(ask_id):
            circuit.settle(row=uid, state="cancelled", outcome="he declined the offer")
        return {"ok": False, "row": uid}
    if not (wid and acts) or not inline_ask.take(ask_id):
        return None                                   # this answer's act already ran (the model's own call took it)
    act = acts[0]
    row = ledger.get(uid) or {}
    request = " ".join(str(retained.get("text") or row.get("goal") or row.get("title") or "").split())
    answer = " ".join(str(text or "").split())
    ledger.resumed(uid)
    inline_ask.resuming(uid, retained)                # the same act called elsewhere meanwhile is this answer's
    payload = await compose(wid, act, request=request, question=question, answer=answer)
    event(None, "↩ his answer to our offer composes its act", f"{wid}:{act}", {"cat": "flash", "task_id": uid,
          "ask_id": ask_id, "composed": payload is not None, "answer": answer[:120]})
    from nucleo.flash import data_ops, frontend
    from widgets import actions as _wa
    mode = frontend.action_mode_now(wid, act, payload) if payload is not None else ""
    if mode not in (_wa.FAST, _wa.CONFIRM):   # not composed, or an act this door does not run (an errand's): no guess
        circuit.settle(row=uid, state="failed", outcome="the offer's act could not be composed and run from his answer")
        return {"ok": False, "row": uid}
    if mode == _wa.FAST:
        return await data_ops.dispatch_and_report(wid, act, payload, row=uid, text=request)
    # CRIT-C13 — his answer composed the act, it never said yes to it: the card's declared question waits on this row
    from nucleo.request import consent_ask, send_task
    q = consent_ask.question(wid, act, payload)
    inline_ask.held(uid, wid, act, payload, {"ok": False, "consent": "ask_consent"}, question=q, options=consent_ask.yes_no())
    send_task._said_asked(wid, act, q)
    return {"ok": False, "row": uid, "asked": True}
