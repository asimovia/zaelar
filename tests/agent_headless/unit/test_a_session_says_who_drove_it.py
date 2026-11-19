"""A session says WHO drove it (V2-939).

A browser driven by a program and a person's browser produced identical sessions: a reader of the stored events had
no fact to tell a verification run from real use. The connecting page now reports what it knows
(`navigator.webdriver`, an optional harness tag) and the request carries its User-Agent; the session stamps those
facts ONCE per screen as a `session`/`client` event, and `observability/flows.py::sessions` returns them with the
session's own `source`. Facts only: nothing in the engine classifies or treats the session differently."""
from __future__ import annotations

import pytest

from bus import log as buslog
from observability import flows, identity

HEADLESS = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/150.0 Safari/537.36"


@pytest.fixture()
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(buslog, "_conn", None)
    monkeypatch.setattr(buslog, "db_path", lambda: tmp_path / "zaelar.db")
    yield lambda rows: buslog._insert([buslog._row({"ts_ms": ts, "topic": "observer", "payload": p}) for ts, p in rows])
    if buslog._conn is not None:
        buslog._conn.close()


def _row(sid: str) -> dict:
    return next(r for r in flows.sessions(limit=10) if r["session_id"] == sid)


def test_the_sessions_read_returns_source_and_client_facts(db):
    db([(1000.0, {"sid": "s1", "cat": "system", "kind": "session", "label": "start", "source": "frontend"}),
        (1001.0, {"sid": "s1", "cat": "system", "kind": "session", "label": "client",
                  "ua": HEADLESS, "automated": True, "tag": "", "dev": "desktop:ab12"}),
        (1002.0, {"sid": "s2", "cat": "system", "kind": "session", "label": "start", "source": "auto"}),
        (1003.0, {"sid": "s2", "cat": "widget", "kind": "ui", "label": "tap", "src": "user"})])
    one, two = _row("s1"), _row("s2")
    assert (one["source"], one["client_ua"], one["client_automated"], one["client_tag"]) == ("frontend", HEADLESS, 1, "")
    assert (two["source"], two["client_ua"], two["client_automated"]) == ("auto", None, None), "no client mark, no fact"
    assert one["last_real_ms"] is None, "the client mark is a system fact, never a person's activity"


def test_note_client_stamps_once_per_screen_and_opens_nothing(monkeypatch):
    sent = []
    monkeypatch.setattr(identity, "_emit_session", lambda label, info, extra=None: sent.append((label, info["id"], extra)))
    monkeypatch.setattr(identity, "_clients_seen", set())
    monkeypatch.setitem(identity._session, "id", None)
    assert identity.note_client(ua=HEADLESS, automated=True) is False, "no open session: nothing is opened for it"
    assert sent == []
    monkeypatch.setitem(identity._session, "id", "sess-1")
    assert identity.note_client(ua=HEADLESS, automated=True, dev="desktop:ab12") is True
    assert identity.note_client(ua=HEADLESS, automated=True, dev="desktop:ab12") is False, "a reconnection says nothing new"
    assert identity.note_client(ua=HEADLESS, automated=True, dev="mobile:cd34") is True, "another screen is another fact"
    label, sid, extra = sent[0]
    assert (label, sid) == ("client", "sess-1")
    assert extra == {"ua": HEADLESS, "automated": True, "tag": "", "dev": "desktop:ab12"}


def test_the_connecting_page_hands_its_facts_to_the_session(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from observability import api

    noted = []
    monkeypatch.setattr(identity, "begin_session", lambda source, force=False: {"id": "sess-9"})
    monkeypatch.setattr(identity, "note_client", lambda **kw: noted.append(kw))
    app = FastAPI()
    app.include_router(api.router)
    r = TestClient(app).post("/api/observability/session/start", headers={"User-Agent": HEADLESS},
                             json={"source": "frontend", "automated": True, "tag": "probe-run", "dev": "desktop:ab12"})
    assert r.status_code == 200
    assert noted == [{"ua": HEADLESS, "automated": True, "tag": "probe-run", "dev": "desktop:ab12"}]
    monkeypatch.setattr(identity, "begin_session", lambda source, force=False: {})
    noted.clear()
    TestClient(app).post("/api/observability/session/start", json={"automated": True})
    assert noted == [], "the agent is off and no session opened: nothing to stamp"
