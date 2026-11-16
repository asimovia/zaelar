"""nucleo/request/send_task_answer.py — his answer to a send task's question, and the answering turn's own call.

The other half of `nucleo/request/send_task` (split by concern, nucleo files stay small): `answered` fills the slot
the task asked for on the SAME row and runs it (a which-answer that still leaves the words lacking hands the row to a
Brain Worker that composes them); `take_call` lets the model's call on the answering turn fill the waiting row, so the
bound answer and the call are one answer, never two sends.
"""
from __future__ import annotations

import time

from nucleo.request import base, note
from nucleo.request.send_task import (AGENT, HIS, KIND, NONE, _emit, _end_state, _keep, _question, _schedule, _words_of,
                                      artefact, missing, sources)
from nucleo.request.send_task_run import _rec

#: Spoken answers to a send task's TEXT question that the model did not quote (`compose`): the worker composes them.
_COMPOSE: set = set()
#: How long a waiting send task stays the one a quoted line of his completes (`fill_from_quote`): the conversation.
RECENT_S = 600.0


def compose(ask_id: str) -> None:
    """His spoken answer to this send task's text question was not quoted by the model: a worker composes it."""
    if ask_id:
        _COMPOSE.add(str(ask_id))


def fill_from_quote(said: str, model_text: str, *, emit=None) -> str:
    """The turn's model QUOTED words of his and named the person of the latest send task waiting on its TEXT: those
    words are the text, that row runs (measured live: «dile: prueba siete…» was not bound — the model said «Sending
    "prueba siete, ignóralo" to Quinn now» and the verdict ran `dismiss`). Both are required — his quoted words AND
    the person the row waits to write to — so a quote about anything else completes nothing. The row's uid, or "".
    """
    try:
        from nucleo.acts.message_names import TOK, fold
        from nucleo.circuit import asker
        from nucleo.cli import worker_api
        from nucleo.request import inline_ask, send_task_words
        quoted = send_task_words.quoted_his(said, model_text)
        if not quoted:
            return ""
        named = set(TOK.findall(fold(send_task_words.without(model_text, quoted))))
        now = time.time()
        for a in sorted(worker_api.open_asks(), key=lambda a: -float(a.get("since") or 0)):
            art = asker.artefact(str(a["task_id"]))
            ret = art.get("retained") or {}
            if ret.get("kind") != KIND or str(ret.get("slot_name") or "") != "text":
                continue
            if now - float(art.get("created") or 0) > RECENT_S:
                break
            uid = str(a["task_id"])
            keep = artefact(uid)
            who = [str(v) for s, d in (keep.get("slots") or {}).items() if d.get("rule") == "his_words"
                   for v in [dict(keep.get("payload") or {}).get(str(d.get("key") or s))] if v]
            if not who or not any(set(TOK.findall(fold(w))) & named for w in who):
                break                              # the latest waiting send is not the one this line speaks of
            entry = dict(art)
            got = answered(uid, entry, quoted)
            _emit(emit, "📨 his quoted words complete the send that waited for them", quoted,
                  {"cat": "flash", "task_id": uid, "ask_id": a.get("ask_id"), "ran": bool(got.get("ok"))})
            return uid
    except Exception as e:  # noqa: BLE001
        note(e)
    return ""


