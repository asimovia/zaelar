"""A Google People API that answers on loopback: the address book of an INVENTED account, for a sandbox engine.

The contacts connector reads the People API at `ZAELAR_CONTACTS_API_BASE` when it is set
(`connectors/contacts/service._api`); a sandbox pointed here, with a token file in its own workspace, reads a
connected Google account whose people are the ones below — and nothing leaves the machine. Every read is recorded.
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


def person(i: int, name: str, phone: str) -> dict:
    return {"resourceName": f"people/c{i}", "etag": f"e{i}",
            "names": [{"displayName": name, "metadata": {"primary": True}}],
            "phoneNumbers": [{"value": phone, "metadata": {"primary": True}}]}


class Double:
    def __init__(self, port: int, people: list[dict]):
        self.port, self.people, self.reads = int(port), list(people), []
        self._server = ThreadingHTTPServer(("127.0.0.1", self.port), self._handler())
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def start(self) -> "Double":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def _handler(self):
        double = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, obj, code=200):
                body = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                path = urlparse(self.path).path
                double.reads.append({"path": path, "t": time.time()})
                if path.endswith("/people/me/connections"):
                    return self._json({"connections": double.people, "nextSyncToken": "s1",
                                       "totalItems": len(double.people)})
                if path.endswith("/otherContacts"):
                    return self._json({"otherContacts": [], "nextSyncToken": "s2"})
                if path.endswith("/contactGroups"):
                    return self._json({"contactGroups": []})
                return self._json({"error": {"code": 404, "message": "not found"}}, 404)

        return H


def connect(workspace: Path, provider: str = "google-contacts") -> None:
    """The workspace's own token file says the account is connected (an invented token, valid for a day)."""
    cred = workspace / "credentials"
    cred.mkdir(parents=True, exist_ok=True)
    (cred / "contacts_oauth.json").write_text(json.dumps({"accounts": {provider: {
        "access_token": "sandbox-token", "refresh_token": "sandbox-refresh", "expires_at": int(time.time()) + 86400,
        "tier": "saved"}}}))
