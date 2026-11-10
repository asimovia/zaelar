"""server/device_api.py — a screen tells the engine where it is (V2-875). Mechanism in `nucleo/where.py`.

An operator route (mutating): admitted like every click of his page (`server/operator_gate.py`). Refused with
`reason: "off"` when the person's `privacy.location` switch is off; nothing is stored then.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

router = APIRouter()


@router.post("/api/device/location")
async def device_location(lat: float = Body(...), lon: float = Body(...), accuracy: float | None = Body(None),
                          dev: str = Body("")) -> JSONResponse:
    from nucleo import where
    out = await asyncio.to_thread(where.report, lat, lon, accuracy, dev)   # the lookup is network I/O
    return JSONResponse(out, status_code=200 if out.get("ok") or out.get("reason") == "off" else 400)
