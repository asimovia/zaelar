"""The tunnel's own WebSocket: a SECOND outbound link, straight to the engine that offered it (V2-836).

The relay carries commands, not traffic: the bytes of a browsing session would cost the relay its bandwidth and CPU.
So the engine sends `egress.offer {token, url, expires_at}` over the relay, and this daemon dials `url` itself:

    connect  WSS <url>  with  Authorization: Bearer <token>
    engine → daemon   {"t":"open","id":7,"host":"example.com","port":443}
    daemon → engine   {"t":"ok","id":7}                 or  {"t":"close","id":7,"error":"private_address"}
    both ways         {"t":"data","id":7,"b64":"…"}     raw bytes of that stream, base64
    both ways         {"t":"close","id":7}              that stream is over
    engine → daemon   {"t":"ping"}  → {"t":"pong"}

WHEN IT DIALS. Only while a fresh offer exists: a dropped tunnel is redialled with a jittered backoff until the
offer's `expires_at`; the engine renews the offer before it expires, and an engine that stops renewing is an engine
the daemon stops calling. A token the engine refuses (close 4401, or a 401/403 on the upgrade) is dropped at once.

WHEN IT CLOSES. When the switch goes off — `stop()` from the switch itself, and the loop re-reads the switch every
tick in case the file changed under it — the socket and EVERY stream close together.
"""
from __future__ import annotations

import base64
import binascii
import contextlib
import ipaddress
import json
import queue
import random
import socket
import threading
import time
from urllib.parse import urlsplit

from .. import config
from ..fs.refusal import Refusal
from ..relay import ws
from ..security import egress_guard as guard
from . import connect as connect_mod, note
from .ledger import LEDGER

#: Seconds the tunnel may hear nothing (the engine pings every 25 s) before it is treated as gone.
SILENCE_S = 75.0
HANDSHAKE_TIMEOUT_S = 15.0
#: Streams one tunnel carries at once. A browser uses tens; a few hundred is a loop, not a person browsing.
MAX_STREAMS = 128
#: Bytes read from a destination per data frame (≈ 44 KB once base64'd into JSON — far under `ws.MAX_MESSAGE`).
CHUNK = 32 * 1024
#: Frames waiting to be written to ONE destination before that stream is given up as stalled.
WRITE_QUEUE = 64
WRITE_STALL_S = 30.0
#: The longest an offer may say it lives: an offer for next week is not an offer, it is a standing credential.
MAX_OFFER_S = 3600.0
BACKOFF_MIN_S = 1.0
BACKOFF_MAX_S = 30.0
#: Close code an engine sends when it does not know the token.
CLOSE_UNKNOWN_TOKEN = 4401
_TICK_S = 1.0
_TOKEN_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-")
_LOOPBACK = ("127.0.0.1", "localhost", "::1")


def _site(host: str) -> str:
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        return guard.domain_of(host)


def acceptable_url(url: str, relay_url: str) -> bool:
    """`wss://` on the SAME SITE as the relay this daemon is paired with (the engine and the relay are one service's
    two doors); `ws://` only between two loopback ends (a test). A command cannot send the token anywhere else."""
    u, r = urlsplit((url or "").strip()), urlsplit((relay_url or "").strip())
    host, rhost = (u.hostname or "").lower(), (r.hostname or "").lower()
    if not host or not rhost:
        return False
    if host in _LOOPBACK or rhost in _LOOPBACK:
        return host in _LOOPBACK and rhost in _LOOPBACK and u.scheme in ("ws", "wss")
    return u.scheme == "wss" and _site(host) == _site(rhost)


def _expiry(raw) -> float:
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        v = float(raw)
        return v / 1000.0 if v > 1e12 else v
    if isinstance(raw, str) and raw.strip():
        from datetime import datetime
        try:
            return datetime.fromisoformat(raw.strip().replace("Z", "+00:00")).timestamp()
        except ValueError as e:
            note("an offer's expiry is unreadable", e)
            return 0.0
    return 0.0


