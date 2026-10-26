"""nucleo/pending_work.py — the ONE reader of what is still pending for him, as durable rows (V2-799).

«Termina esas tareas», «sigue con lo de antes», «finish those»: a turn that refers to earlier work names no errand in
its own words, so anything that reads only the words reads a fragment. Measured live (2026-10-26): with an email
held for his «send it» and a table hunt waiting for his pick, «termina esas tareas» had its two model-written
commissions annulled as «a fragment», and a backstop rebuilt ONE errand by gluing an old utterance to the new one —
losing date, time, party size and area — and the worker refused it.

What is pending is not in the words, it is in the STATE, and the state already has rows:

  · the task board (`nucleo/tasks.py`): errands running, waiting or pending, and errands that ended recently (a
    delivery that waits for his choice is a finished row with its sheet — the row carries the brief, the name, the
    sheet and the outcome);
  · rows a widget holds for his word, declared by the widget itself: `pending_rows() -> [{id, title, state,
    resume: {action, payload}}]` in its data module (the mail card's held drafts, V2-800). Nothing here knows what a
    draft is.

Each row says how it RESUMES from itself — an errand from its own brief, sheet and outcome; a widget row through its
own declared action (and so through its own confirm gate). Which rows his turn means is decided elsewhere, by a
verdict over these rows (`nucleo/flash/resume_turn.py`); this module only lists them. Never raises.
"""
from __future__ import annotations

import importlib
import time

from loguru import logger

#: How far back a finished errand is still «earlier work» he may ask to finish. A bound on what is offered to the
#: verdict, not a judgement: the verdict still has to pick the row.
RECENT_S = 12 * 3600
#: How many rows reach the verdict — a glance at what is pending, newest first.
MAX_ROWS = 8
#: Widgets that may hold rows for his word. Read from the catalogue, so a new widget that declares the hook joins.
_HOOK = "pending_rows"


def _task_rows(now: float) -> list[dict]:
    from nucleo import tasks as _tasks
    ts = _tasks.store()
    live = ts.tasks_where(states=ts.LIVE_STATES, modes=("now",), visible_only=True, limit=MAX_ROWS,
                          exclude_kinds=("inline",))
    ended = ts.tasks_where(states=("done", "failed"), modes=("now",), visible_only=True, limit=MAX_ROWS,
                           newest_first=True, exclude_kinds=("inline",), since=now - RECENT_S)
    out = []
    for r in live + ended:
        uid = str(r.get("id") or "")
        if not uid or any(o["id"] == uid for o in out):
            continue
        out.append({"id": uid, "source": "task", "title": str(r.get("title") or r.get("goal") or "")[:80],
                    "state": str(r.get("state") or ""), "brief": str(r.get("goal") or ""),
                    "outcome": str(r.get("outcome") or ""), "sheet": str(r.get("sheet") or ""),
                    "surface": str(r.get("surface") or ""), "kind": str(r.get("kind") or "generic"),
                    "at": float(r.get("finished_at") or r.get("started_at") or r.get("created_at") or 0)})
    return out


def _widget_rows() -> list[dict]:
    out = []
    try:
        from widgets import runtime
        ids = [str(w.get("id") or "") for w in (runtime.catalog() or [])]
    except Exception as e:  # noqa: BLE001
        logger.debug(f"pending_work: no widget catalogue ({e})")
        return out
    for wid in ids:
        try:
            hook = getattr(importlib.import_module(f"widgets.{wid}.data"), _HOOK, None)
        except Exception as e:  # noqa: BLE001 — a widget without a data module holds nothing for him
            logger.debug(f"pending_work: {wid} has no data module ({e})")
            continue
        if not callable(hook):
            continue
        try:
            for r in hook() or []:
                if isinstance(r, dict) and r.get("id") and isinstance(r.get("resume"), dict):
                    out.append({**r, "source": "widget", "widget": wid, "id": f"{wid}:{r['id']}",
                                "title": str(r.get("title") or "")[:80], "at": float(r.get("at") or 0)})
        except Exception as e:  # noqa: BLE001
            logger.info(f"pending_work: {wid}.{_HOOK} failed ({e}) — its rows are not offered")
    return out


def rows(now: float | None = None) -> list[dict]:
    """Every pending row, newest first, at most `MAX_ROWS`. `[]` when nothing is pending."""
    now = float(now if now is not None else time.time())
    found: list[dict] = []
    try:
        found += _task_rows(now)
    except Exception as e:  # noqa: BLE001
        logger.info(f"pending_work: the task board is unreadable ({e})")
    found += _widget_rows()
    return sorted(found, key=lambda r: -float(r.get("at") or 0))[:MAX_ROWS]


def label(row: dict) -> str:
    """One row as the verdict reads it: what it is called, where it stands, what it delivered."""
    bits = [str(row.get("title") or "")]
    if row.get("state"):
        bits.append(f"state: {row['state']}")
    if row.get("outcome"):
        bits.append(f"delivered: {str(row['outcome'])[:120]}")
    return " · ".join(b for b in bits if b)


def errand_brief(row: dict, his_words: str) -> str:
    """The brief a resumed errand runs with — built from ITS ROW, never from utterances glued together.

    His original words stay verbatim (the fidelity `errand_title` explains), and the row's own state travels with
    them so the worker continues instead of restarting blind: what it already delivered, and his words now."""
    head = str(row.get("brief") or row.get("title") or "").strip()
    state = [f"state: {row.get('state')}"] if row.get("state") else []
    if row.get("outcome"):
        state.append(f"already delivered: {str(row['outcome'])[:600]}")
    return (f"{head}\n\n[Resumed from its own task row ({'; '.join(state)}). His words now: «{his_words.strip()}». "
            "Continue from what was delivered: if it is waiting for his choice, ask him for it or use the one his "
            "words name; do not start over.]")
