"""How many widget data-ops ONE turn runs, and which (V2-391) — one decision shared by both channels.

«ONE per turn» blocked a DUPLICATED `add_meeting` and an ENUMERATION of actions, but two pasted links are two
`add`s (2026-08-27 13:36). So: same widget + same action + different payloads run; an exact duplicate collapses;
another action on the same widget is dropped. Only FAST ops reach here (irreversible ones are CONFIRM).
"""
from __future__ import annotations


import json as _json
import time

from nucleo.acts import op_receipt as _receipt
from nucleo.request import refusal_line as _rline
from nucleo.circuit import compose as _outcome

#: Data-ops per turn. Five pasted links is a request; fifty is a broken model.
MAX_DATA_OPS = 5
#: How long the turn's mouth waits for an op's answer (`nucleo/turn/reply.WAIT_S`): a refusal later than this is
#: said out of turn, never by nobody.
_MOUTH_WAIT_S = 4.0


def _ident(args: dict) -> tuple[str, str, str]:
    """A data-op's identity: widget + action + payload, comparable."""
    a = args if isinstance(args, dict) else {}
    pl = a.get("payload") if isinstance(a.get("payload"), dict) else {}
    return (str(a.get("widget_id") or "").strip().lower(),
            str(a.get("action") or "").strip(),
            _json.dumps(pl, sort_keys=True, ensure_ascii=False, default=str))


def _named(args: dict) -> set[str]:
    """What a data-op names as its object: the non-empty values of its payload, comparable."""
    pl = (args or {}).get("payload") if isinstance((args or {}).get("payload"), dict) else {}
    return {str(v).strip().lower() for v in pl.values() if str(v if v is not None else "").strip()}


# V2-603 — a FAILED data-op must correct the claim already spoken. V2-851 F2: the turn's own mouth says it
# (`nucleo/turn/reply.of_op`, from the card's `say` through `refusal_line.speakable`), ONE line, and no model runs
# again to correct the call. Only a refusal that lands after the mouth stopped waiting is said out of turn, once, on
# the request's row. The correction note, the 🔔 and the corrected re-call went (`corrected_retry`).

#: Late failures already said (wid:action:error → ts): a card retrying on a timer is not a monologue.
_RECENT_FAILURES: dict[str, float] = {}
_FAILURE_COOLDOWN_S = 90.0


def _dedup(key: str, now: float) -> bool:
    """True if this exact failure was announced within the cooldown. Prunes as it goes."""
    for k, ts in list(_RECENT_FAILURES.items()):
        if now - ts > _FAILURE_COOLDOWN_S:
            _RECENT_FAILURES.pop(k, None)
    if key in _RECENT_FAILURES:
        return True
    _RECENT_FAILURES[key] = now
    return False


async def report_failure(wid: str, action: str, res: dict, *, late: bool = False, row: str = "") -> bool:
    """A FAST data-op that came back `ok: False`, on the timeline. Its line belongs to the turn's mouth; `late` (it
    answered after the mouth stopped waiting, `reply.WAIT_S`) → said once by the out-of-turn mouth on `row`. Returns
    True when it was said here. Best-effort: runs in the op's detached task, so it never raises."""
    # V2-743 — `error` counts too (2026-09-21, bcd4aba1: a timeout result had no `ok` and was never told); a POOL
    # TIMEOUT does not — the hook keeps running, so `op_receipt` witnesses it instead.
    if not isinstance(res, dict):
        return False
    if _receipt.is_pool_timeout(res) or not _receipt.failed(res):
        return False
    detail = str(res.get("message") or res.get("error") or "").strip()
    if not detail:
        return False
    # V2-652 — `message` is for the operator, `error` for the MODEL (2026-09-10, 7f77e2cc: a retry instruction was
    # spoken aloud). A bare `error` is said as the generic refusal, never read out.
    speakable = _rline.speakable(wid, res)          # the widget's `say` (bundle) or its cleaned `message`
    wid = (wid or "").strip().lower()
    action = (action or "").strip()
    told = False
    if late and not _dedup(f"{wid}:{action}:{detail}", time.time()):
        try:
            from nucleo.pulse import notices
            line = await _rline.said(wid, res)
            if line:
                await notices.notify(wid.split("::")[0].capitalize(), line, task_id=row,
                                     key="" if row else f"refused:{wid}:{action}:{int(time.time())}", kind="info")
                told = True
        except Exception:  # noqa: BLE001
            pass
    try:
        from voice.observer import emit
        emit("widget", "🩹 data-op fallida → dicha fuera del turno" if told
             else "🩹 data-op fallida → la dice la boca del turno",
             text=detail[:160], extra={"id": wid, "action": action, "told": told, "late": late,
                                       "spoken": bool(speakable), "is_error": True})
    except Exception:
        pass
    return told