class _Stream:
    def __init__(self, sid, sock: socket.socket, host: str):
        self.id, self.sock, self.host = sid, sock, host
        self.outbox: queue.Queue = queue.Queue(WRITE_QUEUE)
        self.done = threading.Event()

    def shut(self) -> None:
        if self.done.is_set():
            return
        self.done.set()
        with contextlib.suppress(queue.Full):
            self.outbox.put_nowait(None)          # wakes the writer, which then sees `done`
        with contextlib.suppress(OSError):        # the destination may have gone already: closing is best effort
            self.sock.shutdown(socket.SHUT_RDWR)
        with contextlib.suppress(OSError):
            self.sock.close()


class Tunnel:
    def __init__(self, *, connect=ws.connect, opener=None, enabled=None, ledger=None, relay_url=None,
                 clock=time.time, rng: random.Random | None = None):
        self._connect = connect
        self._opener = opener or connect_mod.open_stream
        self._enabled = enabled or config.egress_enabled
        self._ledger = ledger or LEDGER
        self._relay_url = relay_url
        self._clock = clock
        self._rng = rng or random.Random()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._ws: ws.WebSocket | None = None
        self._offer: dict | None = None
        self._streams: dict = {}
        self.status: dict = {"state": "idle", "since": 0.0, "last_error": ""}

    # ── the offer, from the relay ────────────────────────────────────────────────────────────────────────

    def _relay(self) -> str:
        if self._relay_url is not None:
            return self._relay_url
        from ..relay import config as relay_config
        return relay_config.url()

    def offer(self, args: dict) -> dict:
        """Accept an `egress.offer`. Raises `Refusal` when the switch is off or the offer is malformed; otherwise
        remembers it (a renewal just replaces the token) and makes sure the tunnel is dialling."""
        if not self._enabled():
            raise Refusal("egress_disabled", "The person has not switched the tunnel on, on this computer.")
        token, url = args.get("token"), args.get("url")
        if not isinstance(token, str) or not (16 <= len(token) <= 512) or not set(token) <= _TOKEN_CHARS:
            raise Refusal("bad_offer", "The offer carries no usable token.")
        if not isinstance(url, str) or not acceptable_url(url, self._relay()):
            raise Refusal("bad_offer", "The offer names a tunnel address this daemon does not dial.")
        expires = _expiry(args.get("expires_at"))
        now = self._clock()
        if not (now < expires <= now + MAX_OFFER_S):
            raise Refusal("bad_offer", "The offer is expired or lives too long.")
        with self._lock:
            self._offer = {"token": token, "url": url, "expires_at": expires}
        self.start()
        return {"ok": True, "accepted": True, "connected": self.connected()}

    def _fresh(self) -> dict | None:
        with self._lock:
            o = self._offer
        return o if o and self._clock() < o["expires_at"] else None

    # ── life ─────────────────────────────────────────────────────────────────────────────────────────────

    def start(self) -> None:
        old = self._thread
        if old is not None and old.is_alive() and self._stop.is_set():
            old.join(2 * _TICK_S)               # a loop that was just told to stop exits within a tick
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self.run, name="daemon-egress", daemon=True)
            self._thread.start()

    def stop(self, reason: str = "local") -> None:
        """Close the tunnel and every stream on it, NOW, and forget the offer."""
        self._stop.set()
        with self._lock:
            self._offer = None
            sock, self._ws = self._ws, None
        if sock is not None:
            sock.close()
        self._close_all()
        self._set("stopped" if reason != "disabled" else "off", last_error="")
        self._ledger.flush()

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    def connected(self) -> bool:
        return self.status.get("state") == "connected"

    def streams(self) -> int:
        with self._lock:
            return len(self._streams)

    def _set(self, state: str, **extra) -> None:
        self.status.update(state=state, since=self._clock(), **extra)

    def _backoff(self, attempt: int) -> float:
        d = min(BACKOFF_MAX_S, BACKOFF_MIN_S * (2 ** max(0, attempt)))
        return max(BACKOFF_MIN_S / 2, d * (0.5 + 0.5 * self._rng.random()))

    def run(self) -> None:
        attempt = 0
        while not self._stop.is_set():
            if not self._enabled():
                self.stop("disabled")
                return
            offer = self._fresh()
            if offer is None:
                self._set("expired" if self._offer else "idle")
                return
            outcome = self._session(offer)
            if outcome == "refused":
                with self._lock:
                    if self._offer is offer:
                        self._offer = None      # a token the engine does not know is never retried
                self._set("refused", last_error="token refused")
                if self._fresh() is None:
                    return
                continue                         # a NEWER offer arrived meanwhile: try that one
            if self._stop.is_set():
                break
            attempt = 0 if outcome == "worked" else attempt + 1
            self._set("waiting", last_error=self.status.get("last_error", ""))
            self._stop.wait(self._backoff(attempt))

    def _session(self, offer: dict) -> str:
        """One connection. Returns `refused` (the token was not accepted), `worked` (it carried, then ended) or
        `failed` (it never came up)."""
        self._set("connecting")
        try:
            sock = self._connect(offer["url"], {"Authorization": f"Bearer {offer['token']}"},
                                 timeout=HANDSHAKE_TIMEOUT_S)
        except ws.HandshakeError as e:
            self.status["last_error"] = f"handshake {e.status}"
            return "refused" if e.status in (401, 403) else "failed"
        except Exception as e:  # noqa: BLE001 — unreachable, DNS, TLS: the backoff decides when to try again
            self.status["last_error"] = type(e).__name__
            return "failed"
        with self._lock:
            self._ws = sock
        self._set("connected", last_error="")
        heard_anything = False
        try:
            sock.settimeout(_TICK_S)
            quiet = 0.0
            while not self._stop.is_set():
                if not self._enabled():
                    self.stop("disabled")
                    break
                try:
                    raw = sock.recv()
                except socket.timeout:
                    quiet += _TICK_S
                    if quiet >= SILENCE_S:
                        self.status["last_error"] = "silent engine"
                        break
                    continue
                quiet, heard_anything = 0.0, True
                try:
                    frame = json.loads(raw)
                except ValueError as e:
                    note("a tunnel frame that is not JSON", e)
                    continue
                if isinstance(frame, dict):
                    self._on_frame(sock, frame)
        except ws.Closed as e:
            self.status["last_error"] = str(e)[:120]
            if getattr(sock, "close_code", None) == CLOSE_UNKNOWN_TOKEN:
                return "refused"
        except Exception as e:  # noqa: BLE001
            self.status["last_error"] = type(e).__name__
        finally:
            with self._lock:
                if self._ws is sock:
                    self._ws = None
            sock.close()
            self._close_all()
            if self.connected():
                self._set("disconnected")
        return "worked" if heard_anything else "failed"

    # ── frames ───────────────────────────────────────────────────────────────────────────────────────────

    def _send(self, sock, frame: dict) -> bool:
        try:
            sock.send(json.dumps(frame, separators=(",", ":")))
            return True
        except Exception as e:   # noqa: BLE001 — the reader notices the broken socket too
            note("frame not sent", e)
            return False

    def _on_frame(self, sock, frame: dict) -> None:
        kind, sid = frame.get("t"), frame.get("id")
        if kind == "ping":
            self._send(sock, {"t": "pong"})
        elif kind == "open":
            threading.Thread(target=self._open, args=(sock, frame), name="egress-open", daemon=True).start()
        elif kind == "data":
            with self._lock:
                st = self._streams.get(sid)
            if st is None:
                return
            try:
                data = base64.b64decode(str(frame.get("b64") or ""), validate=True)
            except (binascii.Error, ValueError):
                self._end(sock, st, notify=True)
                return
            try:
                st.outbox.put(data, timeout=WRITE_STALL_S)
            except queue.Full:
                self._end(sock, st, notify=True)
        elif kind == "close":
            with self._lock:
                st = self._streams.get(sid)
            if st is not None:
                try:
                    st.outbox.put_nowait(None)    # write what is queued, then close
                except queue.Full:
                    self._end(sock, st, notify=False)

    def _open(self, sock, frame: dict) -> None:
        sid, host = frame.get("id"), str(frame.get("host") or "")[:253]
        with self._lock:
            full = len(self._streams) >= MAX_STREAMS
            dup = sid in self._streams
        if full or dup or sid is None:
            self._send(sock, {"t": "close", "id": sid, "error": "busy" if full else "bad_stream"})
            return
        try:
            conn, clean = self._opener(host, frame.get("port"))
        except guard.Refused as r:
            self._ledger.refused(host, r.code)
            self._send(sock, {"t": "close", "id": sid, "error": r.code})
            return
        except Exception as e:  # noqa: BLE001 — a bug here refuses ONE stream, never the tunnel
            note("stream not opened", e)
            self._send(sock, {"t": "close", "id": sid, "error": "connect_failed"})
            return
        st = _Stream(sid, conn, clean)
        with self._lock:
            if self._ws is not sock:            # the tunnel went away while we connected
                st.shut()
                return
            self._streams[sid] = st
        self._ledger.opened(clean)
        if not self._send(sock, {"t": "ok", "id": sid}):
            self._end(sock, st, notify=False)
            return
        threading.Thread(target=self._pump_out, args=(sock, st), name="egress-down", daemon=True).start()
        threading.Thread(target=self._pump_in, args=(sock, st), name="egress-up", daemon=True).start()

    def _pump_in(self, sock, st: _Stream) -> None:
        """Engine → destination: drain the stream's outbox into its socket. `None` is the engine's close."""
        while not st.done.is_set():
            data = st.outbox.get()                # `None`: the engine closed it, or `shut()` woke us
            if data is None:
                self._end(sock, st, notify=False)
                return
            try:
                st.sock.sendall(data)
                self._ledger.bytes(st.host, up=len(data))
            except OSError:
                self._end(sock, st, notify=True)
                return

    def _pump_out(self, sock, st: _Stream) -> None:
        """Destination → engine: read, frame, send. EOF or an error ends the stream on both sides."""
        while not st.done.is_set():
            try:
                data = st.sock.recv(CHUNK)
            except OSError:
                break
            if not data:
                break
            self._ledger.bytes(st.host, down=len(data))
            if not self._send(sock, {"t": "data", "id": st.id, "b64": base64.b64encode(data).decode("ascii")}):
                break
        self._end(sock, st, notify=True)

    def _end(self, sock, st: _Stream, *, notify: bool) -> None:
        with self._lock:
            mine = self._streams.pop(st.id, None) is st
        if not mine:
            return
        st.shut()
        if notify:
            self._send(sock, {"t": "close", "id": st.id})

    def _close_all(self) -> None:
        with self._lock:
            streams, self._streams = list(self._streams.values()), {}
        for st in streams:
            st.shut()

    def view(self) -> dict:
        """What the local screen and the tray read."""
        return {"state": self.status.get("state", "idle"), "connected": self.connected(), "streams": self.streams(),
                "hosts_last_hour": self._ledger.hosts_last_hour()}


TUNNEL = Tunnel()


def switch(enabled: bool, *, consent: bool = False) -> dict:
    """The ONE place the switch is flipped (the loopback route and the tray both call it). ON needs consent; OFF closes
    the tunnel and every stream now. Either way the relay link re-says hello, so its capability list (`egress` or
    not) is what the engine sees from now on."""
    section = config.save_egress(enabled, consent=consent)
    if not section.get("enabled"):
        TUNNEL.stop("disabled")
    try:
        from ..relay import client
        client.CLIENT.refresh_caps()
    except Exception as e:  # noqa: BLE001 — the relay is additive
        note("relay not refreshed", e)
    return section
