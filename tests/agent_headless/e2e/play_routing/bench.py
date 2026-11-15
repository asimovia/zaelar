"""Routing bench for the fast brain + the playbook (V2-909): where each request goes, by text, on ONE sandbox engine.

One isolated sandbox (`tests/platform/sandbox_engine`, connectors off, the model credentials lent) with the stages
`play.shadow` and `play.own` on in its own workspace config. Each case of `cases.json` is one order on the text
channel (`POST /api/flash/say`, a fresh session unless the case carries `pre` turns). What a row records:

  · the turn's `play/route` event (matched by trace): `dest`, `legacy`, `agree`, `unserved`, `named`, `ran`;
  · the `play/step` walk of any send row born in the row's window (the owner's events when `own` is on);
  · the widget state the case declares, read through `GET /widgets/<id>/data` before and after the turn;
  · the reply, the turn's seconds, and `claims_without_act` = `unserved` with `ran` empty (words are not judged).

An errand row (class D) is routed, recorded and then stopped in its own session with the case file's `stop` line;
nothing waits for a worker to finish.

Messaging: a test double of the WhatsApp bridge (`wa_double.py`) answers on a free port, so WhatsApp reads as
connected and an accepted send echoes back about a second later — and nothing leaves the process. `--no-double`
runs with WhatsApp off, as a bare sandbox.

Exit code: 0 when every row reached its expected `dest` and passed its checks; 1 otherwise; 2 when the sandbox did
not boot. Sameness (class E: the same order three times) is reported, not gated.

    ./.venv/bin/python -m tests.agent_headless.e2e.play_routing.bench [--only A1,C3] [--out <dir>]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE = HERE.parents[3]
TABLE = json.loads((ENGINE / "nucleo" / "play" / "table.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------------------------- pure readers


def _path(data, path: str):
    cur = data
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def legal_walk(steps: list[str]) -> bool:
    """Every consecutive pair of steps is a move the table declares (a declared pass may be skipped)."""
    moves, passes = TABLE["moves"], TABLE.get("passes") or {}
    prev = TABLE["first"]
    for step in steps:
        if step == prev:
            continue
        nexts = set((moves.get(prev) or {}).values())
        nexts |= {passes[n] for n in list(nexts) if n in passes}
        if step not in nexts:
            return False
        prev = step
    return True


def reply_kind(reply: str) -> str:
    text = (reply or "").strip()
    if not text:
        return "empty"
    return "question" if "?" in text else "statement"


def signature(row: dict) -> tuple:
    r = row.get("route") or {}
    return (r.get("dest"), r.get("legacy"), tuple(r.get("named") or ()), tuple(r.get("ran") or ()),
            tuple(row.get("walk_events") or ()), row.get("reply_kind"))


# --------------------------------------------------------------------------------------------- engine side


class Timeline:
    def __init__(self, path: Path):
        self.path = path

    def mark(self) -> int:
        return self.path.stat().st_size if self.path.exists() else 0

    def since(self, mark: int) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        with self.path.open("rb") as f:
            f.seek(mark)
            for line in f:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
        return out


def _steps(evs: list[dict], seen: set) -> tuple[list[dict], set]:
    """The `play/step` events of send rows BORN in this window (late events of earlier rows are left out)."""
    steps = [e for e in evs if e.get("kind") == "play" and e.get("label") == "step"]
    new_ids = {e.get("task_id") for e in steps if e.get("task_id") and e.get("task_id") not in seen}
    mine = [e for e in steps if e.get("task_id") in new_ids]
    own = [e for e in mine if e.get("own")]
    return (own or mine), new_ids


def _check(chk: dict, before: dict, after: dict, row: dict) -> tuple[bool, str]:
    if chk.get("ran_empty"):
        ran = (row.get("route") or {}).get("ran") or []
        return (not ran), f"ran={ran}"
    if "no_door" in chk:
        doors = [c.get("door") for c in row.get("consequences") or [] if isinstance(c, dict)]
        return chk["no_door"] not in doors, f"doors={doors}"
    if chk.get("walk_legal"):
        steps = row.get("walk_steps") or []
        return legal_walk(steps), f"steps={steps}"
    if "double_calls" in chk:
        n = len(row.get("double_sends") or [])
        return n == chk["double_calls"], f"double accepted {n} send(s) (want {chk['double_calls']})"
    if "outbox_sent_delta" in chk:
        d = _sent_rows(after) - _sent_rows(before)
        return d == chk["outbox_sent_delta"], f"outbox rows state=sent +{d} (want +{chk['outbox_sent_delta']})"
    if chk.get("send_done"):
        ev = row.get("walk_events") or []
        ok = row.get("walk_outcome") == "done" and "landed" in ev and (row.get("walk_steps") or [""])[-1] == TABLE["last"]
        return ok, f"walk {'→'.join(ev)} outcome={row.get('walk_outcome')}"
    if chk.get("asks"):
        return row.get("reply_kind") == "question", f"reply kind={row.get('reply_kind')}"
    if chk.get("no_claim"):
        return not row.get("claims_without_act"), f"claims_without_act={row.get('claims_without_act')}"
    wid = chk.get("widget")
    a, b = after.get(wid), before.get(wid)
    if "contains" in chk:
        needle = str(chk["contains"]).lower()
        got = needle in json.dumps(a, ensure_ascii=False).lower()
        was = needle in json.dumps(b, ensure_ascii=False).lower()
        return (got and not was), f"{wid} contains «{chk['contains']}»: before={was} after={got}"
    val = _path(a, chk["path"])
    if chk.get("increases"):
        was = _path(b, chk["path"])
        ok = isinstance(val, (int, float)) and isinstance(was, (int, float)) and val > was
        return ok, f"{wid}.{chk['path']} {was!r}→{val!r} (want it to move)"
    if "eq" in chk:
        return val == chk["eq"], f"{wid}.{chk['path']}={val!r} (want {chk['eq']!r})"
    if "gte" in chk:
        return isinstance(val, (int, float)) and val >= chk["gte"], f"{wid}.{chk['path']}={val!r} (want ≥{chk['gte']})"
    return False, f"unknown check {chk}"


def _end_state_read(evs: list[dict]) -> list[str]:
    """The brief's `end_state` answer with its confidence, wherever the turn's verdicts carried it ([] = not asked)."""
    out = []
    for e in evs:
        if e.get("kind") != "brain":
            continue
        label = str(e.get("label") or "")
        if label.startswith("jev read end_state"):
            out.append(f"{e.get('choice')} ({e.get('confidence')})")
        q = (e.get("per_question") or {}).get("end_state") if label.startswith("jev turn-brief") else None
        if isinstance(q, dict):
            out.append(f"{q.get('choice')} ({q.get('confidence')})")
    return out[:2]


def _sent_rows(data: dict) -> int:
    rows = (data.get("mensajeria") or {}).get("outbox") or []
    return sum(1 for r in rows if isinstance(r, dict) and r.get("state") == "sent")


def _widgets_of(case: dict) -> list[str]:
    out = {c["widget"] for c in case.get("checks") or () if c.get("widget")}
    if case.get("send") or case.get("errand"):
        out.add("mensajeria")
    return sorted(out)


def run_case(eng, tl: Timeline, case: dict, seen: set, stop_line: str, double=None) -> dict:
    session = f"pr-{case['id']}-{int(time.time())}"
    for pre in case.get("pre") or ():
        eng.post("/api/flash/say", {"text": pre, "session": session, "execute": True}, timeout=120)
    widgets = _widgets_of(case)
    before = {w: eng.get(f"/widgets/{w}/data")[1] for w in widgets}
    mark = tl.mark()
    n_sent = len(double.sent) if double is not None else 0
    t0 = time.time()
    code, res = eng.post("/api/flash/say", {"text": case["text"], "session": session, "execute": True}, timeout=150)
    secs = round(time.time() - t0, 2)
    res = res if isinstance(res, dict) else {"reply": str(res)}
    trace = res.get("trace")
    route, walk, new_ids = None, [], set()
    deadline = time.time() + (45 if case.get("send") else 8)
    quiet_after = time.time() + 5
    while time.time() < deadline:
        evs = tl.since(mark)
        route = next((e for e in evs if e.get("kind") == "play" and e.get("label") in ("route", "route_drift")
                      and (not trace or e.get("trace") == trace)), None)
        walk, new_ids = _steps(evs, seen)
        if route is not None:
            if not case.get("send"):
                break
            if any(e.get("step") == TABLE["last"] for e in walk):
                break
            if not walk and time.time() > quiet_after + (4 if double is not None else 0):
                break
        time.sleep(0.5)
    time.sleep(1.0 if not case.get("send") else 0)
    evs = tl.since(mark)
    walk, new_ids = _steps(evs, seen)
    seen |= new_ids
    rec = {k: route.get(k) for k in ("label", "dest", "legacy", "agree", "unserved", "named", "ran")} if route else None
    if case.get("send") and double is not None:
        time.sleep(2.0)                                          # a settled row's echo reaches the outbox
    after = {w: eng.get(f"/widgets/{w}/data")[1] for w in widgets}
    stop_reply = None
    if case.get("errand"):
        sc, sr = eng.post("/api/flash/say", {"text": stop_line, "session": session, "execute": True}, timeout=120)
        stop_reply = (sr or {}).get("reply") if isinstance(sr, dict) else str(sr)
    row = {
        "id": case["id"], "cls": case["cls"], "group": case.get("group"), "note": case.get("note"),
        "text": case["text"], "expect_dest": case["dest"], "expect_ran": case.get("ran"),
        "http": code, "trace": trace, "secs": secs, "reply": res.get("reply"), "reply_kind": reply_kind(res.get("reply")),
        "tool_calls": [c.get("name") + (":" + str((c.get("args") or {}).get("widget_id")) + ":" +
                                        str((c.get("args") or {}).get("action")) if c.get("name") == "widget_data" else "")
                       for c in res.get("tool_calls") or [] if isinstance(c, dict)],
        "consequences": res.get("consequences") or [],
        "route": rec,
        "send_task": any(e.get("kind") == "brain" and "send task" in str(e.get("label")) for e in evs),
        "walk_steps": [e.get("step") for e in walk],
        "walk_events": [e.get("event") for e in walk],
        "walk_outcome": next((e.get("outcome") for e in reversed(walk) if e.get("outcome")), None),
        "stop_reply": stop_reply,
        "double_sends": double.sends_since(n_sent) if double is not None else [],
        "opener": ("verdict" if any("the send the verdict identified" in str(e.get("label")) for e in evs)
                   else "model" if any("an act that leaves is a task" in str(e.get("label")) for e in evs) else None),
        "end_state_read": _end_state_read(evs),
        "settle": [f"{(e.get('delta') or {}).get('state')}:{(e.get('delta') or {}).get('verdict')}" for e in evs
                   if e.get("kind") == "task_progress" and e.get("writer") == "settle"][:3],
    }
    row["claims_without_act"] = bool(rec and rec.get("unserved") and not rec.get("ran"))
    fails = []
    if rec is None:
        fails.append("no play/route event for the turn")
    elif rec.get("dest") != case["dest"]:
        fails.append(f"dest {rec.get('dest')} ≠ {case['dest']}")
    if case.get("legacy") and rec is not None and rec.get("legacy") != case["legacy"]:
        fails.append(f"legacy {rec.get('legacy')} ≠ {case['legacy']}")
    if case.get("ran") and rec is not None and not set(case["ran"]) & set(rec.get("ran") or ()):
        fails.append(f"ran {rec.get('ran')} has none of {case['ran']}")
    checks = []
    for chk in case.get("checks") or ():
        ok, what = _check(chk, before, after, row)
        checks.append({"ok": ok, "what": what})
        if not ok:
            fails.append("check: " + what)
    row["checks"], row["fails"], row["pass"] = checks, fails, not fails
    row["trace_lines"] = [
        f"{e.get('rel_ms', 0):>8} {e.get('kind')}/{e.get('label')} {str(e.get('text') or '')[:80]}"
        for e in evs if e.get("kind") in ("play", "task_state") or (
            e.get("kind") == "brain" and any(w in str(e.get("label")) for w in ("send task", "show_panel", "escalat")))
    ][:40]
    return row


# --------------------------------------------------------------------------------------------- report


def _cell(v) -> str:
    return str(v).replace("|", "\\|").replace("\n", " ")


def markdown(rows: list[dict], sameness: dict) -> str:
    out = ["| id | expect | dest | legacy | agree | unserved | named | ran | walk | opener | end_state | double | checks | claims w/o act | s | pass | reply |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        rt = r.get("route") or {}
        out.append("| " + " | ".join(_cell(x) for x in (
            r["id"], r["expect_dest"], rt.get("dest"), rt.get("legacy"), rt.get("agree"), rt.get("unserved"),
            ",".join(rt.get("named") or []), ",".join(rt.get("ran") or []),
            "→".join(r.get("walk_events") or []) + (f" [{r.get('walk_outcome')}]" if r.get("walk_outcome") else ""),
            r.get("opener") or "", "; ".join(r.get("end_state_read") or []) or ("not asked" if r.get("walk_events") else ""), len(r.get("double_sends") or []),
            "; ".join(("✓ " if c["ok"] else "✗ ") + c["what"] for c in r.get("checks") or []),
            "⚑" if r.get("claims_without_act") else "", r["secs"], "PASS" if r["pass"] else "MISS",
            (r.get("reply") or "")[:140])) + " |")
    per = {}
    for r in rows:
        p = per.setdefault(r["cls"], [0, 0])
        p[0 if r["pass"] else 1] += 1
    out += ["", "| class | pass | miss |", "|---|---|---|"] + [f"| {k} | {v[0]} | {v[1]} |" for k, v in sorted(per.items())]
    out += ["", "**Sameness (class E)**", ""]
    for g, s in sameness.items():
        out.append(f"- {g}: {'SAME' if s['same'] else 'DIFFERENT'} — " + " / ".join(_cell(x) for x in s["signatures"]))
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma-separated case ids")
    ap.add_argument("--no-double", action="store_true", help="WhatsApp off, as a bare sandbox (no test double)")
    ap.add_argument("--out", default="", help="run directory (default tests/runs/play-routing-<stamp>)")
    args = ap.parse_args(argv)
    sys.path.insert(0, str(ENGINE))
    os.environ.setdefault("ZAELAR_TEST_ACTOR", "play-routing-bench")
    import tests.platform.sandbox_engine as se
    from tests.platform.voice_sandbox import seed_language
    from tests.use_cases.lab.stage import _brain_env_from_table

    spec = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
    only = {s.strip() for s in args.only.split(",") if s.strip()}
    cases = [c for c in spec["cases"] if not only or c["id"] in only]
    run = Path(args.out).resolve() if args.out else ENGINE / "tests" / "runs" / f"play-routing-{time.strftime('%Y%m%d-%H%M%S')}"
    ws = run / "ws"
    (ws / "config").mkdir(parents=True, exist_ok=True)
    seed_language(ws, spec.get("lang", "es"))
    cfg = ws / "config" / "v2.json"
    data = json.loads(cfg.read_text()) if cfg.exists() else {}
    data["play"] = {"shadow": True, "own": True}
    cfg.write_text(json.dumps(data))
    from . import wa_double
    double = None if args.no_double else wa_double.Double(se.free_port()).start()
    wa_env = wa_double.env_for(double, ws) if double is not None else {}
    if double is not None:                     # enabled in the store, where a paired install keeps it
        (ws / "config" / "connectors.json").write_text(json.dumps({"whatsapp": {"enabled": True}}))
    eng, rows, t_all = None, [], time.time()
    try:
        try:
            eng = se.spawn_engine(workspace=ws, port=se.free_port(), log_path=ws / "engine.log", boot_timeout=240,
                                  extra_env={"MEMORY_RERANK": "off", **_brain_env_from_table(), **wa_env})
        except Exception as e:  # noqa: BLE001 — a sandbox that does not boot is infrastructure, not a routing miss
            print(f"sandbox did not boot: {e!r}", flush=True)
            return 2
        print("READY", eng.base_url, flush=True)
        if double is not None:
            from tests.waiting import until_sync

            def _wa() -> dict:
                _, conns = eng.get("/api/connectors")
                return next((c for c in (conns or {}).get("connectors") or [] if c.get("id") == "whatsapp"), {})
            try:
                until_sync(lambda: _wa().get("connected") is True, "WhatsApp read as connected through the double",
                           timeout_s=60, poll_s=1.0)
            except AssertionError as e:
                print(e, flush=True)
            wa = _wa()
            wa_double.assert_isolated(wa_env, ws, double)
            print(f"WhatsApp double on :{double.port} · /api/connectors whatsapp connected={wa.get('connected')} "
                  f"status={wa.get('status')} config={wa.get('config')}", flush=True)
            if wa.get("connected") is not True:
                print("the engine never read WhatsApp as connected through the double", flush=True)
                return 2
        for c in spec.get("seed_contacts") or ():
            eng.post("/widgets/contactos/action", {"action": "add_contact", "payload": c})
        tl, seen = Timeline(ws / "logs" / "timeline-latest.jsonl"), set()
        for case in cases:
            row = run_case(eng, tl, case, seen, spec.get("stop", ""), double)
            rows.append(row)
            rt = row.get("route") or {}
            print(f"{row['id']:>3} {'PASS' if row['pass'] else 'MISS'} dest={rt.get('dest')} legacy={rt.get('legacy')} "
                  f"ran={rt.get('ran')} opener={row['opener']} double={len(row['double_sends'])} {'⚑claims_without_act ' if row['claims_without_act'] else ''}walk={'→'.join(row['walk_events'])} {row['secs']}s · {(row['reply'] or '')[:90]!r}"
                  + (f"  ✗ {row['fails']}" if row["fails"] else ""), flush=True)
    finally:
        if eng is not None:
            se.stop_engine(eng)
        if double is not None:
            double.stop()
    groups = {}
    for r in rows:
        if r.get("group"):
            groups.setdefault(r["group"], []).append(signature(r))
    sameness = {g: {"same": len(set(s)) == 1, "signatures": [list(x) for x in s]} for g, s in groups.items()}
    result = {"run": str(run), "seconds": round(time.time() - t_all, 1), "rows": rows, "sameness": sameness,
              "pass": sum(r["pass"] for r in rows), "miss": sum(not r["pass"] for r in rows)}
    (run / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    (run / "results.md").write_text(markdown(rows, sameness), encoding="utf-8")
    print(f"\n{result['pass']} pass · {result['miss']} miss · {result['seconds']}s · {run}/results.md", flush=True)
    return 0 if result["miss"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
