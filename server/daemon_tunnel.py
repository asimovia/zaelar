"""server/daemon_tunnel.py — the WebSocket his daemon dials to carry this engine's browsing (V2-836).

`WS /daemon/tunnel`, `Authorization: Bearer <token>`. The token is one THIS instance minted and offered over the relay
(`nucleo/daemon_egress/tokens.py`); anything else is accepted only to be closed with 4401 — the code the daemon reads
as «this token is not known here, do not retry it». On a deployment where several instances share one public
hostname, the admission gate (`server/ingress.py`) has already handed the socket to the instance the token's prefix
names, so the check below is the instance's own: a forged prefix only ever reaches an instance that refuses it.

No session cookie is involved, and none could be: the caller is his daemon, not his browser.
"""
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

CLOSE_UNKNOWN_TOKEN = 4401


def bearer(value: str | None) -> str:
    v = (value or "").strip()
    return v[7:].strip() if v[:7].lower() == "bearer " else ""


@router.websocket("/daemon/tunnel")
async def daemon_tunnel(websocket: WebSocket):
    from nucleo.daemon_egress import link, tokens
    token = bearer(websocket.headers.get("authorization"))
    await websocket.accept()
    if not tokens.verify(token):
        await websocket.close(code=CLOSE_UNKNOWN_TOKEN)
        return

    async def recv() -> str:
        msg = await websocket.receive()
        if msg.get("type") == "websocket.disconnect":
            raise WebSocketDisconnect(msg.get("code") or 1000)
        return msg.get("text") or (msg.get("bytes") or b"").decode("utf-8", "replace")

    async def close() -> None:
        await websocket.close(code=1000)

    await link.attach(websocket.send_text, recv, close)
