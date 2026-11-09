"""The OUTBOUND link: this daemon dials the relay and a remote engine's commands arrive over that one socket.

Nothing on the internet can reach his loopback, so the daemon initiates. The life of the link:

    connect  WSS <relay>/daemon/relay  with  Authorization: Bearer <credential>
    send     {"t":"hello","v":1,"caps":[…],"version":…,"platform":…}           (the first frame, always)
    wait     {"t":"welcome",…}                                                 → connected
    loop     command → result (each on its own worker) · ping → pong · bye → see below
    events   {"t":"event","name":"browser.state","data":…} when his window closes or he signs in

`bye` decides what happens next: `revoked` → the credential is FORGOTTEN and the link stops (a revoked daemon never
retries with a dead credential); `replaced` → another connection of the same account took over, stop without
forgetting; `shutdown` (or anything else) → reconnect. A broken socket, a refused handshake or a relay that sends
nothing for `SILENCE_S` → reconnect after a jittered exponential backoff from `BACKOFF_MIN_S` to `BACKOFF_MAX_S`.

No credential, no link: the daemon is exactly the loopback daemon of P0-P2 until it is paired (`daemon.relay.pair`).
"""
from __future__ import annotations

import json
import random
import socket
import sys
import threading
import time

from .. import VERSION, audit
from . import config, note, ws

BACKOFF_MIN_S = 1.0
BACKOFF_MAX_S = 60.0
#: The relay pings every 25 s and closes a link that has not answered in 60 s; a relay silent for longer than this is
#: gone even if the socket has not noticed.
SILENCE_S = 75.0
WELCOME_TIMEOUT_S = 15.0
#: Concurrent commands one link runs at once (the relay limits the account's rate; this bounds the machine).
MAX_INFLIGHT = 4
#: How often the open sign-in window is looked at to notice it closed or he signed in (only while one is open).
WINDOW_POLL_S = 2.0
#: How long one read waits before the loop looks at `stop()` again.
_TICK_S = 1.0


def backoff(attempt: int, rng: random.Random | None = None) -> float:
    """Seconds before reconnect attempt `attempt` (0-based): 1, 2, 4 … capped at 60, each jittered into [½d, d]."""
    d = min(BACKOFF_MAX_S, BACKOFF_MIN_S * (2 ** max(0, attempt)))
    r = (rng or random).random()
    return max(BACKOFF_MIN_S / 2, d * (0.5 + 0.5 * r))


def platform_name() -> str:
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("win"):
        return "windows"
    return "linux"


def _caps() -> list[str]:
    from ..http import routes
    return routes.capabilities()


