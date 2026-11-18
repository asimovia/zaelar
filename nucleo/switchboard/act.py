"""What a switchboard decision DOES to the process it named: deliver his words, decide the act it held, or stop it.

`route.take` decides; these are the doors it uses — the question's answer door (`worker_api.answer_soon`), the running
worker's relay (`dispatch.relay_his_words`) and the row's ONE cancel door (`dispatch.control.cancel_row`).
"""
from __future__ import annotations

from loguru import logger

from nucleo.switchboard import board as _board

YES, NO, OTHER, FRAGMENT, STOP, STOP_ALL = "yes", "no", "other", "fragment", "stop", "stop_all"
#: How long the turn waits for the sessions' loop to run his stop before it says nothing was stopped.
STOP_S = 2.0


def waits_on_his_yes(p: dict) -> bool:
    """Does this process wait on a yes/no about an act it retained (a send's confirmation, a card's consent)?"""
    if p["state"] != _board.WAITING:
        return False
    if str(p.get("ask_id") or "").startswith(_board.STEP):      # a step parked on his OK asks exactly that
        return True
    try:
        from nucleo.circuit import asker
        return asker.kind_of(asker.artefact(p["key"])) == asker.KIND_CONSENT
    except Exception as e:  # noqa: BLE001
        logger.debug(f"switchboard: the question's kind unread — {e!r}")
        return False


def deliver(p: dict, text: str, kind: str = OTHER) -> bool:
    """Hand `text` to process `p` as he said it: its open question takes it as the answer — a plain yes or no decides
    its retained act at once, as the screen's button does; anything else resumes the task with his words — and a
    running worker takes it as his next words."""
    if str(p.get("ask_id") or "").startswith(_board.STEP):      # his yes or no to a parked step goes to THAT step
        if kind in (YES, NO):
            from nucleo.request.consent_ask import yes_no
            from widgets.navegador import tasks as _nav
            _nav.answer(str(p["ask_id"])[len(_board.STEP):], yes_no()[0 if kind == YES else 1])
            return True
        from nucleo import dispatch as _d      # anything else is for the process that runs it
        return bool(p.get("dispatch")) and bool(_d.relay_his_words(p["dispatch"], text))
    if p["state"] == _board.WAITING and p.get("ask_id"):
        if kind == OTHER and _absorbed(p, text):     # an errand parked on his yes takes what he adds; its question stands
            return True
        from nucleo.cli import worker_api
        choice = {YES: 0, NO: 1}.get(kind)          # the caller passes yes/no only for a process waiting on a yes
        return bool(worker_api.answer_soon(p["ask_id"], text, choice))
    if p.get("dispatch"):
        from nucleo import dispatch as _d
        return bool(_d.relay_his_words(p["dispatch"], text))     # THE door for his sentence into a running errand
    return False


def _absorbed(p: dict, text: str) -> bool:
    """A process parked at its START question («shall I?») and words of his that are neither a yes nor a no: they are
    part of what he asked — a detail, a change — and travel with the errand when his yes relaunches it
    (`confirm.absorb_refinement`). Nothing new is started for them and the question is not asked again."""
    try:
        from nucleo.circuit import asker
        from nucleo.dispatch import confirm as _dc
        a = asker.artefact(p["key"]) or {}
        if (a.get("retained") or {}).get("kind") != "start":
            return False
        return bool(_dc.absorb_refinement(str(a.get("task_id") or ""), text))
    except Exception as e:  # noqa: BLE001 — unread: the question's own answer door takes the words
        logger.debug(f"switchboard: the parked errand did not take the words — {e!r}")
        return False


def stop(procs: list[dict]) -> list[str]:
    """His stop for these processes, through the row's ONE cancel door (`dispatch.control.cancel_row`, the screen's
    button): a running or queued worker is signalled and killed past its grace, a waiting question is closed, the row
    ends `cancelled`. Returns the keys it ended. The door runs on the loop that OWNS the sessions (the turn may be on
    another one): a session stopped from a foreign loop is not stopped."""
    import asyncio

    from nucleo import dispatch
    owner = getattr(dispatch, "_LOOP", None)
    try:
        here = asyncio.get_running_loop()
    except RuntimeError:
        here = None
    if owner is None or owner is here or not owner.is_running():
        return _stop_here(procs)

    async def _on_owner() -> list[str]:
        return _stop_here(procs)
    try:
        return asyncio.run_coroutine_threadsafe(_on_owner(), owner).result(timeout=STOP_S)
    except Exception as e:  # noqa: BLE001 — unreached: nothing is claimed, and Flash takes the turn
        logger.warning(f"switchboard: the stop did not reach the sessions' loop — {e!r}")
        return []


def _stop_here(procs: list[dict]) -> list[str]:
    from nucleo.dispatch import control
    ended = []
    for p in procs:
        try:
            if p["key"].startswith("session:"):                       # a live session with no row yet
                ok = control.cancel_session(p["dispatch"], reason="operator")
            else:
                ok = control.cancel_row(p["key"], outcome="stopped by his word") == "cancelled"
            if ok:
                ended.append(p["key"])
        except Exception as e:  # noqa: BLE001 — one process that would not stop never keeps the others running
            logger.warning(f"switchboard: could not stop {p['key']} — {e!r}")
    return ended


def _line(key: str, about: str = "") -> str:
    """The line he hears for what his words did, WORDED for him (`nucleo/wording`): the language's own line is the
    example and the last resort, never the sentence said every time. Blocking — call it off the loop."""
    from i18n import langs
    from nucleo import wording
    lang = langs.current_language()
    plain = str(getattr(lang, key, "") or getattr(lang, "answer_taken", "") or "")
    fact = wording.FACTS.get(key, "")
    return wording.word(fact, examples=(plain,), about=about, fallback=plain) if fact else plain


def line_key(p: dict, kind: str) -> str:
    """WHICH fact he is told for a chunk a process took: his yes to a send (it is going), his no (it is not), his yes
    or no to any other act it held, or that his words were taken. Read BEFORE the answer clears what the row held."""
    key = "answer_taken"
    if kind in (YES, NO):
        leaves = False
        try:
            from nucleo.circuit import asker
            from nucleo.request import send_receipt
            leaves = send_receipt.is_send((asker.artefact(p["key"]).get("retained") or {}))
        except Exception as e:  # noqa: BLE001
            logger.debug(f"switchboard: the retained act unread — {e!r}")
        key = {(YES, True): "send_going", (NO, True): "send_not_sent",
               (YES, False): "work_started", (NO, False): "confirm_cancelled"}[(kind, leaves)]
    return key


def line_of(p: dict, kind: str) -> str:
    """The ONE line he hears for a chunk a process took, worded for him."""
    return _line(line_key(p, kind), str(p.get("title") or ""))
