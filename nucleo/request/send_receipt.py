"""nucleo/request/send_receipt.py — his yes sent it; the connector says what happened; he hears ONE final line (V2-931).

Measured on his engine (2026-11-17, 23:07): the send was queued at :52, a worker looked 2 s later and said «it is
queued, not confirmed yet», the connector's receipt landed at :56, and the doubtful line was spoken at :57 — after the
card already showed it sent. A final line said before the receipt can only be a guess.

So the engine itself follows the order it just queued (`follow`): it reads the connector's own receipt — the card's
declared end state for «sent», the order's outbox row for «failed» and its reason — and says the line from it:
«Message sent.», or «could not be sent: why». With no receipt inside `RECEIPT_S` it says ONCE that it is not confirmed
yet, keeps looking, and tells him when it lands. The task's row ends with the verdict the line says. No session is
resumed for any of it.
"""
from __future__ import annotations

import asyncio
import time

from loguru import logger


def _note(e: Exception) -> None:
    logger.debug(f"send_receipt: {type(e).__name__}: {e}")


#: How long the final line waits for the connector's own receipt before it says, once, that it is not confirmed yet.
RECEIPT_S = 30.0
#: How long a late receipt is still followed (and told when it lands).
LATE_S = 600.0
POLL_S = 1.0
_following: set = set()
#: The rows whose send the engine took to its receipt (now or earlier): the receipt is their verdict. Bounded.
_taken: dict = {}


def is_send(retained: dict | None) -> bool:
    """Is the act a question retained one that LEAVES the machine (a card's send)?"""
    try:
        from nucleo import on_his_behalf as _ob
        from nucleo.workers import exit_gate
        if str((retained or {}).get("action") or "") != "widget_data":
            return False
        wid, act, _inner = _ob._resolve((retained or {}).get("payload") or {})
        return bool(wid and act) and exit_gate.leaves(wid, act)
    except Exception as e:  # noqa: BLE001
        _note(e)
        return False


def family(wid: str, action: str, payload: dict | None) -> str:
    """The lines of this leaving act (`nucleo/wording.LINES`): "send" for a message, "act" for anything else — read
    off its declared event type (`exit_risk.family`), so a group created is never told as «message sent»."""
    from nucleo.workers import exit_risk
    return exit_risk.family(wid, action, payload)


def family_of(retained: dict | None) -> str:
    """`family` of the act a question retained; "" when it does not leave the machine."""
    if not is_send(retained):
        return ""
    from nucleo import on_his_behalf as _ob
    return family(*_ob._resolve((retained or {}).get("payload") or {}))


#: The row slot of the leaving acts this request already took to their receipt: `[{terms, at}]`.
LANDED = "landed_acts"


def _terms(uid: str, wid: str, action: str, payload: dict | None) -> str:
    """The identity of one leaving act of a request: the call and the text the row last wrote for it."""
    from nucleo.circuit import ask_trace, ledger
    text = str((ledger.store().artifact_get(uid, "written_text") or {}).get("text") or "") if uid else ""
    call = {k: v for k, v in dict(payload or {}).items() if k != "playbook"}     # the door's own mark is not a term
    return ask_trace.terms_of({"retained": {"widget": wid, "action": action, "payload": call, "text": text}})


def landed(uid: str, wid: str, action: str, payload: dict | None) -> bool:
    """Did THIS request already take this very act to its receipt? Then it is done: the exit door never asks about it
    again nor runs it twice (a session relaunched or resumed after its send repeats the call; measured 2026-11-18: a
    message already sent kept a «shall I send it?» open for forty minutes, and his next order fell into it)."""
    try:
        from nucleo.circuit import ledger
        t = _terms(uid, wid, action, payload)
        return bool(uid and t) and any(r.get("terms") == t for r in (ledger.store().artifact_get(uid, LANDED) or []))
    except Exception as e:  # noqa: BLE001 — unread: the door decides as before
        _note(e)
        return False


def _mark_landed(uid: str, wid: str, action: str, payload: dict | None) -> None:
    try:
        from nucleo.circuit import ledger
        rows = list(ledger.store().artifact_get(uid, LANDED) or [])
        rows.append({"terms": _terms(uid, wid, action, payload), "at": time.time()})
        ledger.store().artifact_put(uid, LANDED, rows[-8:])
    except Exception as e:  # noqa: BLE001
        _note(e)


def end_state(wid: str, action: str, payload: dict | None):
    """The send's declared end state (its outbox row as sent), rendered BEFORE the act runs — its baseline is what
    the card showed before. None when the act declares none."""
    try:
        from nucleo.circuit import spec
        return spec.render(wid, action, payload) or None
    except Exception as e:  # noqa: BLE001
        _note(e)
        return None


def _ref_of(result) -> str:
    """The order's own reference in the card's answer (its outbox row is keyed by it), or ""."""
    r = result if isinstance(result, dict) else {}
    inner = r.get("result") if isinstance(r.get("result"), dict) else {}
    for d in (r, inner, inner.get("data"), inner.get("result")):
        if isinstance(d, dict) and d.get("ref"):
            return str(d["ref"])
    return ""


def receipt(wid: str, ref: str, done_when) -> tuple[str, str]:
    """What the connector has said about this order: `("sent", "")`, `("failed", why)` or `("", "")` (nothing yet).
    Sent is the card's own declared end state; failed is the order's outbox row saying so."""
    from nucleo.circuit import verify
    try:
        if done_when and verify.check(done_when) is True:
            return "sent", ""
    except Exception as e:  # noqa: BLE001
        _note(e)
    try:
        view = verify.card_view(wid) or {}
        for row in view.get("outbox") or []:
            if isinstance(row, dict) and ref and str(row.get("ref") or "") == ref:
                state = str(row.get("state") or "")
                if state == "sent":
                    return "sent", ""
                if state == "failed":
                    return "failed", str(row.get("reason") or "")
    except Exception as e:  # noqa: BLE001
        _note(e)
    return "", ""


