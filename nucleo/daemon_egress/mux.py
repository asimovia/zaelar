"""Many TCP streams over the ONE WebSocket his daemon dialled (V2-836) — the engine's end of the frames.

    engine → daemon   {"t":"open","id":7,"host":"example.com","port":443}
    daemon → engine   {"t":"ok","id":7}                 or  {"t":"close","id":7,"error":"private_address"}
    both ways         {"t":"data","id":7,"b64":"…"}
    both ways         {"t":"close","id":7}
    engine → daemon   {"t":"ping"} every `PING_S`       ← {"t":"pong"}

`Session` is transport-agnostic: it takes `send_text` / `recv_text` coroutines, so the FastAPI WebSocket in production
and a pair of queues in a test drive the same code. Back-pressure is per stream (`STREAM_QUEUE` frames) and blocks
the reader when a consumer stalls — head-of-line for the other streams, the price of a single socket; Chromium reads
fast enough that it does not show.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import itertools
import json
import time

PING_S = 25.0
OPEN_TIMEOUT_S = 20.0
CHUNK = 32 * 1024
STREAM_QUEUE = 256
HOUR_S = 3600.0


class StreamRefused(Exception):
    """His daemon would not open that stream (`code`: private_address, port_not_allowed, rate_limited, …), or the
    tunnel went away while it was being opened (`tunnel_closed`)."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class Stream:
    def __init__(self, session: "Session", sid: int, host: str):
        self._s, self.id, self.host = session, sid, host
        self._q: asyncio.Queue = asyncio.Queue(STREAM_QUEUE)
        self._eof = False
        self.closed = False

    async def read(self) -> bytes:
        """The next bytes from the destination; b"" once it (or the tunnel) closed."""
        if self._eof:
            return b""
        data = await self._q.get()
        if not data:
            self._eof = True
            return b""
        return data

    async def write(self, data: bytes) -> None:
        if self.closed:
            raise ConnectionError("stream closed")
        for i in range(0, len(data), CHUNK):
            await self._s._send({"t": "data", "id": self.id,
                                 "b64": base64.b64encode(data[i:i + CHUNK]).decode("ascii")})
        self._s._account(self.host, up=len(data))

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self._s._streams.pop(self.id, None)
        try:
            await self._s._send({"t": "close", "id": self.id})
        except Exception:   # noqa: BLE001 — the tunnel is gone; nothing left to tell
            pass

    def _feed(self, data: bytes) -> asyncio.Future | None:
        return self._q.put(data)

    def _end(self) -> None:
        self.closed = True
        try:
            self._q.put_nowait(b"")
        except asyncio.QueueFull:
            pass


class Session:
    def __init__(self, send_text, recv_text, *, close_transport=None, clock=time.time):
        self._send_text, self._recv_text, self._clock = send_text, recv_text, clock
        self._close_transport = close_transport
        self._ids = itertools.count(1)
        self._streams: dict[int, Stream] = {}
        self._pending: dict[int, asyncio.Future] = {}
        self._send_lock = asyncio.Lock()
        self._hosts: dict[str, float] = {}
        self.bytes_up = 0
        self.bytes_down = 0
        self.closed = False
        self.since = clock()

    # ── what the forwarder uses ──────────────────────────────────────────────────────────────────────────

    async def open(self, host: str, port: int, *, timeout: float = OPEN_TIMEOUT_S) -> Stream:
        if self.closed:
            raise StreamRefused("tunnel_closed")
        sid = next(self._ids)
        fut = asyncio.get_running_loop().create_future()
        self._pending[sid] = fut
        stream = Stream(self, sid, host)
        self._streams[sid] = stream
        try:
            await self._send({"t": "open", "id": sid, "host": host, "port": int(port)})
            await asyncio.wait_for(fut, timeout)
        except StreamRefused:
            self._streams.pop(sid, None)
            raise
        except (asyncio.TimeoutError, ConnectionError, RuntimeError):
            self._streams.pop(sid, None)
            raise StreamRefused("open_timeout") from None
        finally:
            self._pending.pop(sid, None)
        self._hosts[host] = self._clock()
        return stream

    def hosts_last_hour(self) -> int:
        now = self._clock()
        return sum(1 for t in self._hosts.values() if now - t < HOUR_S)

    # ── the socket ───────────────────────────────────────────────────────────────────────────────────────

    async def _send(self, frame: dict) -> None:
        if self.closed:
            raise ConnectionError("tunnel closed")
        async with self._send_lock:
            await self._send_text(json.dumps(frame, separators=(",", ":")))

    def _account(self, host: str, *, up: int = 0, down: int = 0) -> None:
        self.bytes_up += up
        self.bytes_down += down
        if host:
            self._hosts[host] = self._clock()

    async def run(self) -> None:
        """Read frames until the socket ends; then every stream sees EOF and every pending open is refused."""
        pinger = asyncio.create_task(self._ping())
        try:
            while True:
                raw = await self._recv_text()
                try:
                    frame = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                if isinstance(frame, dict):
                    await self._on_frame(frame)
        except Exception:   # noqa: BLE001 — the socket ended (closed, broken, cancelled): same ending
            pass
        finally:
            pinger.cancel()
            self._shutdown()

    async def _ping(self) -> None:
        try:
            while not self.closed:
                await asyncio.sleep(PING_S)
                await self._send({"t": "ping"})
        except Exception:   # noqa: BLE001 — the reader notices too
            return

    async def _on_frame(self, frame: dict) -> None:
        kind, sid = frame.get("t"), frame.get("id")
        if kind == "ok":
            fut = self._pending.get(sid)
            if fut is not None and not fut.done():
                fut.set_result(True)
        elif kind == "data":
            st = self._streams.get(sid)
            if st is None:
                return
            try:
                data = base64.b64decode(str(frame.get("b64") or ""), validate=True)
            except (binascii.Error, ValueError):
                return
            if data:
                self._account(st.host, down=len(data))
                await st._feed(data)
        elif kind == "close":
            fut = self._pending.get(sid)
            if fut is not None and not fut.done():
                fut.set_exception(StreamRefused(str(frame.get("error") or "refused")[:40]))
            st = self._streams.pop(sid, None)
            if st is not None:
                st._end()

    def _shutdown(self) -> None:
        self.closed = True
        for fut in list(self._pending.values()):
            if not fut.done():
                fut.set_exception(StreamRefused("tunnel_closed"))
        for st in list(self._streams.values()):
            st._end()
        self._streams.clear()

    async def close(self) -> None:
        """End the tunnel from this side: every stream sees EOF, and the socket itself is closed."""
        already = self.closed
        self._shutdown()
        if self._close_transport is not None and not already:
            try:
                await self._close_transport()
            except Exception:   # noqa: BLE001 — closing a socket that is already gone
                pass
