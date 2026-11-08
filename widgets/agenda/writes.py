"""widgets/agenda/writes.py — the agenda's own record of the meeting writes that LANDED.

An action's end state (`manifest.json` `actions.<a>.done_when`) must describe what THIS call left true, never
something an older row satisfies: «Dentist on the 12th is in the calendar» is already true when he had it there
last week, and «the notice is set» is true of every row that got its default notice. A row of `meetings` alone
cannot tell the two apart — meetings carry no id of their own, and the store is the operator's calendar, not a
log.

So every meeting write that lands appends one entry here, with an id: `{id, action, title, asked, date, startTime,
at}`.
The end state pairs the REAL outcome (the meeting row, the occurrence gone) with `writes … expect: added` — an
entry that did not exist when the request was born (`nucleo/circuit/baseline.py`). Bounded: only the last
`KEEP` entries stay; the baseline only ever needs the ones that match a title right now.
"""
from __future__ import annotations

import contextvars
import time
import uuid

KEY = "writes"
KEEP = 40

#: The title as the CALL said it, set by `data.apply_action` before any normalisation (`series.normalize`,
#: `edit.day_out_of_title`, `title_when.said_when` all rewrite it): the end state is rendered from the call's raw
#: payload, so that is the spelling the entry must carry. The outermost call wins (an `update_meeting` that hands
#: its hour to `move_meeting` re-enters with a payload already rewritten).
ASKED: contextvars.ContextVar = contextvars.ContextVar("agenda_asked_title", default=None)


def note(db: dict, action: str, row: dict | None = None, *, title: str = "", asked: str = "") -> dict:
    """Record that `action` landed on `row` (or on `title` when the row is gone, as in a cancel). `asked` is the
    title as the call said it: the card finds a meeting tolerantly («the dentist» → «Dentist»), and an end state
    rendered from the call's words matches `title|asked~`, so the tolerance of the finder is never read as
    «not done». Returns the entry."""
    r = row if isinstance(row, dict) else {}
    entry = {"id": uuid.uuid4().hex[:12], "action": str(action or ""),
             "title": str(r.get("title") or title or ""), "asked": str(ASKED.get() or asked or "")[:160],
             "date": str(r.get("date") or ""),
             "startTime": str(r.get("startTime") or ""), "at": round(time.time(), 3)}
    log = db.get(KEY) if isinstance(db.get(KEY), list) else []
    db[KEY] = (log + [entry])[-KEEP:]
    return entry
