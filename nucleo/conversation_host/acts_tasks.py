"""The `Tools` port's TASK acts (INI-078 F2 step 3): his errands, carried to the doors that already run them.

Declared in `declared.json` (`acts`, door `task`), each to its one door — never rebuilt here:

  start      `acts.errand.escalate_to_slowbrain`, the ONE gateway every errand is born through (its refusals, its
             parking, a stopped agent, the capability gate: all the door's)
  resume     `pending_work.by_ids` (the model chooses among DECLARED pending rows: TASKS lists them) →
             `resume_turn.resume`, each row from itself
  reopen     `task_recall.voice_turn`: a finished errand and its sheet brought back, or a question which
  stop       `dispatch.cancel_soon` through the row's one cancel door, by the id TASKS gives
  unschedule `pulse.scheduler.unschedule`, by its reference — said as it ended, found or not
  sign_in    `web_auth.start` / `web_auth.finish`: the real browser opened for HIM to sign in, and his «done»

What each returns is the door's own fact: the model says it. His spoken words to a process already open are not an act
of the model's: they reach that process by the switchboard (`route.py`) before the model is called.
"""
from __future__ import annotations

from conversation.ports import ToolResult


def _start(args: dict) -> ToolResult:
    from nucleo.acts import errand
    request = str(args.get("request") or "").strip()
    if not request:
        return ToolResult("failed", {"reason": "no_request"})
    tid = errand.escalate_to_slowbrain(request, context={"origin": "conversation"})
    if not tid:
        return ToolResult("rejected", {"reason": "the errand door did not start it (refused, parked or stopped)"})
    return ToolResult("ok", {"task": tid, "started": request[:160]})


def _resume(args: dict) -> ToolResult:
    from nucleo import pending_work
    from nucleo.flash import resume_turn
    ids = args.get("ids") if isinstance(args.get("ids"), list) else [args.get("ids")] if args.get("ids") else []
    rows = pending_work.by_ids(ids)
    if not rows:
        return ToolResult("failed", {"reason": "no_such_pending_task", "pending": [
            {"id": r["id"], "title": r.get("title")} for r in pending_work.rows()]})
    done = resume_turn.resume(rows, operator_text="")
    return ToolResult("ok" if done else "rejected", {"resumed": done})


def _reopen(args: dict) -> ToolResult:
    from nucleo.acts import canvas
    from nucleo.turn import task_recall
    query = str(args.get("query") or "").strip()
    v = task_recall.voice_turn(query, query)
    if v.get("show"):
        canvas.apply("show", v["show"], src=f"recall:{v['show']}")
        return ToolResult("ok", {"reopened": v.get("title") or v["show"], "rebuilt": bool(v.get("rebuilt"))})
    if v.get("ask"):
        return ToolResult("failed", {"reason": "which_one", "candidates": v["ask"]})
    return ToolResult("failed", {"reason": "nothing_like_it", "start_it_again": bool(v.get("escalate"))})


def _stop(args: dict) -> ToolResult:
    from nucleo import dispatch
    from nucleo.request import stop_row
    which = str(args.get("task") or "").strip()
    if not which:
        return ToolResult("failed", {"reason": "which_task"})
    tids = dispatch.cancel_soon(which)
    stop_row.stopped_by_his_turn(tids)
    return ToolResult("ok" if tids else "failed", {"stopped": tids} if tids else {"reason": "no_such_task"})


def _unschedule(args: dict) -> ToolResult:
    from nucleo.pulse import scheduler
    r = scheduler.unschedule(str(args.get("job") or "").strip())
    if r.get("ok"):
        return ToolResult("ok", {"cancelled": r.get("label") or r.get("id")})
    return ToolResult("failed", {"reason": "no_such_job", **{k: v for k, v in r.items() if k != "ok"}})


def _sign_in(args: dict) -> ToolResult:
    from nucleo.flash import web_auth
    if str(args.get("done") or "").lower() in ("true", "1", "yes"):
        tid = web_auth.finish()
        return ToolResult("ok" if tid else "failed", {"resumed": tid} if tid else {"reason": "nothing_waited"})
    site = str(args.get("site") or "").strip()
    tid = web_auth.start(site)
    return ToolResult("ok" if tid else "failed", {"opened_for": site, "task": tid} if tid
                      else {"reason": "no_site_recognised", "site": site})


DOORS = {"start": _start, "resume": _resume, "reopen": _reopen, "stop": _stop, "unschedule": _unschedule,
         "sign_in": _sign_in}


def run(op: str, args: dict) -> ToolResult:
    door = DOORS.get(op)
    if door is None:
        return ToolResult("rejected", {"reason": "unknown_door", "op": op})
    return door(args if isinstance(args, dict) else {})
