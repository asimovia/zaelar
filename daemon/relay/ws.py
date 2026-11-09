"""A small WebSocket CLIENT on the standard library (RFC 6455), enough for the relay link.

WHY NOT A LIBRARY. The daemon's `requirements.txt` is empty on purpose (every dependency is weight in a onefile
installer and one more import that can fail on a stranger's machine). The relay link needs one outbound socket, text
frames, ping/pong and close — a few dozen lines over `socket` + `ssl`, with the certificate checked by the platform's
default context.

What it does: the opening handshake (with extra headers, e.g. `Authorization`), masked client frames, reassembly of
fragmented messages, automatic answers to control pings, and a bound on what it will read (`MAX_MESSAGE`). What it does
not: extensions, compression, subprotocols, a server side.
"""
from __future__ import annotations

import base64
import contextlib
import hashlib
import os
import socket
import ssl
import struct
import threading
from urllib.parse import urlsplit

_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
#: Largest message the daemon accepts from the relay. Commands are small JSON; anything bigger is not a command.
MAX_MESSAGE = 1 * 1024 * 1024

OP_CONT, OP_TEXT, OP_BINARY, OP_CLOSE, OP_PING, OP_PONG = 0x0, 0x1, 0x2, 0x8, 0x9, 0xA


class HandshakeError(Exception):
    """The relay answered the upgrade with something other than 101. `status` is its HTTP status (0 = no answer)."""

    def __init__(self, status: int, message: str = ""):
        super().__init__(message or f"websocket handshake refused: HTTP {status}")
        self.status = status


class Closed(Exception):
    """The connection is closed (by either side, or it broke)."""