async def _say(uid: str, stage: str, key: str, **fmt) -> None:
    """One line of the send, by the out-of-turn mouth, once per stage of that send — about what he asked for."""
    try:
        from nucleo import wording
        from nucleo.circuit import ledger
        from nucleo.pulse import notices
        row = ledger.store().task_get(uid) or {}
        line = await wording.said(key, about=str(row.get("title") or row.get("goal") or "")[:200], **fmt)
        if line:
            await notices.notify("zaelar", line, key=f"send:{uid}:{stage}", kind="info")
    except Exception as e:  # noqa: BLE001
        _note(e)


async def follow(uid: str, wid: str, action: str, payload: dict | None, result, done_when, *,
                 receipt_s: float | None = None, late_s: float | None = None, poll_s: float | None = None) -> str:
    """The send was queued on his yes: wait for the connector's own receipt and say the ONE final line from it —
    «Message sent.» when it lands, «could not be sent: why» when it fails; past `receipt_s` with neither, say once that
    it is not confirmed yet and tell him when it is. The task's row ends with the same verdict the line says. Returns
    `sent` · `failed` · `unconfirmed`."""
    from nucleo import circuit
    receipt_s = RECEIPT_S if receipt_s is None else receipt_s
    late_s = LATE_S if late_s is None else late_s
    poll_s = POLL_S if poll_s is None else poll_s
    ref, t0, told_late = _ref_of(result), time.monotonic(), False
    from nucleo import wording
    fam = family(wid, action, payload)
    _following.add(uid)
    _taken[uid] = time.time()
    for old in sorted(_taken, key=_taken.get)[:max(0, len(_taken) - 64)]:
        _taken.pop(old, None)
    try:
        while True:
            state, why = receipt(wid, ref, done_when)
            if state == "sent":
                _mark_landed(uid, wid, action, payload)
                await _say(uid, "sent", wording.line(fam, "done"))
                circuit.settle(row=uid, verdict="met", outcome="the connector confirmed the send")
                return "sent"
            if state == "failed":
                await _say(uid, "failed", wording.line(fam, "failed"), why=why)
                circuit.settle(row=uid, verdict="unmet", outcome=f"the send failed: {why}"[:300])
                return "failed"
            waited = time.monotonic() - t0
            if waited >= late_s:
                circuit.settle(row=uid, verdict="unverifiable", outcome="no receipt from the connector")
                return "unconfirmed"
            if waited >= receipt_s and not told_late:
                told_late = True
                await _say(uid, "late", wording.line(fam, "late"))
            await asyncio.sleep(poll_s)
    except Exception as e:  # noqa: BLE001 — a watcher that broke leaves the row to the circuit's own close
        logger.warning(f"send_receipt: the receipt of {uid} was not followed — {e!r}")
        return "unconfirmed"
    finally:
        _following.discard(uid)


def follow_soon(uid: str, wid: str, action: str, payload: dict | None, result, done_when) -> None:
    """Schedule `follow` on the running loop (the answer door never waits for a connector)."""
    try:
        task = asyncio.get_running_loop().create_task(follow(uid, wid, action, payload, result, done_when))
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)
    except RuntimeError as e:
        _note(e)


_tasks: set = set()


async def run_followed(rec, action: str, payload: dict, run) -> dict:
    """A send that runs with NO question — his order over a draft he had seen was the yes: the same end as a confirmed
    one. Its end state is on the row and the engine follows it to the connector's receipt and says the final line."""
    from nucleo import on_his_behalf as _ob
    wid, act, inner = _ob._resolve(payload or {}) if action == "widget_data" else ("", "", {})
    dw = end_state(wid, act, inner) if wid and act else None          # its baseline: BEFORE the act
    result = await run()
    if wid and act and isinstance(result, dict) and result.get("ok"):
        uid = str(getattr(rec, "uid", "") or "")
        record_end_state(uid, wid, act, inner, done_when=dw)
        follow_soon(uid, wid, act, inner, result, dw)
    return result


def followed(uid: str) -> bool:
    """Is this task's send being followed to its receipt right now? (Its final line is the engine's.)"""
    return uid in _following


def owns_the_verdict(uid: str) -> bool:
    """Did the engine take this task's send to the connector's receipt (now, or it already landed)? Then the RECEIPT
    is the task's verdict and ends its row: the session's own close never reads its goal as unmet nor relaunches it.
    Measured 2026-11-18: a session ended two seconds before its receipt, was judged «unmet», relaunched on another
    model, re-verified a message that had been sent and said so a second time — twice."""
    return bool(uid) and (uid in _following or uid in _taken)


def record_end_state(uid: str, wid: str, action: str, payload: dict | None, said: str = "", *, done_when=None) -> None:
    """The send ran: its declared end state (the outbox row) goes on the task's row, where `bridge act verify` and the
    task's close read it. Not owed to the circuit's own tick: `follow` reads the receipt and ends the row."""
    if not uid:
        return
    try:
        from nucleo.circuit import spec
        dw = done_when or spec.render(wid, action, payload)
        if not dw:
            return
        e = spec.open(dw, text=said, source="send", widget=wid, action=action, task_id=uid)
        if e is not None:
            spec.withdraw(e)
            spec.persist(uid, e)
    except Exception as e:  # noqa: BLE001
        _note(e)