def _failed_line() -> str:
    try:
        from i18n import langs as _lg
        return str(getattr(_lg.current_language(), "op_failed", "") or "")
    except Exception:  # noqa: BLE001
        return ""


async def _say_it_did_not_run(wid: str, action_name: str, exc: BaseException, *, seal=None, row: str = "") -> dict:
    """The op raised before any widget answered: settle its row, forget it as done, and SAY so (V2-778 F0-4).
    Returns the failed result so a caller waiting on it reads a refusal, never an empty success."""
    res = {"ok": False, "message": _failed_line(), "error": f"{type(exc).__name__}: {exc}"[:200]}
    try:
        from voice.observer import emit
        emit("brain", "❌ data-op no se ejecutó", role="system", text=f"{wid}:{action_name} — {res['error']}",
             extra={"id": wid, "action": action_name, "is_error": True, "cat": "flash"})
    except Exception:  # noqa: BLE001
        pass
    if row:
        try:
            from nucleo import circuit as _circuit
            _circuit.settle(row=row, verdict="unmet", outcome=res["error"])
        except Exception:  # noqa: BLE001
            pass
    if callable(seal):
        try:
            seal(False)
        except Exception:  # noqa: BLE001
            pass
    try:
        await report_failure(wid, action_name, res)
    except Exception:  # noqa: BLE001
        pass
    return res