def answered(uid: str, entry: dict, text: str, choice: int | None = None) -> dict:
    """His answer fills the slot this task asked for, on this same row, and the task goes on. A `no` to its consent
    cancels it; a yes clears what the door asked about and runs it."""
    from nucleo import circuit, consent
    from nucleo.request import inline_ask
    retained = entry.get("retained") or {}
    ask_id = str(entry.get("ask_id") or entry.get("corr_id") or "")
    if str(entry.get("consent") or "") == consent.ASK_CONSENT:
        from nucleo.cli.worker_api_answer import decision
        said = decision(str(entry.get("question") or ""), text, choice, entry.get("options"))
        if said is None:
            return {"ok": False, "row": uid, "unclear": True}
        if not inline_ask.take(ask_id):
            return {"ok": True, "row": uid, "already": True}
        if said != "yes":
            circuit.settle(row=uid, state="cancelled", outcome="he did not confirm it")
            return {"ok": False, "row": uid}
        from nucleo.request.send_task_run import consented
        from nucleo.workers import taint
        taint.cleared(_rec(uid, artefact(uid)))
        consented(uid)          # his yes answers the door's question about THIS payload: it is not asked again
        _schedule(uid)
        return {"ok": True, "row": uid}
    key, slot = str(retained.get("slot") or ""), str(retained.get("slot_name") or "")
    if ask_id in _COMPOSE and slot == "text":
        # a SPOKEN answer the model did not quote is not the text: an instruction («reply with what the hotel's mail
        # says») is composed by a Brain Worker on this row — never sent literally (measured live, 2026-11-06)
        _COMPOSE.discard(ask_id)
        if not inline_ask.take(ask_id):
            return {"ok": True, "row": uid, "already": True}
        return {"ok": True, "row": uid, "worker": _worker(uid, artefact(uid), ask_id, " ".join(str(text).split()))}
    cands = list(retained.get("candidates") or [])
    from nucleo.request import consent_ask
    if choice is None and cands and (yn := consent_ask.declared_answer(text)):   # «sí» to «by X, as you said, or by Y?»
        choice = 0 if yn == "yes" else 1 if len(cands) > 1 else None
    value = str(cands[int(choice)]) if choice is not None and 0 <= int(choice) < len(cands) else \
        " ".join(str(text or "").split())
    if not (key and value):
        return {"ok": False, "row": uid, "unclear": True}
    art = artefact(uid)
    from widgets import field_types   # a field declared a list takes his answer as its item (the card splits it)
    wid_, act_ = base(str(art.get("widget") or "")), str(art.get("action") or "")
    listed = field_types.declared(wid_, act_).get(key) == field_types.LIST
    if field_types.keeps(wid_, act_, key, (art.get("payload") or {}).get(key)):
        return {"ok": False, "row": uid, "unclear": True}   # an answer NEVER replaces a list that already has people
    if not inline_ask.take(ask_id):
        return {"ok": True, "row": uid, "already": True}
    art.setdefault("payload", {})[key] = [value] if listed else value
    (art.setdefault("slots", {}).setdefault(slot or key, {"key": key, "rule": ""}))["source"] = HIS
    if (slot or key) == "channel" and cands:   # his answer to «which channel?» IS his reading of it: never doubted again
        from nucleo.acts import message_channel
        art["reading"] = rd = art.get("reading") if isinstance(art.get("reading"), dict) else {}
        rd.setdefault("result", {})[message_channel.KEY] = {"choice": value.strip().lower(), "confidence": 1.0, "probs": {}}
    from nucleo import his_words
    his_words.note(value)                      # his answer is his naming of that value, for every door
    art.setdefault("heard", []).append(" ".join(str(text or value).split()))
    _keep(uid, art)
    _end_state(uid, str(art.get("widget") or ""), str(art.get("action") or ""), art.get("payload") or {},
               _words_of(uid))
    nxt, nkey = missing(art)
    if nxt and str(((art.get("slots") or {}).get(nxt) or {}).get("rule") or "") == "composed":
        # He answered WHICH person and the words still lack: his sentence most likely carried them (the model never
        # extracted them). A question about what he said is not legitimate — a Brain Worker composes the words from
        # his request on THIS row (the person already his, the end state on the row) and sends through the exit door.
        return {"ok": True, "row": uid, "worker": _worker(uid, art, ask_id, value, choice=choice)}
    return _go_on(uid, art)


def _go_on(uid: str, art: dict) -> dict:
    """After a slot was filled on this row: the next declared field that still lacks is asked the same way, on the
    same row (V2-919 M2); with nothing lacking the task runs."""
    from nucleo.request import inline_ask
    nxt, nkey = missing(art)
    if nxt:
        from nucleo.request.send_task import _missing_line, _said_asked
        q = _missing_line(art, nxt)
        ask_id = _question(uid, art, nxt, nkey, q)
        _said_asked(str(art.get("widget") or ""), str(art.get("action") or ""), q)
        return {"ok": True, "row": uid, "asked": ask_id}
    from nucleo.circuit import ledger
    ledger.resumed(uid)
    inline_ask.resuming(uid, {"widget": art.get("widget"), "action": art.get("action"), "candidates": []})
    _schedule(uid)
    return {"ok": True, "row": uid}


def _worker(uid: str, art: dict, ask_id: str, answer: str, *, choice: int | None = None) -> int:
    """A Brain Worker on this row (`message` playbook): the words to compose, the person and the end state kept."""
    from nucleo.circuit import ledger
    from nucleo.request.answered_task import PLAYBOOK
    row = ledger.get(uid) or {}
    request = _words_of(uid)
    said = f"{request} — {answer}" if request and answer else request or answer
    ledger.resumed(uid)
    dw = dict((_spec_of(uid) or {}).get("done_when") or {})
    ctx = {"src": "answer", "kind": "generic", "task_uid": uid, "answers": ask_id, "playbook": PLAYBOOK,
           "surface": "voz", "origin": str(row.get("origin") or "voz"), "heard": answer,
           **({"trace": str(row["trace_id"])} if row.get("trace_id") else {}),
           **({"done_when": dw if "any" in dw or "all" in dw else {"any": [dw]}} if dw else {}),
           **({"chosen": f"{ask_id}#{int(choice)}"} if choice is not None else {})}
    from nucleo.acts.errand import escalate_to_slowbrain
    tid = int(escalate_to_slowbrain(said, context=ctx) or 0)
    _emit(None, "↩ answer handed its task to a worker", said, {"cat": "flash", "task_id": uid, "ask_id": ask_id,
          "worker": tid, "playbook": PLAYBOOK})
    if not tid:
        from nucleo import circuit
        circuit.settle(row=uid, state="failed", outcome="the answered task could not be started")
    return tid