class WebSocket:
    def __init__(self, sock: socket.socket):
        self._sock = sock
        self._send_lock = threading.Lock()
        self._buf = b""
        self._parts: list[bytes] = []
        self.closed = False
        #: The status code of the peer's close frame, when it sent one (the egress tunnel reads 4401 from it).
        self.close_code: int | None = None

    # ── reading ──────────────────────────────────────────────────────────────────────────────────────────

    def _fill(self, n: int) -> None:
        """Buffer at least `n` bytes WITHOUT consuming them, so a timeout mid-frame loses nothing: the next call
        resumes the same frame."""
        while len(self._buf) < n:
            try:
                chunk = self._sock.recv(max(65536, n - len(self._buf)))
            except socket.timeout:
                raise
            except OSError as e:
                raise Closed(str(e)) from None
            if not chunk:
                raise Closed("connection closed")
            self._buf += chunk

    def _read_frame(self) -> tuple[bool, int, bytes]:
        self._fill(2)
        b1, b2 = self._buf[0], self._buf[1]
        fin, opcode = bool(b1 & 0x80), b1 & 0x0F
        masked, length, off = bool(b2 & 0x80), b2 & 0x7F, 2
        if length == 126:
            self._fill(4)
            length, off = struct.unpack("!H", self._buf[2:4])[0], 4
        elif length == 127:
            self._fill(10)
            length, off = struct.unpack("!Q", self._buf[2:10])[0], 10
        if length > MAX_MESSAGE:
            self.close(1009)
            raise Closed("message too big")
        mask = b""
        if masked:
            self._fill(off + 4)
            mask, off = self._buf[off:off + 4], off + 4
        self._fill(off + length)
        payload, self._buf = self._buf[off:off + length], self._buf[off + length:]
        if mask:
            payload = bytes(c ^ mask[i % 4] for i, c in enumerate(payload))
        return fin, opcode, payload

    def recv(self) -> str:
        """The next TEXT message. Answers pings on its own; raises `Closed` on a close frame or a broken socket and
        `socket.timeout` when nothing (or not a whole frame) arrived within the socket's timeout — calling it again
        resumes where it stopped."""
        while True:
            fin, opcode, payload = self._read_frame()
            if opcode == OP_PING:
                self._send_frame(OP_PONG, payload[:125])
                continue
            if opcode == OP_PONG:
                continue
            if opcode == OP_CLOSE:
                if len(payload) >= 2:
                    self.close_code = struct.unpack("!H", payload[:2])[0]
                self.close()
                raise Closed("closed by the relay")
            if opcode in (OP_TEXT, OP_BINARY, OP_CONT):
                self._parts.append(payload)
                if sum(len(p) for p in self._parts) > MAX_MESSAGE:
                    self.close(1009)
                    raise Closed("message too big")
                if fin:
                    out, self._parts = b"".join(self._parts), []
                    return out.decode("utf-8", errors="replace")
                continue
            self.close(1002)
            raise Closed(f"unknown opcode {opcode}")

    # ── writing ──────────────────────────────────────────────────────────────────────────────────────────

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        header = bytearray([0x80 | opcode])
        n = len(payload)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header += struct.pack("!H", n)
        else:
            header.append(0x80 | 127)
            header += struct.pack("!Q", n)
        mask = os.urandom(4)
        header += mask
        # XOR in one pass over ints: fast enough for the 20 MB ceiling without numpy.
        if n:
            full = (mask * (n // 4 + 1))[:n]
            body = (int.from_bytes(payload, "big") ^ int.from_bytes(full, "big")).to_bytes(n, "big")
        else:
            body = b""
        with self._send_lock:
            if self.closed and opcode != OP_CLOSE:
                raise Closed("closed")
            try:
                self._sock.sendall(bytes(header) + body)
            except OSError as e:
                raise Closed(str(e)) from None

    def send(self, text: str) -> None:
        self._send_frame(OP_TEXT, text.encode("utf-8"))

    def close(self, code: int = 1000) -> None:
        if self.closed:
            return
        with contextlib.suppress(Exception):     # the peer may be gone already: closing is best effort
            self._send_frame(OP_CLOSE, struct.pack("!H", code))
        self.closed = True
        with contextlib.suppress(OSError):
            self._sock.shutdown(socket.SHUT_RDWR)   # wakes a reader blocked in recv() on another thread
        with contextlib.suppress(OSError):
            self._sock.close()

    def settimeout(self, seconds: float | None) -> None:
        self._sock.settimeout(seconds)


def connect(url: str, headers: dict | None = None, *, timeout: float = 15.0) -> WebSocket:
    """Open `ws://` or `wss://` `url` with `headers` on the upgrade request. Raises `HandshakeError` (with the HTTP
    status) when the relay refuses, `OSError` when it cannot be reached."""
    parts = urlsplit(url)
    secure = parts.scheme == "wss"
    host = parts.hostname or ""
    port = parts.port or (443 if secure else 80)
    path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    raw = socket.create_connection((host, port), timeout=timeout)
    try:
        sock: socket.socket = ssl.create_default_context().wrap_socket(raw, server_hostname=host) if secure else raw
        key = base64.b64encode(os.urandom(16)).decode()
        host_header = host if parts.port is None else f"{host}:{parts.port}"
        lines = [f"GET {path} HTTP/1.1", f"Host: {host_header}", "Upgrade: websocket", "Connection: Upgrade",
                 f"Sec-WebSocket-Key: {key}", "Sec-WebSocket-Version: 13"]
        for k, v in (headers or {}).items():
            if "\r" in f"{k}{v}" or "\n" in f"{k}{v}":
                raise ValueError("header with a line break")
            lines.append(f"{k}: {v}")
        sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("latin-1"))
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = sock.recv(4096)
            if not chunk:
                raise HandshakeError(0, "the relay closed the connection during the handshake")
            response += chunk
            if len(response) > 65536:
                raise HandshakeError(0, "handshake answer too long")
        head, _, rest = response.partition(b"\r\n\r\n")
        status_line, *header_lines = head.decode("latin-1").split("\r\n")
        try:
            status = int(status_line.split(" ", 2)[1])
        except (IndexError, ValueError):
            raise HandshakeError(0, "malformed handshake answer") from None
        if status != 101:
            raise HandshakeError(status)
        got = {h.split(":", 1)[0].strip().lower(): h.split(":", 1)[1].strip() for h in header_lines if ":" in h}
        expected = base64.b64encode(hashlib.sha1((key + _GUID).encode()).digest()).decode()
        if got.get("sec-websocket-accept") != expected:
            raise HandshakeError(101, "bad Sec-WebSocket-Accept")
        ws = WebSocket(sock)
        ws._buf = rest
        return ws
    except BaseException:
        with contextlib.suppress(OSError):
            raw.close()
        raise
