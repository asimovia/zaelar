"""nucleo/cli/mesh_converse.py — `hbmesh call` and `hbmesh reply`: a structured exchange with ONE skill of an agent.

    hbmesh call <agent_id> <skill> --json '<request>' [--errand "<his words>"]
    hbmesh reply <thread> --answer <question id>=<n> [--value <what he said>] [--cancel]

`call` puts a request to a skill the agent's card declares (`find` lists them); `reply` sends his answers to the
questions that exchange left open. Both cross the session's exit gate first, like `serve`, and print JSON. The request
is the agent's own schema — nothing here knows any of its fields. `--json` takes the object inline, `@file` (a path
relative to the working directory: the worker's shell refuses braces with quotes in an argument) or `-` (stdin).
"""
from __future__ import annotations

import json
import os
import sys


#: The two forms, as the bridge's usage prints them (`nucleo/cli/mesh._USAGE`).
USAGE = ('hbmesh call <agent_id> <skill> --json @request.json [--errand "<his words>"]   # ONE declared skill',
         'hbmesh reply <thread> --answer <question id>=<n> [--value "<his words>"] [--cancel]   # his answers back')
REPORT_USAGE = 'hbmesh report <thread> <outcome>   # how a step the agent handed back ended (one of its `report_as`)'


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


def _answers(pairs: list[str], values: list[str]) -> tuple[list, str]:
    from nucleo.mesh_dialog import parse_value
    out = []
    for i, p in enumerate(pairs or []):
        qid, sep, n = str(p).partition("=")
        if not sep or not qid.strip() or not n.strip().lstrip("-").isdigit():
            return [], f"`--answer {p}` is not <question id>=<n> (the choice's `n`)"
        value = parse_value(values[i]) if i < len(values or []) and values[i] != "" else None
        out.append((qid.strip(), int(n), value))
    return out, ""


def call(a) -> dict:
    body, why = _body(a.json)
    if body is None:
        return {"ok": False, "reason": why}
    from nucleo.cli.mesh import _leave_gate, _not_cleared
    cleared = _leave_gate(a.errand or a.skill, json.dumps(body, ensure_ascii=False), a.agent_id)
    if not cleared.get("ok") or cleared.get("status") == "pending":
        return _not_cleared(cleared)
    from nucleo import mesh_call
    return mesh_call.call(a.agent_id, a.skill, body, errand=a.errand, task_id=os.getenv("ZAELAR_TASK_ID", ""))


def reply(a) -> dict:
    answers, why = _answers(a.answer, a.value)
    if why or (not answers and not a.cancel):
        return {"ok": False, "reason": why or "nothing to send: give one `--answer` per question, or `--cancel`"}
    from nucleo import mesh_dialog
    t = mesh_dialog.thread(a.thread) or {}
    from nucleo.cli.mesh import _leave_gate, _not_cleared
    cleared = _leave_gate(t.get("errand") or a.thread, json.dumps(answers, ensure_ascii=False, default=str),
                          str(t.get("agent") or ""))
    if not cleared.get("ok") or cleared.get("status") == "pending":
        return _not_cleared(cleared)
    from nucleo import mesh_call
    return mesh_call.reply(a.thread, answers, cancel=bool(a.cancel))


def report(a) -> dict:
    from nucleo import mesh_handoff
    return mesh_handoff.report(a.thread, a.outcome)


def add_parsers(sub) -> None:
    p = sub.add_parser("call", help="put a request to ONE declared skill of an agent `find` returned")
    p.add_argument("agent_id")
    p.add_argument("skill")
    p.add_argument("--json", default="{}", help="the request object: inline, @file or -")
    p.add_argument("--errand", default="", help="his words for the errand (the exit gate and the learned route)")
    r = sub.add_parser("reply", help="send his answers to the questions an exchange left open")
    r.add_argument("thread")
    r.add_argument("--answer", action="append", default=[], metavar="QID=N", help="repeatable")
    r.add_argument("--value", action="append", default=[], help="his words for a choice with `needs_value`, in order")
    r.add_argument("--cancel", action="store_true", help="withdraw the request instead")
    o = sub.add_parser("report", help="how a step the agent handed back ended")
    o.add_argument("thread")
    o.add_argument("outcome")


def skills_for(agents: list[dict]) -> dict:
    """`{agent_id: [skills]}` read from each agent's own card (cached per origin), for `find`'s answer."""
    if not agents:
        return {}
    from nucleo import mesh_agents, mesh_skills
    out = {}
    for x in agents or []:
        ep = mesh_agents._endpoint_of(x)
        if ep and x.get("agent_id"):
            out[str(x["agent_id"])] = mesh_skills.skills_of(mesh_agents._card_of(ep))
    return out
