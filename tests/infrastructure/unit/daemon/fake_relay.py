"""An in-process relay for the daemon's outbound link: a real WebSocket server on an ephemeral loopback port.

It speaks the daemon side of the relay contract — reads `hello`, answers `welcome`, can send `ping`, `command` and
`bye`, and collects what the daemon sends back. `on_connect(conn)` decides each connection's script; `conn.command`
sends one command and waits for its result, which is how an engine-side test reaches the daemon "through the relay".
"""
from __future__ import annotations

import itertools
import json
import queue
import threading

from websockets.sync.server import serve


class Conn:
    _ids = itertools.count(1)

    def __init__(self, ws):
        self.ws = ws
        self.headers = {k.lower(): v for k, v in ws.request.headers.raw_items()}
        self.hello: dict = {}
        self.inbox: queue.Queue = queue.Queue()
        self.results: dict = {}
        self.events: list = []
        self._cv = threading.Condition()
        self.closed = threading.Event()

    def send(self, frame: dict) -> None:
        self.ws.send(json.dumps(frame))

    def pump(self) -> None:
        """Read until the daemon closes: results land in `results`, events in `events`, the rest in `inbox`."""
        try:
            for raw in self.ws:
                frame = json.loads(raw)
                if frame.get("t") == "result":
                    with self._cv:
                        self.results[frame.get("id")] = frame
                        self._cv.notify_all()
                elif frame.get("t") == "event":
                    self.events.append(frame)
                else:
                    self.inbox.put(frame)
        except Exception:   # noqa: BLE001 — the daemon went away
            pass
        finally:
            self.closed.set()

    def command(self, op: str, args: dict | None = None, *, deadline_ms: int = 30_000, wait: float = 20.0) -> dict:
        cid = f"c{next(self._ids)}"
        self.send({"t": "command", "id": cid, "op": op, "args": args or {}, "deadline_ms": deadline_ms})
        with self._cv:
            self._cv.wait_for(lambda: cid in self.results, timeout=wait)
            return self.results.get(cid) or {}


class FakeRelay:
    def __init__(self, on_connect=None, *, status: int = 101):
        self.on_connect = on_connect
        self.conns: list[Conn] = []
        self.connected = threading.Event()
        self._status = status
        self._server = serve(self._handler, "127.0.0.1", 0, process_request=self._process)
        self.port = self._server.socket.getsockname()[1]
        self.url = f"http://127.0.0.1:{self.port}"
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def _process(self, connection, request):
        if self._status != 101:
            return connection.respond(self._status, "refused\n")
        return None

    def _handler(self, ws):
        conn = Conn(ws)
        self.conns.append(conn)
        conn.hello = json.loads(ws.recv(timeout=10))
        conn.send({"t": "welcome", "account": "acct-opaque", "server_time": "2026-11-09T00:00:00Z"})
        self.connected.set()
        reader = threading.Thread(target=conn.pump, daemon=True)
        reader.start()
        if self.on_connect:
            self.on_connect(conn)
        conn.closed.wait(30)

    def close(self) -> None:
        self._server.shutdown()
