"""The body's face to the voice process (V2-891): four loopback routes, answered only with the spawn's token.

  POST /api/voice/child/events   the session's facts, in order, in batches (`voice/remote_session.handle_batch`)
  POST /api/voice/child/kickoff  the first-turn decision for a session the voice process just started
  POST /api/voice/child/conv     before a session is built: does it go by the conversation manager?
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


def _allowed(request: Request) -> bool:
    from server import api_guard
    from voice import child_process
    want = child_process.token()
    host = getattr(request.client, "host", "") if request.client is not None else ""
    return bool(want) and api_guard._is_loopback(host) and request.headers.get(child_process.HEADER, "") == want


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
    from server import voice_child_once
    n = remote_session.handle_batch(voice_child_once.once(body.get("events")))
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
    from server import voice_child_once
    return {"ok": True, **remote_session.kickoff(str(body.get("room") or ""), voice_child_once.once(body.get("events")))}


@router.post("/api/voice/child/conv")
async def child_conv(request: Request):
    """Before the voice process builds a session: does it go by the conversation manager?"""
    if not _allowed(request):
        return _deny()
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    from nucleo.conversation_host import voice_session
    return {"ok": True, **await asyncio.to_thread(voice_session.ask, body.get("flag"))}


@router.post("/api/turn/stream")
async def turn_stream(request: Request):
    if not _allowed(request):
        return _deny()
    from voice import remote_session
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        payload = {}
    if isinstance(payload, dict) and payload.get("events"):
        from server import voice_child_once
        payload["events"] = voice_child_once.once(payload["events"])   # a fact asked twice is replayed once

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
