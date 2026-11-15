"""nucleo/play/run.py — the driver: it walks ONE programme from its first step to its report.

The driver holds no knowledge of any action. It is handed the HANDS of the action — the callables that do each step —
and calls each one only in its step, in the table's order, each under the step's deadline:

    resolve(state)  → {"slots": {name: {value, source}}}  or  {"missing": "<slot>"}  or  {"fail": "<why>"}
    answer(state, slot) → {"slots": {...}} (his answer)  or  None (he said no)
    consent(state)  → "yes" | "no" | "change"
    execute(state)  → {"ok": True, ...} | {"ok": False, "error": ...}     (the executor's own return)
                      {"parked": True}: the executor waits on him (its own question); the walk stops here, with
                      no report, and a later `run` over the same state goes on from this step
    look(state)     → True (the declared end state is there) | False | None (it could not be read)
    say(kind, value, state)                                                (the ONE mouth of this programme)

`look` is reached only through `executed`, so the end state is never read before the executor returned; `say("report")`
only with an outcome. A hand that raises is that step's failure, never a skipped step.
"""
from __future__ import annotations

import asyncio
import time

from loguru import logger

from . import programme as _programme
from . import state as _st


async def _call(fn, limit, *args):
    """One hand under its step's deadline: (`value`, "") or (None, "timeout" | "raised")."""
    try:
        out = fn(*args)
        if asyncio.iscoroutine(out):
            out = await asyncio.wait_for(out, timeout=limit)
        return out, ""
    except asyncio.TimeoutError:
        return None, "timeout"
    except Exception as e:  # noqa: BLE001 — a hand that raises fails its step; the programme still ends and reports
        logger.warning(f"play/run: {getattr(fn, '__name__', fn)!r} raised — {e!r}")
        return None, "raised"


async def run(state: dict, hands, *, clock=time.monotonic, on_move=None) -> dict:
    """Walk `state` to `reported`. Returns the final state; `state["outcome"]` is what happened."""
    limits = _st._TABLE["deadline_s"]

    def move(event: str, slots: dict | None = None) -> None:
        nonlocal state
        m = _st.advance(state, event, now=clock(), slots=slots)
        if m.ok and on_move:
            on_move(event, m.state)
        state = m.state

    async def speak(kind: str, value: str = "") -> None:
        nonlocal state
        m = _st.say(state, kind, value, now=clock())
        if m.ok:
            state = m.state
            await _call(hands.say, None, kind, value, state)
            if on_move and kind == "report":
                on_move("report", state)

    if state["step"] == _st.FIRST:
        move("start")
    asked = ""
    while state["step"] != _st.LAST:
        step = state["step"]
        if step == "resolving":
            got, bad = await _call(hands.resolve, limits.get(step), state)
            got = got if isinstance(got, dict) else {}
            if bad == "timeout":
                move("timeout")
            elif bad or got.get("fail"):
                move("fail")
            elif got.get("missing"):
                asked = str(got["missing"])
                move("missing")
            else:
                move("resolved", got.get("slots"))
        elif step == "asking":
            await speak("ask", asked)
            got, bad = await _call(hands.answer, limits.get(step), state, asked)
            if bad == "timeout":
                move("timeout")
            elif bad or not isinstance(got, dict):
                move("no")
            else:
                move("answer", got.get("slots"))
        elif step == "confirming":
            await speak("confirm", f"{state['wid']}:{state['action']}")
            got, bad = await _call(hands.consent, limits.get(step), state)
            move("timeout" if bad == "timeout" else got if got in ("yes", "change") and not bad else "no")
        elif step == "executing":
            await speak("announce")
            got, bad = await _call(hands.execute, limits.get(step), state)
            if isinstance(got, dict) and got.get("parked"):
                return state
            ok = isinstance(got, dict) and got.get("ok") is not False and not got.get("error")
            move("timeout" if bad == "timeout" else "returned" if ok and not bad else "error")
        elif step == "executed":
            move("check")
        elif step == "verifying":
            landed = None
            if state["programme"].get("verify") == _programme.CHECK:
                landed, bad = await _call(hands.look, limits.get(step), state)
                if bad == "timeout":
                    move("timeout")
                    continue
                landed = None if bad else landed
            move(_programme.verdict_event(state["programme"], landed))
        elif step in _st.ENDS:
            await speak("report", state["outcome"])
        else:  # a step the driver does not know cannot loop for ever
            logger.error(f"play/run: no hand for step {step!r}")
            break
    return state
