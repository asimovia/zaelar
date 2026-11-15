"""A connected WhatsApp bridge that sends nothing: the routing bench's test double for the messaging channel.

The engine talks to WhatsApp only through the bridge's loopback HTTP API (`connectors/whatsapp/client.py`), and a
bridge already answering `/health` on `WA_BRIDGE_PORT` is reused, never spawned (`bridge_proc._already_up`). So a
sandbox pointed at this server on a free port reads WhatsApp as connected everywhere it reads it, while every
`POST /send` is recorded here and goes nowhere. About a second after an accepted send, the double queues the
outgoing echo the phone would produce (`direction: out` on `GET /messages`), the way the real bridge does in
observe mode.

Guards: refuses the real bridge's default port, and `assert_isolated` checks the sandbox env before the first order.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

REAL_BRIDGE_PORT = 3111
ECHO_DELAY_S = 1.0
_BRIDGE_JS = Path(__file__).resolve().parents[4] / "connectors" / "whatsapp" / "bridge" / "bridge.js"


def _script_hash() -> str:
    """The hash the real bridge reports, so the engine does not take the double for a stale bridge to retire."""
    try:
        return hashlib.sha256(_BRIDGE_JS.read_bytes()).hexdigest()[:16]
    except OSError:
        return ""


class Double:
    def __init__(self, port: int, contacts: list[dict] | None = None):
        if int(port) == REAL_BRIDGE_PORT:
            raise RuntimeError("the double never listens on the real bridge's port")
        self.port = int(port)
        self.calls: list[dict] = []        # every request, in order
        self.sent: list[dict] = []         # accepted sends
        self._queue: list[dict] = []
        self._lock = threading.Lock()
        self._contacts = contacts or []
        self._server = ThreadingHTTPServer(("127.0.0.1", self.port), self._handler())
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self) -> "Double":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def sends_since(self, n: int) -> list[dict]:
        with self._lock:
            return list(self.sent[n:])

    def _echo_later(self, chat_id: str, text: str, mid: str) -> None:
        def push():
            time.sleep(ECHO_DELAY_S)
            ev = {"messageId": mid, "chatId": chat_id, "senderId": "", "senderName": "", "chatName": chat_id.split("@")[0],
                  "isGroup": chat_id.endswith("@g.us"), "body": text, "hasMedia": False, "mediaType": "",
                  "mediaUrls": [], "mentionedIds": [], "timestamp": int(time.time()), "direction": "out",
                  "history": False}
            with self._lock:
                self._queue.append(ev)
        threading.Thread(target=push, daemon=True).start()

    def _handler(self):
        double = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):  # quiet
                pass

            def _json(self, obj, code=200):
                body = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _body(self) -> dict:
                n = int(self.headers.get("Content-Length") or 0)
                try:
                    return json.loads(self.rfile.read(n) or b"{}")
                except ValueError:
                    return {}

            def do_GET(self):
                path = urlparse(self.path).path
                with double._lock:
                    double.calls.append({"m": "GET", "path": path, "t": time.time()})
                    if path == "/health":
                        return self._json({"status": "connected", "queueLength": len(double._queue), "uptime": 1,
                                           "scriptHash": _script_hash(), "qr": None})
                    if path == "/messages":
                        out, double._queue = double._queue, []
                        return self._json(out)
                if path == "/contacts":
                    return self._json({"contacts": double._contacts, "groups": [], "partial": True})
                if path == "/chats":
                    return self._json({"chats": [], "complete": True, "known": 0})
                if path in ("/sync", "/reads"):
                    return self._json([])
                if path.startswith("/chat/"):
                    cid = path[len("/chat/"):]
                    return self._json({"name": cid.split("@")[0], "isGroup": cid.endswith("@g.us"), "participants": []})
                return self._json({"error": "not found"}, 404)

            def do_POST(self):
                path = urlparse(self.path).path
                body = self._body()
                with double._lock:
                    double.calls.append({"m": "POST", "path": path, "body": body, "t": time.time()})
                if path in ("/send", "/send-media"):
                    chat_id = str(body.get("chatId") or "")
                    text = str(body.get("message") or body.get("caption") or "")
                    if not chat_id or (path == "/send" and not text):
                        return self._json({"error": "chatId and message are required"}, 400)
                    mid = "3EB0" + uuid.uuid4().hex[:16].upper()
                    with double._lock:
                        double.sent.append({"path": path, "chatId": chat_id, "text": text, "messageId": mid,
                                            "t": time.time()})
                    double._echo_later(chat_id, text, mid)
                    return self._json({"success": True, "messageId": mid, "messageIds": [mid]})
                if path == "/mark-read":
                    return self._json({"success": True, "marked": len(body.get("keys") or [])})
                if path in ("/mark-unread", "/typing", "/edit"):
                    return self._json({"success": True})
                if path == "/history":
                    return self._json({"available": False, "requested": 0})
                if path == "/group":
                    return self._json({"id": uuid.uuid4().hex[:18] + "@g.us", "subject": body.get("subject") or ""})
                return self._json({"error": "not found"}, 404)

        return H


def env_for(double: Double, workspace: Path) -> dict:
    """The sandbox env that turns WhatsApp on against the double (the sandbox already isolates the session dir)."""
    return {"WA_ENABLED": "1", "WA_BRIDGE_PORT": str(double.port),
            "WA_SESSION_DIR": str(workspace / "connectors" / "whatsapp-session")}


def assert_isolated(env: dict, workspace: Path, double: Double) -> None:
    """Before the first order: the engine's bridge is the double, never the real one, and its session is the sandbox's."""
    port = int(env.get("WA_BRIDGE_PORT") or 0)
    assert port == double.port and port != REAL_BRIDGE_PORT, f"bridge port {port} is not the double's"
    sess = Path(env.get("WA_SESSION_DIR") or "").resolve()
    assert str(sess).startswith(str(workspace.resolve()) + "/"), f"session dir {sess} is outside the sandbox"
    assert any(c["path"] == "/health" for c in double.calls), "the engine never asked the double for /health"
