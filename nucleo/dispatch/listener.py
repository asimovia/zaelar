"""The SlowBrain's escalation listener — what turns a `escalate.requested` into a worker (V2-778 F1-11, 2026-10-01).

Moved out of `nucleo/dispatch.py`, which stays the facade: `dispatch.run_listener` delegates here. The body is the
SAME code; the one change is that every name it read from the dispatcher (its registry, `_run_session`, `inject`,
the dedup and continuity gates…) is read THROUGH the module — `_d.<name>` — so a test or a caller that patches
`dispatch.<name>` still governs the listener exactly as before the move.
"""
from __future__ import annotations

import asyncio

from loguru import logger

from nucleo import dispatch as _d


def _note_screen(key: str, ctx: dict, rec) -> None:
    try:
        from voice import screens as _screens
        _screens.note_task(key, ctx.get("origin_dev") or _screens.origin_of({"trace": rec.trace_id}))
    except Exception as e:  # noqa: BLE001 — where a card opens never stops the errand from starting
        logger.debug(f"dispatch: no screen origin for {key}: {e!r}")


async def run_listener(stop: "asyncio.Event | None" = None) -> None:
    import bus

    sub = bus.subscribe("escalate.requested")
    logger.info("dispatch: listener de escalados (Brain Workers) arrancado")
    try:
        while stop is None or not stop.is_set():
            try:
                ev = await asyncio.wait_for(sub.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except Exception:
                break
            payload = ev if isinstance(ev, dict) else {}
            tid = payload.get("id")
            request = (payload.get("request") or "").strip()
            ctx = payload.get("context") or {}
            if not request:
                continue
            key = str(tid or "?")
            kind = str(ctx.get("kind", "generic"))
            # V2-092: with the agent STOPPED (⏻) no new work opens (paused workers resume on start). Rejected
            # VISIBLY (`task/blocked`), never silently.
            from nucleo import runstate
            _halted = runstate.blocks_new_work(who="dispatch")   # V2-655: falla CERRADO, ver ese docstring
            if _halted:
                try:
                    from voice.observer import emit
                    emit("task", "blocked", role="system", text=request[:120],
                         extra={"id": key, "reason": "el agente está parado (⏻): no se abre trabajo nuevo"})
                except Exception:
                    pass
                _d._close_escalated_flow(ctx, ok=False, status="rejected_halted")
                _unborn(ctx)
                logger.info(f"dispatch: escalada RECHAZADA (agente parado): {request[:80]}")
                continue
            # NOTHING IS FOLDED (INI-078 segregation S2): the model of the conversation decided this is a NEW task, and a
            # new task it is — the one decider. A word table that folded it into a live or a parked one undid that
            # decision in silence («a hotel in Rome» into «a flight to Rome»). A new task that looks very much like an
            # open one is only RECORDED (`route/near`, both rows) for the auditor; he cancels it if it is one too many.
            _bound = bool(ctx.get("answers") or (ctx.get("resume") or {}).get("rebrief"))   # its own row coming back
            if not (_bound or ctx.get("confirmed")):
                _near(request, kind if kind != "generic" else _d._kind_of(ctx.get("errand_kind")), key, ctx)
            # V2-566/V2-570 — A FOLLOW-UP IS NOT A NEW ERRAND, and a follow-up of a DELIVERED listing fast
            # pass does not spawn a parallel worker. Both decisions live in `nucleo/request/append.py`
            # (extracted: dispatch sat one line under its ratchet ceiling): the escalation may come back with
            # an inherited sheet, or redirected entirely to a refined fast re-run in the same box — in which
            # case there is no session to open and the module already owns the errand's next step.
            ctx, _redirected = (ctx, False) if _bound else _d._continuity.inherit_and_maybe_rerun(
                request, kind if kind != "generic" else _d._kind_of(ctx.get("errand_kind")), ctx, key)
            if _redirected:
                _d._close_escalated_flow(ctx, ok=True, status="linear_rerun")
                _unborn(ctx)
                continue
            # V2-049 CONTINUIDAD: without session live that casar, ¿there is a operation web INCOMPLETA reciente that ESTA
            # request resumes? (nudge «continues with the ITV», or the operator aportando the dato that was missing). Reanuda esa
            # same tab + razonamiento in vez of start of cero.
            _k = kind if kind != "generic" else _d._kind_of(ctx.get("errand_kind"))
            if _k == "web" and not _bound:
                # take=True: the reanudacion is CONSUME al entregarla. Sin eso, two escaladas of the same
                # request is llevan the same id of session of the CLI and the second dies in the arranque.
                _res = _d._find_resume(request, take=True)
                if _res and (_res.get("nav_task") or _res.get("native_sid")):
                    ctx = dict(ctx)
                    ctx["resume"] = _res
                    try:
                        from voice.observer import emit
                        emit("task", "resume", role="system", text=request[:120],
                             extra={"id": key, "nav_task": _res.get("nav_task", ""),
                                    "reason": "reanuda gestión web incompleta (no re-lanza de cero)"})
                    except Exception:
                        pass
            task = _d.Task(id=key, request=request, kind=kind,
                        trusted=bool(ctx.get("trusted", True)), context=ctx)
            rec = _d.SessionRecord(task_id=key, goal=request[:200], kind=task.kind,
                                parent_task_id=str(ctx.get("parent_task_id", "")),
                                depth=int(ctx.get("depth", 0) or 0),
                                # La GENERACIÓN of relevo viaja with the cadena. Sin esto the cap of `_finish` no
                                # exists: each relevo estrena record and su contador vuelve a cero.
                                relay_gen=int(ctx.get("relay_gen", 0) or 0),
                                # …and the SHEET with it, for the same reason: a relay continues the errand, so
                                # it keeps writing where the operator is already looking instead of opening a
                                # second box beside it.
                                sheet=str(ctx.get("sheet", "") or ""), uid=str(ctx.get("task_uid", "") or ""),
                                # …and HOW SUCCESS IS MEASURED (V2-707 F2): a relay that dropped the condition
                                # would deliver the half-done work the harness had just caught.
                                done_when=dict(ctx.get("done_when") or {}),
                                trace_id=str(ctx.get("trace", "") or ""), heard=str(ctx.get("heard", "") or ""),
                                run=str(ctx.get("run", "") or ""))
            # V2-227 — the SURFACE is sealed here, the one point EVERY door into the dispatcher passes (the brain with its
            # `surface`, auto-resume, the confirm gate, the cluster). What the brain declared rules; with nothing
            # declared (or a word outside the vocabulary) it derives from the kind. Sealing later would open the sheet
            # once the answer is already there — exactly what this exists to prevent.
            from nucleo.circuit import ledger as _tasks
            rec.uid = rec.uid or _tasks.task_uid(key)    # V2-852 I1: named by its ROW, registered before its first act
            _d._SESSIONS[key] = rec
            _note_screen(key, ctx, rec)   # V2-792: its cards open on the screen that commissioned it
            _d.surfaces.set_once(rec, ctx.get("surface"))
            # …and a sheet surface OPENS NOW, empty, on its process tab: here, not at delivery, his blank screen ends.
            if _d.surfaces.opens_sheet(getattr(rec, "surface", "")):
                _d._sheet_open(rec)
            elif _d.surfaces.opens_doc(getattr(rec, "surface", "")):   # a REPORT opens the DOCUMENT sheet (V2-644)
                _d._docsheet.doc_open(rec)
            # V2-728 — the DURABLE row (a restart empties `_SESSIONS`), written at the same single door.
            # Best-effort: a failed store must not lose the worker.
            try:
                _tasks.opened(rec, ctx)
            except Exception:  # noqa: BLE001
                logger.debug("dispatch: no pude registrar la tarea durable", exc_info=True)
            __import__("nucleo.chat_refs", fromlist=["x"]).opened(rec, ctx)   # V2-862: its box on his chat wall, or why not
            _d._name_errand(rec)          # V2-530 — asynchronous; the sheet is already open under its brief

            rec.task = asyncio.create_task(_d._run_session(task), name=f"worker-session-{key}")
            _d.sync_state()
    finally:
        sub.close()
        logger.info("dispatch: listener de escalados detenido")


def _unborn(ctx: dict | None) -> None:
    """The row the turn wrote for an escalation that did not become a worker of its own goes (V2-844 F1a)."""
    try:
        from nucleo.circuit import ledger as _ledger
        _ledger.unborn(str((ctx or {}).get("born_uid") or ""))
    except Exception as e:  # noqa: BLE001
        logger.debug(f"dispatch: a born row was not withdrawn — {type(e).__name__}: {e}")


def _near(request: str, kind: str, key: str, ctx: dict) -> None:
    """A new task that looks very much like an open one: recorded for the auditor, never folded. Never raises."""
    try:
        dup, ev = _d.dedup_scan(request, kind)
        if not dup:
            return
        from voice.observer import emit
        emit("route", "near", role="system", text=request[:200],
             extra={"new": key, "open": str(dup), "by": str(ev.get("by") or ""), "trace": str(ctx.get("trace") or "")})
    except Exception as e:  # noqa: BLE001 — a record for the auditor never decides an errand
        logger.debug(f"dispatch: near not recorded for {key} ({e!r})")
