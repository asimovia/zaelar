"""Who wins a turn's commission — one rule, read in SHADOW first (V2-874).

Measured on a demo turn («open the one that's the best deal», an errand searching): three voices answered it. The
brief's `escalate_or_inline` at 0.54 routed the turn and silenced the model inline («nothing runs inline»); `flow_of`
put the request into the live errand it belonged to (an inject); and the model's clarifying question was said anyway.
The close then logged the inject as an escalation.

The rule `verdicts` already states — a verdict overrides what the model did only at VETO; between LICENCE and VETO
a disagreement is a doubt — applied to the commission, without exceptions but one:

  · route          — the escalate verdict decides only errand vs inline, and below VETO it does not overrule the
                     model: a model that answered inline (its words, its calls) keeps the turn; a model that did nothing
                     is licensed into an errand from LICENCE. WHICH errand (new · inject · steer · stop) is `flow_of`'s.
  · hold_send      — the one exception, by REVERSIBILITY: a call that LEAVES the machine (`widgets.effects.leaves`)
                     is held from LICENCE (battery C9 measured the flip to escalate at 0.52-0.62 on sends).
  · silence_words  — the model's words and its clarifying question are silenced only at ≥ VETO.
  · open_new       — the more specific question wins: an escalate opens nothing new while `errand_target` reads an
                     errand, or `stop_errand` reads a steer/replace/stop/settled, at ≥ LICENCE — nor when `flow_of`
                     joined the request to an open flow.

`shadow()` emits `🧭 commission (shadow)` — what this rule WOULD do beside what the turn DID — and changes nothing.
The verdicts are read raw (`jev.peek`): the shadow adds no `jev read` of its own to the timeline.
"""
from __future__ import annotations

from loguru import logger

#: `stop_errand` choices that address the running errand (`nucleo.request.stop`): its words are for it.
ADDRESSES_THE_ERRAND = ("steer", "replace", "stop", "stop_all", "settled")
#: The model's own calls that hand the turn to an errand (a new one, or the one running).
HANDS_OVER = ("escalate_to_slowbrain", "send_to_worker")
#: `flow_of` outcomes that open a new errand («» — no route was begun or settled).
OPENS = ("", "new")
LABEL = "🧭 commission (shadow)"


def _answer(brief, key: str) -> tuple[str, float]:
    """`(choice, confidence)` as the brief answered `key`, or ("", 0.0). Never waits, never emits, never raises."""
    try:
        from nucleo import jev
        ans = (jev.peek(brief) or {}).get(key) or {}
        return str(ans.get("choice") or ""), float(ans.get("confidence") or 0.0)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"commission: {key} unreadable — {e!r}")
        return "", 0.0


def leaves(call: dict) -> bool:
    """Does this model call reach the world outside the machine? Read from the card's declared effects."""
    try:
        name, args = str((call or {}).get("name") or ""), (call or {}).get("args") or {}
        if name == "reply_message":
            wid, action = "mensajeria", "reply"
        elif name == "widget_data":
            wid, action = str(args.get("widget_id") or ""), str(args.get("action") or "")
        else:
            return False
        from nucleo.request import base
        from widgets import effects
        return bool(wid and action) and effects.leaves(base(wid.strip().lower()), action.strip())
    except Exception as e:  # noqa: BLE001
        logger.debug(f"commission: effects unreadable — {e!r}")
        return False


def reading(brief) -> dict:
    """The three questions the rule weighs, as the brief answered them."""
    esc, esc_c = _answer(brief, "escalate_or_inline")
    target, target_c = _answer(brief, "errand_target")
    stop, stop_c = _answer(brief, "stop_errand")
    return {"escalate": [esc, round(esc_c, 3)], "errand_target": [target, round(target_c, 3)],
            "stop_errand": [stop, round(stop_c, 3)]}


def in_play(brief) -> bool:
    """Is the escalate verdict at the licence this turn? Below it the rule has nothing to weigh."""
    from nucleo.turn import verdicts as _v
    esc, conf = _answer(brief, "escalate_or_inline")
    return esc == "escalate" and conf >= _v.LICENCE