async def dispatch_and_report(wid: str, action_name: str, payload: dict, *, seal=None, receipt: bool = False,
                              text: str = "", row: str = ""):
    """Dispatch a widget data-op AND announce it if it failed (V2-603). Never raises. `seal` (V2-707 F0) gets
    whether the op HAPPENED, so a refused mutation is never remembered as executed by the anti-drag guard. `row` —
    the waiting row this op resumes (V2-851: an answered question re-runs its act on its own row)."""
    import widgets
    from nucleo.request import inline_ask as _ia
    handed = row         # a row the CALLER resumes: no turn of his is left to say its failure
    if not row:          # V2-851 — the act a waiting row retained, called again with a candidate: it is HIS answer
        row, _dup = _ia.claim(wid, action_name, payload or {})
        if _dup:
            return {"ok": True, "already": True, "row": row}    # his answer already ran exactly this act
    from nucleo.acts import worker_note_relay as _relay
    if (_to := _relay.relay(wid, action_name, text)):    # a worker's own note: his words go to it (2026-10-14)
        return {"ok": True, "relayed_to": _to}
    # V2-903 P1-1 — what reaches the card's door is what he approved or dictated, byte for byte: nothing rewrites
    # an act between his yes and its exit (CRIT-T2e). The language is the composer's job, before anything is shown.
    # V2-743 — the witness is read BEFORE the op, and only on the `receipt` (confirmed irreversible) path.
    before = await _receipt.read_signature(wid) if receipt else ""
    # V2-776 L1 — the declared postcondition (`done_when`) is opened BEFORE the op, attested after.
    try:
        from nucleo.circuit import spec as _spec
        _spec_entry = _spec.open_for_action(wid, action_name, payload, text=text)
    except Exception:  # noqa: BLE001
        _spec_entry = None
    # V2-776 M1 — the request is a ROW, opened by its first op (`nucleo/request/model.py`).
    try:
        from nucleo.request import model as _rq
        _row = row or _rq.opened(wid, action_name, text=text)
    except Exception:  # noqa: BLE001
        _row = row
    if _spec_entry is not None and _row:
        _spec_entry["row"] = _row
        _spec_entry["turn"] = _rq.current()      # his words, for the correction the circuit may have to say
        # V2-778 F3-26 — persisted so a restart can still judge the row; not as `task_id` (that means a worker owns it).
        _spec.persist(_row, _spec_entry)
    # V2-769 — this create's sentence completes an earlier create's piece: revert that row (`circuit/compose.py`).
    if (_prev := _outcome.superseded(wid, action_name, text)):
        await _revert(wid, _prev)
    from nucleo.request import ending as _ending
    _hold = _ending.hold(wid, action_name, _row) if _row else ""   # V2-851 F2e — does this op end the request?
    if _hold and _spec_entry is not None:
        _spec_entry["row"] = ""                  # its ending is not the pulse's to write on the request's row
    async def _run(w, a, p):
        return await widgets.dispatch_tag("widget.data", {"id": w, "data": {"action": a, "payload": p or {}}})
    _t0 = time.monotonic()
    try:
        res = await _run(wid, action_name, payload)
    except Exception as e:  # noqa: BLE001 — V2-778 F0-4: an op that raised is said, never left behind «Done.»
        return await _say_it_did_not_run(wid, action_name, e, seal=seal, row=_row)
    # Late = no turn of his is left to say it: it answered after the mouth stopped waiting, or its caller resumes a
    # row out of turn. A row this op CLAIMED as his answer is inside the run that called it, which says the refusal
    # from its receipt — a second line out of turn would say the same failure twice.
    _late = time.monotonic() - _t0 > _MOUTH_WAIT_S or bool(handed)
    _ia.reached(wid, action_name, res, _row)     # V2-851 — whom it reached: a waiting row's re-run never repeats it
    _outcome.remember(wid, action_name, text, res)
    _refused = bool(_receipt.failed(res)) if isinstance(res, dict) else False
    _attested = None
    if _spec_entry is not None:
        try:
            from nucleo.circuit import spec as _spec
            # A refusal is said by the turn's mouth (or, late, out of turn): the circuit's pulse never says it again.
            _spec_entry["reported"] = _refused
            _attested = _spec.attest(_spec_entry)
        except Exception:  # noqa: BLE001
            pass
    if _row:
        try:
            if _refused and _ia.held(_row, wid, action_name, payload, res):
                if _spec_entry is not None:      # it did not run: it WAITS for his answer, nothing to attest
                    from nucleo.circuit import spec as _spec
                    _spec.withdraw(_spec_entry)
            else:
                _end = lambda: _write_ending(_row, wid, action_name, res, _spec_entry, _attested, _refused)  # noqa: E731
                _ending.defer(_row, _end) if _hold else _end()
        except Exception as e:  # noqa: BLE001
            from loguru import logger
            logger.debug(f"data_ops: the ending of {wid}:{action_name} was not written — {e!r}")
    await _report_ignored(wid, action_name, res, _row)
    if not receipt and isinstance(res, dict) and _receipt.is_pool_timeout(res) and res.get("pending"):
        from nucleo.acts import op_pending as _op_pending        # node 2.917: still running, reported when it ends
        return await _op_pending.still_running(wid, action_name, res, seal=seal, row=_row)
    if callable(seal):
        try:
            seal(not (isinstance(res, dict) and res.get("ok") is False))
        except Exception:
            pass
    if receipt:
        # The receipt OWNS the outcome on this path, so `report_failure` must not also speak.
        try:
            await _receipt.settle(wid, action_name, res, before=before, row=_row)
        except Exception:
            pass
        return res
    try:
        await report_failure(wid, action_name, res, late=_late, row=_row)
    except Exception:
        pass
    return res          # the RESULT, for a turn that owes words and waits on it (`answer_of`)


