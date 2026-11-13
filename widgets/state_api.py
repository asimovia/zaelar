"""widgets/state_api.py — `POST /widgets/{wid}/state`, a surface's report of what an app shows (V2-884 C2).

The door is `widgets.state.report`; this module only serves it, and tells it when a one-screen app moves off a screen
(`voice.screens.on_moved` → `state.forget`), so the old screen's report stops speaking for it.
"""
from __future__ import annotations

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from voice import screens
from widgets import state

router = APIRouter()
screens.on_moved(lambda card, old_dev: state.forget(card, old_dev))


@router.post("/widgets/{wid}/state")
async def widget_state(wid: str, body: dict = Body(default_factory=dict)):
    code, out = state.report(wid, body)
    return JSONResponse(out, status_code=code)