def would(brief, *, model_calls=(), flow_as: str = "", model_wrote: bool = False, variant: str = "a") -> dict:
    """What the one rule decides for this turn. `model_wrote`: the model wrote words of its own this turn (said or held).

    (a) — the rule as `verdicts` writes it, the one chosen: below VETO the model's inline answer WINS (its words, its
        calls) and the escalate verdict commissions nothing; a model that did nothing is licensed into an errand; a send
        is still held from LICENCE. (b) — the escalate verdict commissions from LICENCE and the model's words stand
        beside it (kept in the shadow only to show what it would cost)."""
    from nucleo.turn import verdicts as _v
    r = reading(brief)
    (esc, esc_c), (target, target_c), (stop, stop_c) = r["escalate"], r["errand_target"], r["stop_errand"]
    names = [str((c or {}).get("name") or "") for c in model_calls or ()]
    by_verdict = esc == "escalate" and esc_c >= _v.LICENCE
    sure = esc == "escalate" and esc_c >= _v.VETO
    called = any(n in HANDS_OVER for n in names)
    sends = by_verdict and any(leaves(c) for c in model_calls or ())
    inline = bool(model_wrote) or any(n and n not in HANDS_OVER and n != "not_understood" for n in names)
    specific = ((target not in ("", "none") and target_c >= _v.LICENCE)
                or (stop in ADDRESSES_THE_ERRAND and stop_c >= _v.LICENCE))
    if variant == "b":
        errand = by_verdict or called
    else:
        errand = called or sure or sends or (by_verdict and not inline)
    return {"route": "errand" if errand else "inline",
            "open_new": bool(errand and not specific and str(flow_as or "") in OPENS),
            "silence_words": bool(sure),
            "hold_send": bool(sends)}


def did(escalate_req: dict | None, *, model_calls=(), flow_as: str = "", launched: bool = False,
        words_said: bool = False, worker: str = "") -> dict:
    """What the turn did, in the same four terms (read from the turn's own state, not from its prose)."""
    req = escalate_req or {}
    routed = bool(req.get("routed"))
    return {"route": "errand" if (launched or routed or worker) else "inline",
            "open_new": bool(launched and str(flow_as or "") in OPENS),
            "silence_words": bool(routed and not words_said),
            "hold_send": bool(routed and any(leaves(c) for c in model_calls or ()))}


def shadow(emit, *, at: str, brief, escalate_req: dict | None, model_calls=(), flow_as: str = "",
           launched: bool = False, words_said: bool = False, worker: str = "", text: str = "") -> dict | None:
    """Emit the rule's verdict, (a) and (b), beside the turn's. Never raises, never changes the turn.
    `escalate_req["held_words"]`: what the Hold kept unsaid on a routed turn (the model wrote them)."""
    try:
        from voice import trace as _trace
        model_calls = [*(model_calls or ()), *((escalate_req or {}).get("held_calls") or ())]   # the ones the gate held
        calls = [str((c or {}).get("name") or "") for c in model_calls]
        wrote = bool(words_said or str((escalate_req or {}).get("held_words") or "").strip())
        w = would(brief, model_calls=model_calls, flow_as=flow_as, model_wrote=wrote)
        wb = would(brief, model_calls=model_calls, flow_as=flow_as, model_wrote=wrote, variant="b")
        d = did(escalate_req, model_calls=model_calls, flow_as=flow_as, launched=launched, words_said=words_said,
                worker=str(worker or ""))
        if not in_play(brief):   # no escalate verdict at the licence: the rule touches nothing, the turn's own path stands
            for x in (w, wb):
                x.update(route=d["route"], open_new=d["open_new"])
        extra = {"cat": "flash", "at": at, "turn_id": str(_trace.current() or ""),
                 "call_id": str((brief or {}).get("_call_id") or ((_peek(brief) or {}).get("_call_id") or "")),
                 **reading(brief), "flow_as": str(flow_as or ""), "model_calls": calls, "words_said": bool(words_said), "model_wrote": wrote,
                 "worker": str(worker or ""),
                 "would": w, "did": d, "changes": sorted(k for k in w if w[k] != d[k]),
                 "would_b": wb, "changes_b": sorted(k for k in wb if wb[k] != d[k])}
        emit("brain", LABEL, role="system", text=str(text or "")[:160], extra=extra)
        return extra
    except Exception as e:  # noqa: BLE001 — a shadow never breaks a turn
        logger.debug(f"commission: shadow not emitted — {e!r}")
        return None


def _peek(brief):
    try:
        from nucleo import jev
        return jev.peek(brief)
    except Exception:  # noqa: BLE001
        return None
