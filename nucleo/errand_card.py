"""nucleo/errand_card.py — the ONE card that represents an errand on screen (V2-797).

One request opened three cards: the browser's monitor card when the errand started (it had no sheet yet, so the
monitor was «the only surface»), the results sheet when the worker wrote its first rows, and — after a restart —
a second sheet beside the first. Three doors each answered «what should he look at?» on their own.

The answer is ONE rule, asked here by every door that raises a card for an errand's browser:

  * an errand presents its DELIVERABLE — the results sheet, whose PROCESS tab embeds the live browser (V2-571);
  * the browser's live view never opens as a card of its own just because the errand started: until there is
    something to deliver, the activity indicator and the voice say it is working;
  * when the operator MUST act in the page (a wall such as a captcha, a login), the errand's sheet is raised —
    opened now if the errand can hold one — so the page he has to act on is inside the surface that will also
    hold the result;
  * only a tab that belongs to no errand (he is browsing by hand), or an errand whose deliverable is not a sheet
    (a report, a picture viewer), falls back to the monitor card — there it is the only place the page can be seen.

Generic by construction: nothing here knows what the errand is for (a table, a hotel, a flight, a shopping list).
"""
from __future__ import annotations


def card_for(nav_task: str, *, must_act: bool = False) -> str:
    """The card id to raise for this browser tab, or "" when nothing should open now."""
    tid = str(nav_task or "").strip()
    if not tid:
        return ""
    from nucleo import dispatch as _d, sheets as _sheets
    from widgets.navegador import tasks as navtasks
    from widgets.results import data as results
    sessions, live = list(_d._SESSIONS.values()), _d.LIVE_SESSION_STATES
    sheet = str((navtasks.get(tid) or {}).get("sheet") or "") or _sheets.sheet_for_nav_task(tid, sessions)
    if sheet:
        return results.instance_id(sheet)
    if not must_act:
        return ""
    sheet = _sheets.sheet_for_delivery(tid, sessions, live, show=False)   # opens the errand's sheet, if it takes one
    if not sheet:
        return navtasks.inst_id(tid)
    navtasks.set_sheet(tid, sheet)          # the tab now refreshes the sheet's PROCESS tab on every change
    return results.instance_id(sheet)


def monitor_stands(nav_task: str) -> bool:
    """Is this tab's monitor card a card of its own? Only for a tab no live errand drives and no sheet holds —
    an errand's tab lives inside the errand's card, so a refresh must not bring its monitor back beside it."""
    tid = str(nav_task or "").strip()
    if not tid:
        return False
    from nucleo import dispatch as _d
    from widgets.navegador import tasks as navtasks
    if str((navtasks.get(tid) or {}).get("sheet") or ""):
        return False
    return not any(tid in (str(getattr(r, "nav_task", "") or ""), str(getattr(r, "task_id", "") or ""))
                   for r in list(_d._SESSIONS.values()) if r.status in _d.LIVE_SESSION_STATES)
