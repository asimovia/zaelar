"""nucleo/request/sign_in_wait.py — an errand parked on HIS sign-in ends as a WAIT, never as a result (V2-868 D3).

Measured on the operator's console: an errand driving a seller's page landed on the sign-in, its worker kept going,
wrote its own status («login pending», a daily hour) as a finding on the results sheet, and the circuit judged and
relaunched it. A sign-in the engine cannot do is not something the worker can finish — it is his move.

So when the browser task an errand drives reaches `awaiting_login` (a window waits for him) or `blocked: no_window`
(no window can reach him), THIS is the errand's end state for now:

  · ONE question through THE asker (`nucleo/cli/worker_api_asks._register_ask` → `nucleo/circuit/asker`): the row
    waits on him (`state=waiting`, `user_answer`), the question goes on screen, in his language (`errand.sign_in.*`);
  · the worker STOPS — parked, so its ending writes nothing (no breadth judge, no harness verdict, no delivery);
  · on his sign-in (`auth_memory.record_session_established`, the probe-confirmed fact of the owner's login flow)
    the SAME row resumes by id, through the same answer path his words would take;
  · the line for a request that came from the PHONE (V2-792 screens) says the window opens on a computer — product
    data, never offered as something the phone can do.

Keyed by the browser task id the errand drives (`rec.nav_task`); nothing here reads his words.
"""
from __future__ import annotations

import asyncio
import time

from loguru import logger

#: A sign-in wait is an ordinary question to him (`ask_user`): nothing runs on his yes. Its artefact is tagged
#: `sign_in` with the browser task it waits on, which is how his confirmed sign-in finds it.
ACTION = "ask_user"
#: How long after his login wait ended a confirmed sign-in still resumes the errand that waited on it.
RESUME_WINDOW_S = 120.0

#: nav task id → when its login wait ended without a block (a sign-in to be confirmed by `established`).
_ENDED: dict[str, float] = {}


def _note(e: BaseException) -> None:
    import sys
    logger.debug(f"sign_in_wait: {sys._getframe(1).f_code.co_name} — {type(e).__name__}: {e}")


def _record_driving(nav_tid: str):
    """The live worker record that drives browser task `nav_tid`, or None."""
    if not nav_tid:
        return None
    try:
        from nucleo import dispatch
        for rec in list(dispatch._SESSIONS.values()):
            if str(getattr(rec, "nav_task", "") or "") == nav_tid and getattr(rec, "status", "") in ("queued", "running"):
                return rec
    except Exception as e:  # noqa: BLE001
        _note(e)
    return None


def _on_phone(rec) -> bool:
    """Did the request come from his phone (V2-792: the screen that commissioned it)?"""
    try:
        from voice import screens
        return screens.surface(screens.task_origin(getattr(rec, "task_id", ""))) == "phone"
    except Exception as e:  # noqa: BLE001
        _note(e)
        return False


def question(rec, *, blocked: str = "") -> str:
    """The one line he is asked, in his language: a window waits for him; or none can reach him — from the phone
    the window opens on a computer, elsewhere it needs the daemon."""
    from i18n import runtime as _rt
    if _on_phone(rec):
        return _rt.text("errand.sign_in.phone", default="From your phone I can't open a sign-in window: open your "
                                                          "agent on a computer and I'll carry on from there.")
    if blocked:
        return _rt.text("errand.sign_in.no_window", default="I need you to sign in, and I can't open a window for "
                                                            "you from here. I'll wait here and carry on once you do.")
    return _rt.text("errand.sign_in.window", default="Sign in in the window I just opened and I'll carry on by "
                                                     "myself.")