def _spec_of(uid: str) -> dict | None:
    from nucleo.circuit import spec
    return spec.of_task(uid)


def _folded(wid: str, action: str, payload: dict | None) -> dict:
    """The call's payload under the card's own keys and shapes (`contract.fold_aliases`, `field_types.as_declared`,
    as `send_task.retain` keeps it)."""
    from widgets import field_types
    try:
        from widgets import contract
        folded = contract.fold_aliases(base(wid), action, dict(payload or {}))
    except Exception as e:  # noqa: BLE001
        note(e)
        folded = dict(payload or {})
    return field_types.as_declared(base(wid), action, folded)


def _answers(brief, ask_id: str) -> bool:
    """Does the turn's reading surely say his words answer THIS open question (`worker_api_bind.KEY`, at the licence)?
    No reading, a doubt, or another choice → no."""
    if brief is None or not ask_id:
        return False
    try:
        from nucleo.cli import worker_api_bind as _bind
        from nucleo.turn import verdicts
        choice, _info = verdicts.read(brief, _bind.KEY, None)
        return choice is not None and str(choice).split(_bind.PICK, 1)[0] == ask_id
    except Exception as e:  # noqa: BLE001 — an unread verdict is no answer: the exit asks
        note(e)
        return False


def take_call(wid: str, action: str, payload: dict | None, said: str, *, brief=None) -> str:
    """The same act Flash calls on a turn that answers this task's question (the model heard his answer and called
    the door with it): its slots fill the waiting row, nothing new opens. The row's uid, or "" when no send task
    waits on this card's act."""
    try:
        from nucleo.circuit import asker
        from nucleo.cli import worker_api
        from nucleo.request import inline_ask
        for a in worker_api.open_asks():
            art = asker.artefact(a["task_id"])
            ret = art.get("retained") or {}
            if ret.get("kind") != KIND or base(ret.get("widget")) != base(wid) or str(ret.get("action")) != action:
                continue
            uid = str(a["task_id"])
            keep = artefact(uid)
            said = f"{_words_of(uid)} {said}".strip()     # his words on this task: the request and this answer
            payload = _folded(wid, action, payload)          # `name`/`platform` are the card's `contact`/`channel`
            got = sources(wid, action, dict(payload or {}), said, reading=keep.get("reading"))
            slot = str(ret.get("slot_name") or ret.get("slot") or "")
            if got.get(slot, {}).get("source", NONE) == NONE:
                continue                        # the call does not fill what this task is waiting for
            if not inline_ask.take(str(a["ask_id"] or "")):
                return uid                      # his answer already ran this
            art.update(state="answered", answer=str(dict(payload or {}).get(ret.get("slot")) or ""),
                       answered_at=time.time())
            asker.keep(uid, art)
            from widgets import field_types   # a value merges only into a field of ITS declared kind (V2-919 M1)
            held = dict(keep.get("payload") or {})   # …and never over a list the row already holds (`keeps`)
            merged = {**held, **{k: v for k, v in dict(payload or {}).items()
                                 if field_types.filled(base(wid), action, k, v)
                                 and not field_types.keeps(base(wid), action, k, held.get(k))}}
            before = dict(keep.get("slots") or {})
            keep.update(payload=merged, slots=sources(wid, action, merged, said, reading=keep.get("reading")))
            keep.setdefault("heard", []).append(said)
            for s, d in keep["slots"].items():   # what he already gave this task stays his — if the call left it as it was
                k = str(d.get("key") or s)
                if d["source"] == AGENT and str((before.get(s) or {}).get("source")) == HIS and merged.get(k) == held.get(k):
                    d["source"] = HIS
            # A value this turn's CALL put on the row is part of what he ordered only when the turn's reading says
            # his words ANSWER this row's question; with any other reading, or none, his order over a held row is
            # not read for it — the exit asks.
            if merged != held and not _answers(brief, str(a.get("ask_id") or "")):
                keep["order_void"] = True
            _keep(uid, keep)
            _end_state(uid, wid, action, merged, said)
            _go_on(uid, keep)    # missing re-read AFTER the merge: a row never waits on a question nobody asked
            return uid
    except Exception as e:  # noqa: BLE001
        note(e)
    return ""
