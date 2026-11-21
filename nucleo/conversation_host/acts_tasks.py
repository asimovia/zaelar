"""The `Tools` port's TASK acts (INI-078 F2 step 3): his errands, carried to the doors that already run them.

Declared in `declared.json` (`acts`, door `task`), each to its one door — never rebuilt here:

  start      `acts.errand.escalate_to_slowbrain`, the ONE gateway every errand is born through (its refusals, its
             parking, a stopped agent, the capability gate: all the door's)
  resume     `pending_work.by_ids` (the model chooses among DECLARED pending rows: TASKS lists them) →
             `request.resume`, each row from itself
  reopen     `task_recall.voice_turn`: a finished errand and its sheet brought back, or a question which
  stop       `dispatch.cancel_soon` through the row's one cancel door, by the id TASKS gives
  unschedule `pulse.scheduler.unschedule`, by its reference — said as it ended, found or not
  sign_in    `request.web_login.start` / `finish`: the real browser opened for HIM to sign in, and his «done»
  note       `support_note.spoken`: his words kept as a note for the support team, nothing else done
  answer     `switchboard.act.deliver`, the one door his words take to a process: a waiting question's answer (a plain
             yes or no decides the act it held), a running worker's next words — the process the model named by id
  listings   `search_listing.hunt`: the fast listings pass on the engine's loop — the rows on his results sheet, too few
             and the deep search is an errand already started; the fact (how many, the rows, the sheet) is returned

What each returns is the door's own fact: the model says it. His spoken words to a process already open are not an act
of the model's: they reach that process by the switchboard (`route.py`) before the model is called.
"""
from __future__ import annotations

from conversation.ports import ToolResult


def errand_context(args: dict) -> dict:
    """What the model's call decides about an errand, in the context its readers already respect (`request/kind`
    reads `kind_of` and `sure_order` off it): its kind, its consent class, the surface he will look at, the declared
    action it starts with, and his words. The model's order IS the decision: carried at full confidence."""
    from nucleo.conversation_host import routing, turns
    from nucleo.request import kind as _kind
    said = routing.said()
    ctx: dict = {"origin": "conversation", **({"heard": said, "said": said} if said else {})}
    if turns.run_in_course():     # its sibling calls of this run are other tasks, never a duplicate of this one
        ctx["run"] = turns.run_in_course()
    for arg, key in (("kind", _kind.KEY), ("class", "errand_class")):
        if str(args.get(arg) or "").strip():
            ctx[key] = {"choice": str(args[arg]).strip(), "confidence": 1.0}
    if str(args.get("surface") or "").strip():
        ctx["surface"] = str(args["surface"]).strip()
    if str(args.get("widget") or "").strip() and str(args.get("action") or "").strip():
        ctx["first_act"] = {"widget": str(args["widget"]).strip(), "action": str(args["action"]).strip()}
    return ctx


def _start(args: dict) -> ToolResult:
    from nucleo.acts import errand
    request = str(args.get("request") or "").strip()
    if not request:
        return ToolResult("failed", {"reason": "no_request"})
    tid = errand.escalate_to_slowbrain(request, context=errand_context(args))
    if not tid:
        return ToolResult("rejected", {"reason": "the errand door did not start it (refused, parked or stopped)"})
    return ToolResult("ok", {"task": tid, "started": request[:160]})


def _resume(args: dict) -> ToolResult:
    from nucleo import pending_work
    from nucleo.request import resume
    ids = args.get("ids") if isinstance(args.get("ids"), list) else [args.get("ids")] if args.get("ids") else []
    rows = pending_work.by_ids(ids)
    if not rows:
        return ToolResult("failed", {"reason": "no_such_pending_task", "pending": [
            {"id": r["id"], "title": r.get("title")} for r in pending_work.rows()]})
    done = resume.resume(rows, operator_text="", apply_widget_data=_apply_widget_data)   # a widget's row by its act
    return ToolResult("ok" if done else "rejected", {"resumed": done})


