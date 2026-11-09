"""The engine's local proxy: `127.0.0.1:<ephemeral>`, the address Chromium's `--proxy-server` and httpx's `proxy=`
point at while his tunnel is up (V2-836).

Two request shapes, both reduced to a byte stream to `host:port`:

  · `CONNECT host:port HTTP/1.1` — every https page. Answered `200 Connection established` once his daemon opened the
    stream; from then on the bytes are the browser's TLS, which this process never reads.
  · `GET http://host/path HTTP/1.1` (absolute form) — plain http. The request line is rewritten to origin form, the
    `Proxy-*` headers are dropped, and the rest is sent through the same kind of stream.

WHERE A STREAM GOES: through his tunnel while one is up; DIRECTLY (exactly what the engine did before) when none is
— a tunnel that dropped must not take the browser down with it. A stream his daemon REFUSES (a private address, a
port that is not the web's, his per-site limit) is answered `502` and is NOT retried directly: half a page from his
connection and half from a datacenter is the pattern anti-bot systems flag, and a refusal is his machine's answer.

Bound to loopback only; nothing off this machine can use it.
"""
from __future__ import annotations

import asyncio
from urllib.parse import urlsplit

from loguru import logger

from .mux import StreamRefused

HEAD_LIMIT = 64 * 1024
HEAD_TIMEOUT_S = 30.0
CHUNK = 32 * 1024
_DROP = ("proxy-connection", "proxy-authorization", "proxy-authenticate")


class _Direct:
    """A plain TCP connection with the same three calls a tunnel `Stream` has."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self._r, self._w = reader, writer

    async def read(self) -> bytes:
        return await self._r.read(CHUNK)

    async def write(self, data: bytes) -> None:
        self._w.write(data)
        await self._w.drain()

    async def close(self) -> None:
        try:
            self._w.close()
        except Exception:   # noqa: BLE001
            pass


def parse_target(line: str) -> tuple[str, str, int, str, str]:
    """`(method, host, port, origin_form_path, version)` from a proxy request line. Raises ValueError."""
    parts = line.strip().split(" ")
    if len(parts) != 3:
        raise ValueError("request line")
    method, target, version = parts
    if method.upper() == "CONNECT":
        host, _, port = target.rpartition(":")
        host = host.strip("[]")
        if not host or not port.isdigit():
            raise ValueError("connect target")
        return "CONNECT", host, int(port), "", version
    u = urlsplit(target)
    if u.scheme != "http" or not u.hostname:
        raise ValueError("absolute-form http only")
    path = (u.path or "/") + (f"?{u.query}" if u.query else "")
    return method.upper(), u.hostname, u.port or 80, path, version


class Forwarder:
    """`session_fn()` → the live tunnel `Session` or None. `direct(host, port)` → a `_Direct` (injectable for tests)."""

    def __init__(self, session_fn, *, direct=None):
        self._session_fn = session_fn
        self._direct = direct or self._open_direct
        self._server: asyncio.base_events.Server | None = None
        self.port = 0
        self.streams_tunnel = 0
        self.streams_direct = 0

    @staticmethod
    async def _open_direct(host: str, port: int) -> _Direct:
        r, w = await asyncio.open_connection(host, port)
        return _Direct(r, w)

    async def start(self) -> int:
        if self._server is None:
            self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0, limit=HEAD_LIMIT)
            self.port = self._server.sockets[0].getsockname()[1]
        return self.port

    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}" if self.port else ""

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            try:
                await self._server.wait_closed()
            except Exception:   # noqa: BLE001
                pass
            self._server = None

    async def _route(self, host: str, port: int):
        session = self._session_fn()
        if session is not None and not session.closed:
            stream = await session.open(host, port)
            self.streams_tunnel += 1
            return stream
        self.streams_direct += 1
        return await self._direct(host, port)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        upstream = None
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), HEAD_TIMEOUT_S)
            first, _, rest = head.decode("latin-1").partition("\r\n")
            method, host, port, path, version = parse_target(first)
            try:
                upstream = await self._route(host, port)
            except StreamRefused as r:
                writer.write(f"HTTP/1.1 502 Bad Gateway\r\nX-Zaelar-Egress: {r.code}\r\n"
                             "Content-Length: 0\r\nConnection: close\r\n\r\n".encode("latin-1"))
                await writer.drain()
                return
            except OSError:
                writer.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                await writer.drain()
                return
            if method == "CONNECT":
                writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
                await writer.drain()
            else:
                kept = [ln for ln in rest.split("\r\n") if ln and ln.split(":", 1)[0].strip().lower() not in _DROP]
                out = f"{method} {path} {version}\r\n" + "".join(f"{ln}\r\n" for ln in kept) + "\r\n"
                await upstream.write(out.encode("latin-1"))
            await self._pump(reader, writer, upstream)
        except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, asyncio.TimeoutError, ValueError):
            try:
                writer.write(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                await writer.drain()
            except Exception:   # noqa: BLE001
                pass
        except Exception as e:  # noqa: BLE001 — one stream fails alone
            logger.debug(f"daemon_egress: stream ended ({type(e).__name__})")
        finally:
            if upstream is not None:
                await upstream.close()
            try:
                writer.close()
            except Exception:   # noqa: BLE001
                pass

    @staticmethod
    async def _pump(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, upstream) -> None:
        async def up():
            while True:
                data = await reader.read(CHUNK)
                if not data:
                    return
                await upstream.write(data)

        async def down():
            while True:
                data = await upstream.read()
                if not data:
                    return
                writer.write(data)
                await writer.drain()

        tasks = [asyncio.create_task(up()), asyncio.create_task(down())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