def park(nav_tid: str, *, blocked: str = "") -> str:
    """The errand that drives `nav_tid` waits on his sign-in: one question, the row waits, the worker stops. Returns
    the question's id ("" when no live errand drives that browser task, or it already waits). Never raises."""
    try:
        rec = _record_driving(nav_tid)
        if rec is None or getattr(rec, "parked", False) or str(getattr(rec, "waiting_on", "") or ""):
            return ""
        _ENDED.pop(nav_tid, None)
        from nucleo.cli import worker_api_asks
        ask_id = worker_api_asks._register_ask(rec, question(rec, blocked=blocked), action=ACTION)
        from nucleo.circuit import asker
        uid = str(getattr(rec, "uid", "") or "")
        art = asker.artefact(uid)
        if art:
            asker.keep(uid, {**art, "nav_task": nav_tid, "sign_in": True})
        _event("🔐 errand waits for his sign-in — worker stopped, nothing delivered", rec, nav_tid, blocked)
        _stop_soon(rec)
        return ask_id
    except Exception as e:  # noqa: BLE001
        logger.warning(f"sign_in_wait: errand on {nav_tid} not parked: {type(e).__name__}: {e}")
        return ""


def _stop_soon(rec) -> None:
    """End the worker's PROCESS without cancelling its errand: it is parked, so its ending writes nothing and his
    sign-in resumes it by id (the same path an answered question takes)."""
    session = getattr(rec, "session", None)
    backend = getattr(session, "_b", None)
    if backend is None:
        return

    async def _go() -> None:
        try:
            await backend.stop(grace=3.0)
        except Exception as e:  # noqa: BLE001
            _note(e)
    try:
        asyncio.get_running_loop().create_task(_go())
    except RuntimeError:
        try:
            from nucleo import dispatch
            loop = getattr(dispatch, "_LOOP", None)
            if loop is not None:
                asyncio.run_coroutine_threadsafe(_go(), loop)
        except Exception as e:  # noqa: BLE001
            _note(e)


def ended(nav_tid: str) -> None:
    """His login wait on `nav_tid` ended without a block — a sign-in or an abandoned window. Nothing resumes until
    the owner CONFIRMS the sign-in (`established`): an abandoned window would walk the errand back into the wall."""
    if nav_tid:
        _ENDED[str(nav_tid)] = time.time()


def established(site: str = "") -> int:
    """The owner confirmed a sign-in: every errand parked on a login wait that just ended resumes, by id, through the
    answer path. Returns how many resumed. Never raises."""
    now, n = time.time(), 0
    fresh = {t for t, at in list(_ENDED.items()) if now - at <= RESUME_WINDOW_S}
    _ENDED.clear()
    if not fresh:
        return 0
    try:
        from nucleo.cli import worker_api_asks
        from nucleo.circuit import asker
        for a in worker_api_asks.open_asks():
            art = asker.artefact(a["task_id"])
            if art.get("sign_in") and str(art.get("nav_task") or "") in fresh:
                _answer_soon(a["ask_id"], _signed_in_line(site))
                n += 1
    except Exception as e:  # noqa: BLE001
        _note(e)
    return n


def _signed_in_line(site: str) -> str:
    from i18n import runtime as _rt
    line = _rt.text("errand.sign_in.done", default="I've signed in{site} — carry on where you stopped.")
    return line.replace("{site}", f" ({site})" if site else "")


def _answer_soon(ask_id: str, text: str) -> None:
    from nucleo.cli import worker_api_answer

    async def _go() -> None:
        try:
            await worker_api_answer.answer(ask_id, text)
        except Exception as e:  # noqa: BLE001
            _note(e)
    try:
        asyncio.get_running_loop().create_task(_go())
    except RuntimeError:
        try:
            from nucleo import dispatch
            loop = getattr(dispatch, "_LOOP", None)
            if loop is not None:
                asyncio.run_coroutine_threadsafe(_go(), loop)
        except Exception as e:  # noqa: BLE001
            _note(e)


def _event(label: str, rec, nav_tid: str, blocked: str) -> None:
    try:
        from voice.observer import emit
        emit("task", label, role="system",
             extra={"id": str(getattr(rec, "task_id", "") or ""), "uid": str(getattr(rec, "uid", "") or ""),
                    "nav_task": nav_tid, "cat": "circuit", **({"blocked": blocked} if blocked else {})})
    except Exception as e:  # noqa: BLE001
        _note(e)


def _reset_for_tests() -> None:
    _ENDED.clear()
