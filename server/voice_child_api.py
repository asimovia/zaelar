"""The body's face to the voice process (V2-891): three loopback routes, answered only with the spawn's token.

  POST /api/voice/child/events   the session's facts, in order, in batches (`voice/remote_session.handle_batch`)
  POST /api/voice/child/kickoff  the first-turn decision for a session the voice process just started
  POST /api/turn/stream          one voice turn, as NDJSON lines the voice process speaks as they arrive

None of them exists for a browser: a request that is not from this host, or that lacks the token the body handed
the voice process when it started it (`voice/child_process.py`), is refused before anything is read. A deployment
that embeds the voice (`ZAELAR_VOICE_EMBEDDED=1`) has no token, so every call is refused.
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

router = APIRouter()

_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def _allowed(request: Request) -> bool:
    from voice import child_process
    from voice.engine.pipeline import body_link
    want = child_process.token()
    host = getattr(request.client, "host", "") if request.client is not None else ""
    return bool(want) and host in _LOOPBACK and request.headers.get(body_link.HEADER, "") == want


def _deny() -> JSONResponse:
    return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)


@router.post("/api/voice/child/events")
async def child_events(request: Request):
    if not _allowed(request):
        return _deny()
    from voice import remote_session
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    n = remote_session.handle_batch(list(body.get("events") or []))
    return {"ok": True, "n": n}


@router.post("/api/voice/child/kickoff")
async def child_kickoff(request: Request):
    if not _allowed(request):
        return _deny()
    from voice import remote_session
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    return {"ok": True, **remote_session.kickoff(str(body.get("room") or ""))}


@router.post("/api/turn/stream")
async def turn_stream(request: Request):
    if not _allowed(request):
        return _deny()
    from voice import remote_session
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        payload = {}

    async def _lines():
        agen = remote_session.turn_lines(payload)
        try:
            async for line in agen:
                yield json.dumps(line, ensure_ascii=False) + "\n"
        except asyncio.CancelledError:          # the voice process closed the stream: a barge-in, a draft discarded
            raise
        finally:
            await agen.aclose()

    return StreamingResponse(_lines(), media_type="application/x-ndjson")
