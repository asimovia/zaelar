"""nucleo/cli/worker_api_schedule.py — the scheduler's worker acts, split from `worker_api_exec._exec_allow` by concern.

Every name that lives in `worker_api` is read as `_m.<name>`, so a test patching it there still governs this code.
"""
from __future__ import annotations

import asyncio


async def run(action: str, payload: dict, rec) -> dict:
    """The scheduler's three worker acts: `schedule` creates a reminder (capped per task), `schedules` lists the
    jobs by reference and `unschedule` cancels ONE (V2-883). Split out of `_exec_allow` so it only shrinks."""
    from nucleo.cli import worker_api as _m
    if action == "schedule":
        # V2-249 — a scheduled reminder must really exist, or it must not be claimed.
        when = str(payload.get("when") or payload.get("schedule") or "").strip()
        what = str(payload.get("prompt") or payload.get("text") or payload.get("what") or "").strip()
        tid = str(getattr(rec, "task_id", "") or "")
        if not what:
            return {"ok": False, "error": "falta `prompt`: qué tiene que decir o hacer zaelar cuando llegue el "
                                          "momento, escrito como se lo dirías a él."}
        if not when:
            return {"ok": False, "error": "falta `when`: cuándo. " + _m._CUANDO_VALE}
        try:
            from nucleo.pulse import scheduler
            # Machine forms first (`parse_schedule`: every/cron/ISO), then spoken ones (`parse_when`).
            spec = when if scheduler.parse_schedule(when) else (scheduler.parse_when(when) or "")
            if not spec:
                # Ambiguous input parses to "": a reminder on a guessed date is worse than none.
                return {"ok": False, "error": f"«{when}» no me dice un momento exacto y no lo adivino: un aviso "
                                              f"sobre una fecha inventada es peor que ninguno. " + _m._CUANDO_VALE}
            # THE CAP, counted over live jobs by attribution: a looping worker cannot fill the agenda.
            mias = [j for j in scheduler.list_jobs() if f"[worker:{tid}]" in str(j.get("name") or "")]
            if len(mias) >= _m._SCHEDULE_CAP:
                return {"ok": False, "error": f"ya has programado {len(mias)} avisos en esta tarea, que es el "
                                              f"tope. Si necesitas otro, cancela uno o dilo en tu entrega."}
            name = f"{(payload.get('name') or what)[:80]} [worker:{tid}]"
            # V2-480: a cron's reader is the AGENT at another time, so the job tells it to NOTIFY (the agenda's rule)
            from widgets.agenda import notice as _notice
            what = _notice.prompt_for({"commitment": what}) or what
            out = await asyncio.to_thread(scheduler.create_unless_ringing, what, spec, name)   # one alarm per instant
            if not out.get("ok"):
                return {"ok": False, "error": f"{out.get('error') or 'no se pudo programar'}. " + _m._CUANDO_VALE}
            # V2-249 — and make it VISIBLE: a row with the real cron id, the proof of the effect.
            try:
                from voice.observer import emit
                emit("task", "⏰ aviso programado",
                     text=f"{out.get('display') or when} — {what[:120]}",
                     extra={"id": tid, "src": f"worker:{tid}", "cron_id": out.get("id"),
                            "when": out.get("display") or when})
            except Exception as e:  # noqa: BLE001 — the reminder exists; only its visible row failed
                from loguru import logger
                logger.debug(f"worker_api_schedule: the scheduled-notice event was not emitted ({e!r})")
            return {"ok": True, "result": {"id": out.get("id"), "cuando": out.get("display") or when,
                                           "que": what,
                                           "ref": f"cron:{out.get('id')}"}}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"no pude programarlo: {e}"}
    # V2-883: `schedules` / `unschedule` — the jobs' one reader and one door by reference
    from nucleo.pulse import scheduler_refs
    return await asyncio.to_thread(scheduler_refs.worker_act, action, payload)