def _write_ending(_row: str, wid: str, action_name: str, res, _spec_entry, _attested, _refused: bool) -> None:
    """The row's ending this op writes through `circuit.settle` (the one writer). Never raises."""
    from nucleo import circuit as _circuit
    if _refused:
        # V2-850 — the spec closes WITH the row: left open, a refused send's check waited out its grace over a
        # message that was never queued.
        _circuit.settle(_spec_entry, row=_row, verdict="unmet",
                        outcome=str(res.get("message") or res.get("error") or "")[:200])
    elif _spec_entry is None:
        # V2-847 — `undeclared` is «It is done.», and for an act that LEAVES the machine nothing has said so:
        # with no end state to check it is `unverifiable` (said as done-but-unconfirmed), never success.
        from widgets import effects as _fx
        _leaves = _fx.leaves(wid, action_name)
        _circuit.settle(row=_row, verdict="unverifiable" if _leaves else "undeclared",
                        outcome=_fx.unattestable(wid, action_name) if _leaves else "")
    elif _attested is None and _spec_entry.get("awaiting"):
        return                          # V2-884 A6: the app has not confirmed it yet — the circuit's pulse settles it
    elif _attested is not False:
        _circuit.settle(_spec_entry, row=_row, verdict=_circuit.verdict.from_attest(_attested).name)
    elif _spec_entry is not None and _unchanged(_spec_entry):   # a replay, not a failure: the circuit leaves it
        _circuit.settle(_spec_entry, row=_row, verdict="unverifiable",
                        outcome="sin cambio visible: la app ya estaba así")
    # False: the widget may still be catching up — the circuit's pulse settles it.


def _unchanged(e: dict) -> bool:
    try:
        from nucleo.circuit import verify as _verify
        return _verify.only_unchanged(e.get("done_when"))
    except Exception:  # noqa: BLE001
        return False


#: The keys every result carries — an ack, not an answer.
_ACK_KEYS = frozenset({"ok", "queued", "id", "error", "message", "widget", "action", "tab"})   # a face's NAME answers nothing


async def _revert(wid: str, prev: dict) -> None:
    """Take out the row a piece of a sentence wrote. Never raises; says so on the timeline either way."""
    import widgets
    rv = prev.get("revert") or {}
    ok = False
    try:
        r = await widgets.dispatch_tag("widget.data", {"id": wid, "data": {
            "action": str(rv.get("action") or ""), "payload": dict(rv.get("payload") or {})}})
        ok = isinstance(r, dict) and r.get("ok") is not False and not r.get("error")
    except Exception:
        pass
    _outcome.forget(wid)
    try:
        from voice.observer import emit
        emit("widget", "🧩 la frase completa sustituye lo que escribió un trozo de ella",
             text=str(prev.get("text") or "")[:120],
             extra={"id": wid, "action": prev.get("action"), "revert": rv, "ok": ok})
    except Exception:
        pass


async def _report_ignored(wid: str, action: str, res, row: str = "") -> None:
    """A write that landed without part of what it was told is corrected, never left standing (V2-769) — on its
    request's row and said out of turn (V2-851: a task matter goes to its task)."""
    note = _outcome.ignored_note(wid, action, res)
    if not note:
        return
    from nucleo.events import task_event          # never raises
    task_event.told(note, task_id=row, key=f"ignored:{wid}:{action}", ok=False)
    try:
        from voice.observer import emit
        emit("widget", "🩹 data-op guardada SIN parte de sus datos → a su tarea", text=note[:200],
             extra={"id": wid, "action": action, "ignored": list(res.get("ignored") or [])})
    except Exception:
        pass


# ── Is this data-op a DRAG from the previous turn? (V2-038 guard, extracted V2-717) ─────────────────────────

#: The last op a widget REFUSED (V2-773: an identical empty `select` refused twice more). Not remembered as
#: DONE (V2-707), so the anti-drag guard cannot see it.
_REFUSED: dict = {"v": None}
_REFUSED_S = 180.0