class RelayClient:
    def __init__(self, *, connect=ws.connect, sleep=None, rng: random.Random | None = None):
        self._connect = connect
        self._stop = threading.Event()
        self._sleep = sleep or self._stop.wait
        self._rng = rng
        self._thread: threading.Thread | None = None
        self._ws: ws.WebSocket | None = None
        self._slots = threading.BoundedSemaphore(MAX_INFLIGHT)
        self.status: dict = {"state": "idle", "since": 0.0, "account": "", "last_error": "", "attempt": 0}
        self.stopped_by: str = ""
        self._window_thread: threading.Thread | None = None

    # ── public surface ───────────────────────────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Start the link in the background when this daemon is paired. Returns whether it is running."""
        if self._thread is not None and self._thread.is_alive():
            return True
        if not config.paired():
            return False
        self._stop.clear()
        self.stopped_by = ""
        self._thread = threading.Thread(target=self.run, name="daemon-relay", daemon=True)
        self._thread.start()
        return True

    def stop(self, reason: str = "local") -> None:
        self.stopped_by = self.stopped_by or reason
        self._stop.set()
        sock = self._ws
        if sock is not None:
            sock.close()

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    def refresh_caps(self) -> None:
        """The capability list changed here (the tunnel switch): drop the live link so the loop redials at once and
        says `hello` again with the new list. Nothing happens when there is no link."""
        sock = self._ws
        if sock is not None and self.connected():
            sock.close()

    def connected(self) -> bool:
        return self.status.get("state") == "connected"

    def send_event(self, name: str, data: dict) -> bool:
        """Push a spontaneous event to the relay. False when there is no live link (events are not queued)."""
        sock = self._ws
        if sock is None or not self.connected():
            return False
        try:
            sock.send(json.dumps({"t": "event", "name": name, "data": data}))
            return True
        except Exception as e:   # noqa: BLE001 — the reader will notice the broken socket and reconnect
            note("event not sent", e)
            return False

    # ── the loop ─────────────────────────────────────────────────────────────────────────────────────────

    def _set(self, state: str, **extra) -> None:
        self.status.update(state=state, since=time.time(), **extra)

    def run(self) -> None:
        attempt = 0
        while not self._stop.is_set():
            cfg = config.load()
            if not (cfg.get("url") and cfg.get("credential")):
                self._set("unpaired")
                return
            outcome = self._session(cfg)
            if outcome in ("revoked", "replaced"):
                self.stopped_by = outcome
                self._set(outcome)
                return
            if self._stop.is_set():
                break
            if outcome == "welcomed":
                attempt = 0            # a link that WORKED and then dropped starts the backoff over
            delay = backoff(attempt, self._rng)
            attempt += 1
            self.status["attempt"] = attempt
            self._set("waiting", last_error=self.status.get("last_error", ""))
            self._sleep(delay)
        self._set("stopped")

    def _session(self, cfg: dict) -> str:
        """One connection, start to end. Returns why it ended: `revoked` · `replaced` · `welcomed` (it worked, then
        ended) · `failed` (never got a welcome)."""
        self._set("connecting")
        try:
            sock = self._connect(config.ws_url(cfg["url"]), {"Authorization": f"Bearer {cfg['credential']}"},
                                 timeout=WELCOME_TIMEOUT_S)
        except ws.HandshakeError as e:
            self.status["last_error"] = f"handshake {e.status}"
            if e.status in (401, 403):
                audit.record("relay.connect", caller="relay", outcome="refused", reason=f"http_{e.status}")
            return "failed"
        except Exception as e:  # noqa: BLE001 — unreachable, DNS, TLS: try again later
            self.status["last_error"] = type(e).__name__
            return "failed"
        self._ws = sock
        welcomed = False
        try:
            sock.send(json.dumps({"t": "hello", "v": 1, "caps": _caps(), "version": VERSION,
                                  "platform": platform_name()}))
            # Short reads, so `stop()` is honoured within `_TICK_S` whatever the platform does with a socket closed
            # under a blocked reader; silence is counted across them against the window that applies now.
            sock.settimeout(_TICK_S)
            quiet, limit = 0.0, WELCOME_TIMEOUT_S
            while not self._stop.is_set():
                try:
                    raw = sock.recv()
                except socket.timeout:
                    quiet += _TICK_S
                    if quiet >= limit:
                        self.status["last_error"] = "silent relay"
                        break
                    continue
                quiet = 0.0
                try:
                    frame = json.loads(raw)
                except ValueError as e:
                    note("a frame that is not JSON", e)
                    continue
                if not isinstance(frame, dict):
                    continue
                kind = frame.get("t")
                if kind == "welcome":
                    welcomed = True
                    self._set("connected", account=str(frame.get("account") or "")[:64], last_error="")
                    audit.record("relay.connect", caller="relay", outcome="ok")
                    limit = SILENCE_S
                    self._watch_window()
                elif kind == "ping":
                    sock.send(json.dumps({"t": "pong"}))
                elif kind == "command" and welcomed:
                    self._run_command(sock, frame)
                elif kind == "bye":
                    reason = str(frame.get("reason") or "")
                    audit.record("relay.bye", caller="relay", outcome="ok", reason=reason[:32] or None)
                    if reason == "revoked":
                        config.forget()
                        return "revoked"
                    if reason == "replaced":
                        return "replaced"
                    break
        except ws.Closed as e:
            self.status["last_error"] = str(e)[:120]
        except Exception as e:  # noqa: BLE001
            self.status["last_error"] = type(e).__name__
        finally:
            self._ws = None
            sock.close()
            if self.connected():
                self._set("disconnected")
        return "welcomed" if welcomed else "failed"

    def _run_command(self, sock, frame: dict) -> None:
        from . import dispatch
        if not self._slots.acquire(blocking=False):
            cid = str(frame.get("id") or "")
            sock.send(json.dumps({"t": "result", "id": cid, "ok": False,
                                  "error": {"code": "busy", "message": "Too many operations at once."}}))
            return

        def work():
            try:
                result = dispatch.handle(frame)
                try:
                    sock.send(json.dumps(result, ensure_ascii=False))
                except Exception as e:   # noqa: BLE001 — the link dropped; the relay times the command out
                    note("result not sent", e)
                if frame.get("op") in ("browser.open", "browser.close"):
                    self._watch_window()
            finally:
                self._slots.release()
        threading.Thread(target=work, name="relay-command", daemon=True).start()

    # ── his window: tell the relay when it closes or he signs in ────────────────────────────────────────

    def _watch_window(self) -> None:
        """Poll the sign-in window ONLY while one is open; emit `browser.state` when `open` or `signed_in` flips."""
        if self._window_thread is not None and self._window_thread.is_alive():
            return

        def loop():
            from . import dispatch
            seen = {"open": False, "signed_in": False}
            while not self._stop.is_set() and self.connected():
                if not getattr(dispatch._windows(), "_current", None) and not seen["open"]:
                    return
                try:
                    state = dispatch._browser_state({})
                except Exception as e:   # noqa: BLE001 — a browser that cannot answer has nothing to report
                    note("window state unreadable", e)
                    return
                now = {"open": bool(state.get("open")), "signed_in": bool(state.get("signed_in"))}
                if now != seen:
                    self.send_event("browser.state", {k: state.get(k) for k in
                                                      ("open", "signed_in", "url", "new_cookies") if k in state})
                    seen = now
                if not now["open"]:
                    return
                self._stop.wait(WINDOW_POLL_S)
        self._window_thread = threading.Thread(target=loop, name="relay-window", daemon=True)
        self._window_thread.start()


CLIENT = RelayClient()


def start_if_paired() -> bool:
    """Called when the daemon starts serving: dial the relay if this daemon has been paired."""
    try:
        return CLIENT.start()
    except Exception as e:   # noqa: BLE001 — the relay is additive; loopback serving never depends on it
        note("link not started", e)
        return False


def stop() -> None:
    CLIENT.stop("shutdown")
