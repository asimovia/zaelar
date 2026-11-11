"""«Is that for X, or something new?» — the question the door asks when the flow judge ran out of time with an errand
open (V2-878 §3 e).

A judge timeout used to read as «no flow», so a refinement said while the model was slow opened a SECOND errand beside
the one it refined. Now `flow_of.route` answers `undecided` (only with an errand open, only on a timeout) and the portal
asks through the one asker: a `waiting_for=user_answer` row with its `ask_id` and two declared answers in his language
— the errand he named last («For the monitors») and «Something new». The brief's binding pick, or a reply that IS one of
the two, answers it; nothing is opened until he does, and the row ends by its own deadline, never a wall clock.
"""
from __future__ import annotations

import json

from loguru import logger

KIND = "which"


def _plain(ctx: dict) -> dict:
    """The escalation's context, kept on the row: what survives JSON (a restart reads it back)."""
    out = {}
    for k, v in (ctx or {}).items():
        try:
            json.dumps(v)
            out[k] = v
        except (TypeError, ValueError) as e:   # a value the row cannot carry is left out, and said
            logger.debug(f"which_flow: context key {k!r} not kept on the row ({type(e).__name__})")
            continue
    return out


def options(name: str) -> list[str]:
    from i18n import langs as _lg
    lang = _lg.current_language()
    return [lang.which_errand_that.format(what=name), lang.which_errand_new]


def ask(req: str, r: dict, ctx: dict) -> str:
    """Ask him whose `req` is (route `r`, `undecided`, names the errand he named last). Returns the `ask_id`, "" when
    the question could not be put on a row (the portal has already declined to open anything: the request waits on
    his next words, as a timeout without an errand open never did)."""
    try:
        from i18n import langs as _lg
        from nucleo.circuit import asker
        from nucleo.runtime_ids import next_seq
        from nucleo.turn import flow_of as _f, named_errand as _ne
        fid = str(r.get("flow") or "")
        flow = next((c for c in _f.candidates() if str(c.get("id")) == fid), {"id": fid, "request": ""})
        name = _ne.spoken_name(flow) or str(flow.get("request") or "")[:60]
        question = _lg.current_language().which_errand.format(what=name)
        uid = asker.open_row(req, kind=KIND, origin=str(ctx.get("origin") or "voz"))
        if not uid:
            return ""
        ask_id = f"{uid}-w{next_seq('which.ask')}"
        return asker.ask(uid, {"ask_id": ask_id, "corr_id": ask_id, "uid": uid, "task_id": "", "inline": True,
                               "question": question, "options": options(name), "answer": "", "result": None,
                               "retained": {"kind": KIND, "request": req, "flow": fid, "context": _plain(ctx)}})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"which_flow: the question is not on a row — {type(e).__name__}: {e}")
        return ""


def answered(uid: str, entry: dict, text: str, choice: int | None) -> dict:
    """His answer (`inline_ask.rerun`): the brief's pick, or a reply that IS one of the two declared answers. «For X»
    routes the request into X as the portal would have; «something new» opens it. Anything else: the row waits."""
    from nucleo import circuit
    from nucleo.request import consent_ask as _ca
    from nucleo.request.inline_ask import take
    said = ("yes" if int(choice) == 0 else "no") if choice is not None else _ca.declared_answer(text, entry.get("options"))
    if said is None:
        return {"ok": False, "row": uid, "unclear": True}
    if not take(str(entry.get("ask_id") or "")):
        return {"ok": True, "row": uid, "already": True}
    kept = entry.get("retained") or {}
    req, fid, ctx = str(kept.get("request") or ""), str(kept.get("flow") or ""), dict(kept.get("context") or {})
    from nucleo.acts import errand
    from nucleo.turn import flow_door, flow_of as _f
    flow = next((c for c in _f.candidates() if str(c.get("id")) == fid), None) if said == "yes" else None
    if flow is None or flow_door.obey(req, _f._of(flow, req, None), ctx):
        ctx.setdefault("routed", f"{_f.NEW}:")
        errand.escalate_to_slowbrain(req, context=ctx)
    circuit.settle(row=uid, state="done", outcome=f"his answer: {'that errand' if flow else 'a new one'}")
    return {"ok": True, "row": uid, "into": str((flow or {}).get("id") or "")}