def _apply_widget_data(widget: str, action: str, payload: dict) -> None:
    """A widget's pending row resumed through its own declared action, on the engine's loop (its confirm gate)."""
    import asyncio

    from nucleo.acts import data_ops
    from nucleo.conversation_host.acts_widget import _on_engine_loop
    asyncio.run(_on_engine_loop(data_ops.dispatch_and_report(widget, action, payload)))


def _reopen(args: dict) -> ToolResult:
    from nucleo.acts import canvas
    from nucleo.errands import task_recall
    query = str(args.get("query") or "").strip()
    v = task_recall.voice_turn(query, query)
    if v.get("show"):
        canvas.apply("show", v["show"], src=f"recall:{v['show']}")
        return ToolResult("ok", {"reopened": v.get("title") or v["show"], "rebuilt": bool(v.get("rebuilt"))})
    if v.get("ask"):
        return ToolResult("failed", {"reason": "which_one", "candidates": v["ask"]})
    return ToolResult("failed", {"reason": "nothing_like_it", "start_it_again": bool(v.get("escalate"))})


def numbered(which) -> dict | None:
    """The task of the queue a `#n` names (also `n`, or its row id); None when it is not open (S3: never a guess)."""
    from nucleo import queue
    w = str(which or "").strip().lstrip("#")
    rows = [r for lane in queue.view().values() for st in lane.values() for r in st]
    return next((r for r in rows if w and (str(r.get("num")) == w or str(r.get("id")) == w)), None)


def _not_open(which) -> ToolResult:
    """A number that is not open: the act fails and gives OPEN back, so the model corrects itself in the next step."""
    from nucleo.conversation_host import open_block
    return ToolResult("failed", {"reason": "not_open", "asked_for": str(which or ""), "open": open_block.text()})


def _session_of(uid: str) -> str:
    from nucleo import dispatch
    return next((k for k, rec in dispatch._SESSIONS.items() if getattr(rec, "uid", "") == uid
                 and rec.status in dispatch.LIVE_SESSION_STATES), "")


def _stop(args: dict) -> ToolResult:
    from nucleo import dispatch, queue
    from nucleo.conversation_host import routing
    which = str(args.get("task") or "").strip()
    if not which:
        return ToolResult("failed", {"reason": "which_task"})
    row = numbered(which)
    if row is None and which.lower() not in ("all", "*"):
        return _not_open(which)
    if row is not None and not (key := _session_of(str(row["id"]))):   # nothing runs it: it leaves the queue now
        ok = queue.signal(str(row["id"]), "cancelled", by="him", outcome="stopped by him")
        return ToolResult("ok" if ok else "failed", {"stopped": [f"#{row['num']}"]} if ok else {"reason": "refused"})
    tids = dispatch.cancel_soon(key if row is not None else which)
    __import__("nucleo.request.stop_row", fromlist=["x"]).stopped_by_his_turn(tids, words=routing.said())
    return ToolResult("ok" if tids else "failed", {"stopped": tids} if tids else {"reason": "no_such_task"})


def _priority(args: dict) -> ToolResult:
    from nucleo import queue
    row = numbered(args.get("task"))
    if row is None:
        return _not_open(args.get("task"))
    urgent = str(args.get("urgent", True)).lower() not in ("false", "0", "no")
    ok = queue.signal(str(row["id"]), "priority", by="him", urgent=urgent)
    return ToolResult("ok" if ok else "failed", {"task": f"#{row['num']}", "urgent": urgent} if ok
                      else {"reason": "only a pending task changes its place"})


def _move(args: dict) -> ToolResult:
    from nucleo import queue
    row = numbered(args.get("task"))
    if row is None:
        return _not_open(args.get("task"))
    before = str(args.get("before") or "").strip()
    if before not in ("first", "last"):
        other = numbered(before)
        if other is None:
            return _not_open(before)
        before = str(other["id"])
    ok = queue.signal(str(row["id"]), "move", by="him", before=before)
    return ToolResult("ok" if ok else "failed", {"task": f"#{row['num']}", "moved": True} if ok
                      else {"reason": "only a pending task of the same lane moves"})


