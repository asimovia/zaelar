"""nucleo/request/send_task_turn.py — where a voice turn meets a send task (2026-11-06).

The fourth piece of `nucleo/request/send_task`, split by concern so the turn's own files stay small: `identified`
reads the send the brief surely names; `at_escalation` / `at_close` make it the send task whatever the model did
(an escalation, a promise, a question in prose); `unbind` keeps a turn that already is a send task from answering
another waiting question; `slot_answer` gives a send task's slot question the words the model quoted of his.
"""
from __future__ import annotations

from nucleo.request import base, note


def identified(brief) -> tuple[str, str]:
    """The send the turn's brief surely identifies: `(card, leaving act)` — the `screen_action` verdict naming an act
    that leaves, else the `end_state` verdict naming a card's `<collection>` that a leaving act's declared end state
    fills (the send of that card: the act whose slots name his person). ("", "") when the brief names none."""
    try:
        from nucleo.circuit import spec as _spec
        from nucleo.turn import brief as _tb, verdicts
        from nucleo.workers import exit_slots
        from widgets import effects
        choice, info = verdicts.read(brief, _tb.TARGET_KEY, None)
        wid, _sep, act = str(choice or "").partition(":")
        # only an act whose person comes from HIS words: one whose recipient the card picks (a `reply` to «the open
        # thread») could reach a stranger — measured live, a reply row with no person would have answered the last
        # inbound mail. Such an act keeps its own route (the worker, the exit door).
        if info and wid and act and effects.leaves(base(wid), act) and _his_person(wid, act):
            return wid, act
        choice, info = verdicts.read(brief, _spec.END_KEY, None)
        wid, _sep, coll = str(choice or "").partition(":")
        if not (info and wid and coll) or str(choice) == "none":
            return "", ""
        from nucleo import on_his_behalf as _ob
        from nucleo.request.ending import leaving_acts
        cands = [a for a in leaving_acts(wid)
                 if str((_spec.template_of(wid, a) or {}).get("collection") or "") == coll
                 and any(d.get("from") == "his_words" for d in exit_slots.declared(wid, a).values())]
        # the card says which of them a bare order means (`"primary": true` on the action), else the first declared
        primary = [a for a in cands if (_ob._spec(wid, a) or {}).get("primary") is True]
        if primary or cands:
            return wid, (primary or cands)[0]
    except Exception as e:  # noqa: BLE001
        note(e)
    return "", ""


def _his_person(wid: str, act: str) -> bool:
    from nucleo.workers import exit_slots
    return any(d.get("from") == "his_words" for d in exit_slots.declared(base(wid), act).values())


def at_escalation(brief, said: str, spoken_text: str, escalate_req: dict, worker_acted: dict, replacing: bool,
                  emit) -> dict:
    """A send the brief identified is a SEND TASK whatever the model did (`send_task_words.by_verdict`): an escalation
    whose request quotes his words runs on its row with no worker; one that lacks the words keeps the worker, ON that
    row (its slots and end state already there). Measured: the model escalated a complete send and a worker
    rediscovered it in 192 s. Returns the context the worker carries ({} when none)."""
    from nucleo.request import send_task_answer as _sta, send_task_words as _stw
    if not escalate_req.get("send_task") and _sta.fill_from_quote(
            said, f"{escalate_req['v'] or ''} {spoken_text or ''}", emit=emit):
        escalate_req["send_task"] = True        # his quoted words completed the send that waited: nothing else opens
        escalate_req["v"] = None
        escalate_req.pop("say", "")
    if escalate_req["v"] is not None and (not worker_acted["v"] or replacing):
        uid, how = _stw.by_verdict(brief, said=said, model_text=str(escalate_req["v"] or ""),
                                   escalate_req=escalate_req, worker_acted=worker_acted, replacing=replacing,
                                   emit=emit, on_missing="worker")
        if how == "run":
            escalate_req["v"] = None            # the task runs on its row: nothing is launched for it
            escalate_req.pop("say", "")
        elif how == "worker":
            return {"task_uid": uid, "playbook": "message"}
    return {}


def at_close(brief, said: str, spoken_text: str, escalate_req: dict, worker_acted: dict, emit, escalate_mod) -> str:
    """A send the brief identified, with no call and no escalation (a promise, a question in prose), is its task: run,
    or waiting on the one slot it lacks (the question the mouth already said becomes the row's). A sure «escalate»
    verdict says the text is work (composed from somewhere): the worker composes it ON the send row. The row's uid,
    or '' when the turn holds no send task."""
    from nucleo.request import send_task_words as _stw
    from nucleo.turn import brief as _tb
    esc, esc_info = _tb.read(brief, _tb.ESCALATE_KEY, "")
    uid, how = _stw.by_verdict(brief, said=said, model_text=spoken_text, escalate_req=escalate_req,
                               worker_acted=worker_acted, emit=emit,
                               on_missing="worker" if (esc_info is not None and esc == "escalate") else "ask",
                               asked_line=spoken_text if _stw.ends_asking(spoken_text) else "")
    if uid and how == "worker":
        escalate_mod.escalate_to_slowbrain(said, context={"src": "voice", "kind": "generic", "task_uid": uid,
                                                          "playbook": "message", "surface": "voz",
                                                          "errand_class": escalate_mod.class_verdict(brief),
                                                          "reading": _tb.carried(brief)})
    return uid


def unbind(brief, text: str, how: str, asks: list, escalate_req: dict, emit) -> tuple[str, list]:
    """This turn's words already are a send task (opened, or filling the one that asked): they answer no other waiting
    question. Measured live: a 0.51 reading bound a dictated send to a stale reply row as well. A new send to his
    named person answers no waiting task either."""
    from nucleo.cli import worker_api_bind as _bind
    if how != _bind.NOTHING and escalate_req.get("send_task"):
        emit("brain", "📨 his words are this turn's send task — no other waiting task is answered", text=text[:120],
             role="system", extra={"cat": "flash", "among": [a.get("task_id") for a in asks]})
        return _bind.NOTHING, []
    if how == _bind.ASK_WHICH:
        from nucleo.request import send_task_words as _stw
        if _stw.new_send(brief, text, asks):
            return _bind.NOTHING, []
    return how, asks


def slot_answer(ask: dict, text: str, spoken_text: str) -> str:
    """His answer to a SEND TASK's slot question is the words the model quoted of his when it quoted them («Sending
    "prueba tres, ignóralo" to Quinn»), else his line as he said it; any other task's question gets his line."""
    from nucleo.cli import worker_api_bind as _bind
    try:
        from nucleo.circuit import asker
        from nucleo.request import send_task_words
        ret = asker.artefact(str(ask.get("task_id") or "")).get("retained") or {}
        if ret.get("kind") == "send":
            if (quoted := send_task_words.quoted_his(text, spoken_text)):
                return quoted
            from nucleo.request import send_task_answer
            send_task_answer.compose(str(ask.get("ask_id") or ""))   # not quoted: the worker composes it
            return _bind.answer_text(text)
    except Exception as e:  # noqa: BLE001
        note(e)
    return _bind.answer_text(text)
