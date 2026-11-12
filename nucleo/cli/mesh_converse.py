"""nucleo/cli/mesh_converse.py — `hbmesh call` and `hbmesh report`: a structured exchange with ONE skill of an agent.

The forms are `USAGE`. `call` crosses the session's exit gate first, like `serve`, and prints JSON; the request is the
agent's own schema. `--json` takes the object inline, `@file` (relative: the worker's shell refuses braces with quotes
in an argument) or `-` (stdin). When the agent ASKS, the question goes on this task's row in the agent's own words (the
server reads them from the exchange, never from here) and the worker's turn ends; his answer resumes it.
"""
from __future__ import annotations

import json
import os
import sys

#: The forms, as the bridge's usage prints them (`nucleo/cli/mesh._USAGE`).
USAGE = ('hbmesh call <agent_id> <skill> --json @request.json --errand "<his words>"   # ONE declared skill',
         'hbmesh report <thread> <outcome>   # how a step the agent handed back ended (one of its `report_as`)')


def _body(raw: str) -> tuple[dict | None, str]:
    raw = str(raw or "").strip()
    try:
        if raw == "-":
            raw = sys.stdin.read()
        elif raw.startswith("@"):
            with open(raw[1:], encoding="utf-8") as fh:
                raw = fh.read()
        got = json.loads(raw or "{}")
    except Exception as e:  # noqa: BLE001 — said back to the worker as the form to fix
        return None, f"`--json` is not a JSON object ({type(e).__name__}): {str(e)[:160]}"
    return (got, "") if isinstance(got, dict) else (None, "`--json` must be a JSON object")


def call(a) -> dict:
    body, why = _body(a.json)
    if body is None:
        return {"ok": False, "reason": why}
    from nucleo.cli.mesh import _bridge_end_turn, _leave_gate, _not_cleared
    cleared = _leave_gate(a.errand or a.skill, json.dumps(body, ensure_ascii=False), a.agent_id)
    if not cleared.get("ok") or cleared.get("status") == "pending":
        return _not_cleared(cleared)
    from nucleo import mesh_call
    out = mesh_call.call(a.agent_id, a.skill, body, errand=a.errand, task_id=os.getenv("ZAELAR_TASK_ID", ""))
    if out.get("agent_asks_user") and os.getenv("ZAELAR_TASK_ID"):
        from nucleo.cli import bridge
        tid, tok = bridge._tid_token()
        asked = bridge._post("/api/worker/act", {"task_id": tid, "token": tok, "action": "ask_user",
                                                 "payload": {"remote": {"thread": out["thread"]}}})
        out["next"] = ("The agent ASKS him first (it did not refuse); the question is on his row in its words. "
                       + _bridge_end_turn(asked)) if asked.get("ok") else f"(could not ask him: {asked.get('error')})"
    return out


def report(a) -> dict:
    from nucleo import mesh_handoff
    return mesh_handoff.report(a.thread, a.outcome)


def add_parsers(sub) -> None:
    p = sub.add_parser("call", help="put a request to ONE declared skill of an agent `find` returned")
    p.add_argument("agent_id")
    p.add_argument("skill")
    p.add_argument("--json", default="{}", help="the request object: inline, @file or -")
    p.add_argument("--errand", default="", help="his words for the errand (the exit gate and the learned route)")
    o = sub.add_parser("report", help="how a step the agent handed back ended")
    o.add_argument("thread")
    o.add_argument("outcome")


def skills_for(agents: list[dict]) -> dict:
    """`{agent_id: [skills]}` read from each agent's own card (cached per origin), for `find`'s answer."""
    if not agents:
        return {}
    from nucleo import mesh_agents, mesh_call
    return {str(x["agent_id"]): mesh_call.skills_of(mesh_agents._card_of(mesh_agents._endpoint_of(x)))
            for x in agents if x.get("agent_id") and mesh_agents._endpoint_of(x)}
