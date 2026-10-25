"""server/screens_api.py — the HTTP face of `voice/screens.py` (V2-792: one agent, one voice, many screens).

  · `POST /api/chat`           — a typed line from ANY screen, into the one conversation.
  · `POST /api/screens/beat`   — a screen says whether it is visible (sent on `visibilitychange`).
  · `POST /api/screens/bring`  — «bring it here»: a card that plays on one screen at a time moves to this one.
  · `GET  /api/screens`        — which screens are open, which holds the voice, which one is active.
"""
from __future__ import annotations

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from voice import screens
from voice.observer import emit

router = APIRouter()


def _single(card_id: str) -> bool:
    from widgets import screen_policy
    return screen_policy.of_card(card_id) == screen_policy.SINGLE


screens.register_policy(_single)     # the voice layer asks the widgets' own declaration, never a list of its own


@router.post("/api/chat")
async def chat(text: str = Body(..., embed=True), dev: str = Body("", embed=True)) -> JSONResponse:
    """Deliver a typed line to the live session, whichever screen typed it.

    The surface holding the voice types through its LiveKit data channel, as before. Every other surface has no
    room — the voice lock gives a room to one surface — so its typed line used to sit in a queue waiting for a
    connection the lock would never grant. `ok:false, reason:"no_session"` means nobody holds a live session: the
    caller then brings the voice up itself, which is the only way a session exists."""
    from nucleo import runstate
    if runstate.stopped():
        return JSONResponse({"ok": False, "reason": "stopped"}, status_code=409)
    t = str(text or "").strip()[:4000]
    if not t:
        return JSONResponse({"ok": False, "reason": "empty"}, status_code=400)
    if not await screens.deliver_typed(t, dev):
        return JSONResponse({"ok": False, "reason": "no_session"})
    return JSONResponse({"ok": True})


@router.post("/api/screens/beat")
def beat(payload: dict = Body(...)) -> dict:
    dev = (payload or {}).get("dev")
    visible = (payload or {}).get("visible")
    screens.beat(dev, visible=visible if isinstance(visible, bool) else None)
    if (payload or {}).get("touched"):
        screens.touched(dev)
    return {"ok": True}


@router.post("/api/screens/bring")
def bring(id: str = Body(..., embed=True), dev: str = Body("", embed=True)) -> dict:
    """The asking screen has just opened the card; every other screen that has it open lets it go. One event,
    addressed by `to`, so the order is the same whether the operator tapped a chip or said «tráelo aquí»."""
    d = screens.clean(dev)
    cid = str(id or "").strip()[:120]
    if not d or not cid:
        return {"ok": False}
    screens.touched(d)
    if screens.note_playing(cid, d) == d:
        return {"ok": True, "to": d, "already": True}     # the server announced this move when the order landed
    emit("screens", "moved", extra={"id": cid, "to": d, "origin_dev": d})
    return {"ok": True, "to": d}


@router.get("/api/screens")
def list_screens() -> dict:
    return {"screens": screens.open_screens(), "voice": screens.holder(), "active": screens.current()}
