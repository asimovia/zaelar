"""The OPEN block: what is open for him, each thing by its short NUMBER (INI-078 segregation S3).

One view of the ONE queue (`queue.view()`), the same his screen paints: each task of the queue by its `#n`, its owner,
its state and what it DOES (its title, never the sentence that commissioned it); a task waiting for him with the
question it asked him, word for word, how long ago, and its declared answers. At most `MAX_LINES` lines, the rest
counted. A question open on something that is not a task of the queue (an act waiting for his yes) is listed by its
key. Then the tasks that ENDED a moment ago (`queue.recent`, INI-078 #5), by their `#n` with how they ended: his words
to one («not these, others») reopen the same task. Last, our own last question to him: a bare «yes» answers THAT
before any task.

The model refers to a task by its `#n` (`task_say`, `task_priority`, `task_move`, `stop_task`); a number that is not
here fails and gives this block back. Its words: the labels below are protocol for the model, not his language.
"""
from __future__ import annotations

import time

#: the most lines the block takes; past it, the rest is counted («… and N more pending»)
MAX_LINES = 12


def _age(since: int | float | None, now: float) -> str:
    s = max(0, int(now - float(since or now)))
    return f"{s} s ago" if s < 90 else f"{s // 60} min ago" if s < 5400 else f"{s // 3600} h ago"


def _answers(row: dict) -> str:
    try:
        from nucleo.circuit import asker
        opts = (asker.artefact(str(row.get("id") or "")) or {}).get("options") or []
        return " / ".join(str(o.get("label") if isinstance(o, dict) else o) for o in opts if o)
    except Exception as e:  # noqa: BLE001 — a question with no declared answers is still listed
        __import__("loguru").logger.debug(f"open_block: the answers of {row.get('id')} unread ({e!r})")
        return ""


def line(row: dict, now: float, place: int = 0) -> str:
    """One task of the queue as the model reads it."""
    bits = [f"#{row.get('num')}", str(row.get("owner") or ""), str(row.get("state") or ""),
            " ".join(str(row.get("title") or row.get("goal") or "").split())[:140]]
    prog = row.get("progress") or {}
    if row.get("state") == "running":
        if prog.get("total"):
            bits.append(f"step {min(int(prog.get('done') or 0), int(prog['total']))}/{prog['total']}")
        if row.get("phase"):
            bits.append(str(row["phase"])[:100])
    elif row.get("state") == "waiting" and row.get("ask"):
        asked = f"ASKED ({_age(row.get('waiting_since'), now)}): «{str(row['ask'])[:240]}»"
        bits.append(asked + (f" · answers: {a}" if (a := _answers(row)) else ""))
    elif row.get("state") == "pending" and place:
        bits.append(f"{place}{('st', 'nd', 'rd')[place - 1] if place < 4 else 'th'} in line")
    return " · ".join(b for b in bits if b)


def ended(row: dict, now: float) -> str:
    """A task archived a moment ago, as the model reads it: its number, how it ended, when, what it did."""
    bits = [f"#{row.get('num')}", str(row.get("owner") or ""),
            f"ended {row.get('state')} ({_age(row.get('finished_at'), now)})",
            " ".join(str(row.get("title") or row.get("goal") or "").split())[:140]]
    if (out := " ".join(str(row.get("outcome") or "").split())):
        bits.append(f"«{out[:160]}»")
    return " · ".join(b for b in bits if b)


def _other_questions(numbered: set) -> list[str]:
    """Questions open on something that is not a task of the queue (an act waiting for his yes), by their key."""
    out = []
    try:
        from nucleo.switchboard import board
        for p in board.open_processes():
            if p.get("question") and str(p.get("key") or "") not in numbered:
                out.append(f"[{p['key']}] · question · {str(p.get('title') or '')[:120]} · ASKED: «"
                           f"{str(p['question'])[:240]}»")
    except Exception as e:  # noqa: BLE001 — the queue's own tasks still list
        __import__("loguru").logger.debug(f"open_block: the other questions unread ({e!r})")
        return out
    return out


def _asked_last(now: float) -> str:
    from nucleo.conversation_host import route
    text, at = route.last_said()
    t = text.rstrip()
    return f"YOU ASKED HIM LAST ({_age(at, now)}): «{t[:240]}»" if t.endswith("?") else ""


def text(now: float | None = None) -> str:
    """The block, or "" when nothing is open."""
    from nucleo import queue
    now = time.time() if now is None else now
    view = queue.view()
    lines, pending_left = [], 0
    for lane in queue.OWNERS:
        lines += [line(r, now) for r in view[lane]["running"] + view[lane]["waiting"]]
    for lane in queue.OWNERS:
        for i, r in enumerate(view[lane]["pending"], 1):
            if len(lines) < MAX_LINES:
                lines.append(line(r, now, place=i))
            else:
                pending_left += 1
    numbered = {str(r.get("id") or "") for lane in queue.OWNERS for st in view[lane].values() for r in st}
    extra = _other_questions(numbered)
    lines = lines[:MAX_LINES] + extra[:max(0, MAX_LINES - len(lines))]
    if pending_left:
        lines.append(f"… and {pending_left} more pending")
    lines += [ended(r, now) for r in queue.recent(now)][:max(0, MAX_LINES - len(lines))]
    if asked := _asked_last(now):
        lines.append(asked)
    return "\n".join(lines)
