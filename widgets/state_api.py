"""widgets/state_api.py — `POST /widgets/{wid}/state`, a surface's report of what an app shows (V2-884 C2).

The door is `widgets.state.report`, run off the event loop; this module serves it, tells it when a one-screen app moves
off a screen (`voice.screens.on_moved` → `state.forget`), and hands a declared fact's tell to the late-report seam on
the loop: a fact that turned ON arms its sentence (spoken only over a recent agent order, after `SETTLE_S`), one that
turned OFF withdraws it (C2b) — the muted autoplay start that sounds a second later is never said.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from voice import screens
from widgets import state

router = APIRouter()
screens.on_moved(lambda card, old_dev: state.forget(card, old_dev))


@router.post("/widgets/{wid}/state")
async def widget_state(wid: str, body: dict = Body(default_factory=dict)):
    code, out = await asyncio.to_thread(state.report, wid, body)          # disk and the app's code, off the loop
    on, off = out.pop("_on", []), out.pop("_off", [])
    if on or off:
        from widgets import late_report
        said, withdrawn = state.tells(wid, on, off)
        if withdrawn:
            late_report.retract(wid)
        for line in said:
            late_report.deliver(wid, {"tell": line})
    return JSONResponse(out, status_code=code)