def _unschedule(args: dict) -> ToolResult:
    from nucleo.pulse import scheduler
    r = scheduler.unschedule(str(args.get("job") or "").strip())
    if r.get("ok"):
        return ToolResult("ok", {"cancelled": r.get("label") or r.get("id")})
    return ToolResult("failed", {"reason": "no_such_job", **{k: v for k, v in r.items() if k != "ok"}})


def _sign_in(args: dict) -> ToolResult:
    from nucleo.request import web_login
    if str(args.get("done") or "").lower() in ("true", "1", "yes"):
        tid = web_login.finish()
        return ToolResult("ok" if tid else "failed", {"resumed": tid} if tid else {"reason": "nothing_waited"})
    site = str(args.get("site") or "").strip()
    tid = web_login.start(site)
    return ToolResult("ok" if tid else "failed", {"opened_for": site, "task": tid} if tid
                      else {"reason": "no_site_recognised", "site": site})


def _note(args: dict) -> ToolResult:
    """His words as a note for the support team (`support_note.spoken`): kept on the timeline, nothing else done."""
    from nucleo.conversation_host import routing
    from nucleo.input import support_note
    kept = support_note.spoken(routing.said() or str(args.get("note") or ""))
    return ToolResult("ok" if kept else "failed", {"kept": True} if kept else {"reason": "no_note"})


#: how much of the sheet's rows the fact carries back to the model
LISTING_ROWS_CHARS = 1600


def _listings(args: dict) -> ToolResult:
    import asyncio

    from nucleo.acts import search_listing
    from nucleo.conversation_host import routing, tools_read
    from nucleo.conversation_host.acts_widget import _on_engine_loop
    if not str(args.get("query") or "").strip():
        return ToolResult("failed", {"reason": "no_query"})
    got = asyncio.run(_on_engine_loop(search_listing.hunt(routing.said() or str(args["query"]), args)))
    res = got.get("res") or {}
    rows = str(res.get("ctx") or "")[:LISTING_ROWS_CHARS]
    fact = {"found": int(res.get("n") or 0), "on_his_results_sheet": bool(res.get("delivered")),
            "deep_search_started": bool(res.get("escalated") or res.get("pending")), "rows": rows or None}
    return ToolResult("ok" if fact["found"] or fact["deep_search_started"] else "failed",
                      {k: v for k, v in fact.items() if v is not None},
                      tools_read._text_evidence(f"listings:{res.get('sheet') or ''}", rows) if rows else ())


def _say(args: dict) -> ToolResult:
    """His words to what an open task DOES, the task named by its `#n` (or a question's key OPEN lists): its question
    answered, a yes or a no, a fact added or changed — by the one delivery door (R-3: the model decides, no router)."""
    from nucleo.conversation_host import routing
    from nucleo.switchboard import act, board
    which = str(args.get("task") or "").strip()
    row = numbered(which)
    if row is not None and row.get("owner") == "send":     # a message draft has its own acts (S4)
        return ToolResult("failed", {"reason": "a_message_draft", "task": f"#{row['num']}",
                                     "use": "draft_send (his yes) · draft_edit (who or text) · draft_drop (his no)"})
    keys = {str(row["id"]), _session_of(str(row["id"]))} - {""} if row else {which.lstrip("#")}
    p = next((p for p in board.open_processes() if keys & {p.get("key"), p.get("dispatch"), p.get("ask_id")}), None)
    if p is None:
        return _not_open(which)
    kind = {"yes": act.YES, "no": act.NO}.get(str(args.get("is") or "").lower(), act.OTHER)
    text = str(args.get("text") or "").strip() or routing.said()
    ok = act.deliver(p, text, kind)
    return ToolResult("ok" if ok else "failed", {"task": f"#{row['num']}" if row else p.get("key"),
                                                 "title": p.get("title"), "delivered": ok})


DOORS = {f.__name__.lstrip("_"): f for f in (_say, _priority, _move, _listings, _start, _resume, _reopen, _stop,
                                             _unschedule, _sign_in, _note)}


def run(op: str, args: dict) -> ToolResult:
    door = DOORS.get(op)
    if door is None:
        return ToolResult("rejected", {"reason": "unknown_door", "op": op})
    return door(args if isinstance(args, dict) else {})
