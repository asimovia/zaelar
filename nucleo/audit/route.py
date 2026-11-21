"""What the one decider did with each batch of his words in a session, read back for the auditor (INI-078 S1).

    python -m nucleo.audit.route --session <id> [--json]

One entry per `route` event (`nucleo/conversation_host/route.py`), in order: what he said, our last line before it,
the open tasks as the model read them, the class (A conversation · B new task · C to an open task · D the queue) and
the acts with their arguments. The auditor marks each one right or wrong; the signals that follow are its `hints`,
computed here from the records alone (no store of their own), never the mark:

  · `undone:<act>` — a `task_unsay` or `task_restore` of a #number it acted on, within `UNDO_S` after it;
  · `redrafted` — its `draft_edit` of a draft edited again within `UNDO_S`;
  · `stopped_soon` — a `stop_task` within `STOP_S` after its `start_task`;
  · `not_open:<act>` — an act on a number that was not open; `refused:<act>` — an act the gateway refused.
Read-only.
"""
from __future__ import annotations

import argparse
import json

#: how soon an undo or a second edit after a decision hints that it was wrong; how soon a stop after a start
UNDO_S, STOP_S = 120, 60
UNDOES = ("task_unsay", "task_restore")


def decisions(session_id: str, *, limit: int = 2000) -> list[dict]:
    """The session's `route` records, oldest first, each `{ts_ms, corr_id, class, his_text, our_last, open, acts,
    model, ms, outcome}` — plus the `near` records (a new task very like an open one) as `{near: {...}}`."""
    from observability import flows
    out = []
    for e in flows.events(session_id=str(session_id), limit=limit):
        if e.get("kind") != "route":
            continue
        try:
            p = json.loads(e.get("payload") or "{}") if isinstance(e.get("payload"), str) else dict(e.get("payload") or {})
        except ValueError:
            p = {}
        body = p.get("extra") if isinstance(p.get("extra"), dict) else p
        row = {"ts_ms": e.get("ts_ms"), "corr_id": e.get("corr_id")}
        row.update({"near": body} if e.get("label") == "near" else
                   {k: body.get(k) for k in ("class", "his_text", "our_last", "open", "acts", "model", "ms", "outcome")})
        out.append(row)
    return hints(out)


def _names(d: dict) -> list[str]:
    return [str(a.get("name") or "") for a in d.get("acts") or []]


def _tasks(d: dict, name: str = "") -> set[str]:
    """The #numbers a decision's acts (named `name`, or any) acted on."""
    return {str((a.get("args") or {}).get("task")) for a in d.get("acts") or []
            if (a.get("args") or {}).get("task") and (not name or a.get("name") == name)}


def hints(decisions: list[dict]) -> list[dict]:
    """Each decision with the signals that followed it (`hints`, see the module's doc), in order."""
    rows = [d for d in decisions if "near" not in d]
    for i, d in enumerate(rows):
        h, t0 = [], int(d.get("ts_ms") or 0)
        for a in d.get("acts") or []:
            st = str(a.get("status") or "")
            if st.startswith("refused"):
                h.append(f"refused:{a.get('name')}")
            elif "not_open" in st:
                h.append(f"not_open:{a.get('name')}")
        drafted = _tasks(d, "draft_edit")
        touched = _tasks(d)
        for later in rows[i + 1:]:
            dt = (int(later.get("ts_ms") or 0) - t0) / 1000.0
            if dt > UNDO_S:
                break
            h += [f"undone:{n}" for n in UNDOES if touched & _tasks(later, n)]
            if drafted & _tasks(later, "draft_edit"):
                h.append("redrafted")
            if dt <= STOP_S and "start_task" in _names(d) and "stop_task" in _names(later):
                h.append("stopped_soon")
        d["hints"] = list(dict.fromkeys(h))
    return decisions


def _line(d: dict) -> str:
    if "near" in d:
        n = d["near"] or {}
        return f"  ~ near: new {n.get('new')} looks like open {n.get('open')} ({n.get('by')})"
    acts = "; ".join(f"{a.get('name')}({json.dumps(a.get('args'), ensure_ascii=False)[:120]})→{a.get('status')}"
                     for a in d.get("acts") or []) or "—"
    return (f"[{d.get('class')}] «{d.get('his_text')}»\n    after: «{(d.get('our_last') or '')[:160]}»\n"
            f"    open: {(d.get('open') or '—').replace(chr(10), ' | ')[:400]}\n    acts: {acts}  ({d.get('model')}, "
            f"{d.get('ms')} ms, {d.get('outcome')})" + (f"\n    hints: {', '.join(d['hints'])}" if d.get("hints") else ""))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--session", required=True)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    got = decisions(a.session)
    print(json.dumps(got, ensure_ascii=False, indent=1) if a.json else "\n".join(_line(d) for d in got) or "(none)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
