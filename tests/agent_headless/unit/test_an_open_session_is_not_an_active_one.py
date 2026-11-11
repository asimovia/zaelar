"""An OPEN session is not an ACTIVE one (2026-11-11).

Background noise opened and kept work sessions: a widget's tick and the tab's own state reports (it came to the
foreground, the agent state moved) were stored as activity, so a sessions list read sessions with nobody in them as
active. A session is ACTIVE while its voice room is up or a person did something within the idle window; the stored
rows say which (`paced`, `voice.up`/`voice.down`), and `observability/flows.py` reads them with one rule."""
from __future__ import annotations

import pytest

from bus import log as buslog
from observability import flows, identity
from voice import observer

NOW = 1_800_000_000_000.0
MIN = 60_000


@pytest.fixture()
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(buslog, "_conn", None)
    monkeypatch.setattr(buslog, "db_path", lambda: tmp_path / "zaelar.db")
    yield lambda rows: buslog._insert([buslog._row({"ts_ms": ts, "topic": "observer", "payload": p}) for ts, p in rows])
    if buslog._conn is not None:
        buslog._conn.close()


def _row(sid: str) -> dict:
    return next(r for r in flows.sessions(limit=10) if r["session_id"] == sid)


def test_background_noise_alone_is_not_activity(db):
    db([(NOW - 1 * MIN, {"sid": "s1", "cat": "widget", "kind": "ui", "label": "tab:visibility", "src": "frontend"}),
        (NOW - 1 * MIN, {"sid": "s1", "cat": "widget", "kind": "widget", "label": "tick", "paced": True}),
        (NOW - 1 * MIN, {"sid": "s1", "cat": "pulse", "kind": "pulse", "label": "beat"}),
        (NOW - 1 * MIN, {"sid": "s1", "cat": "system", "kind": "homeostasis", "label": "ok"})])
    r = _row("s1")
    assert r["last_real_ms"] is None
    assert flows.is_active(r, NOW) is False, "THE BUG: a session with only background noise read as active"


def test_a_person_or_a_connected_voice_is(db):
    db([(NOW - 2 * MIN, {"sid": "s2", "cat": "flash", "kind": "transcript", "label": "user", "role": "user"}),
        (NOW - 30 * MIN, {"sid": "s3", "cat": "flash", "kind": "transcript", "label": "user"}),
        (NOW - 30 * MIN, {"sid": "s3", "cat": "system", "kind": "session", "label": "voice.up"}),
        (NOW - 40 * MIN, {"sid": "s4", "cat": "flash", "kind": "transcript", "label": "user"}),
        (NOW - 39 * MIN, {"sid": "s4", "cat": "system", "kind": "session", "label": "voice.up"}),
        (NOW - 35 * MIN, {"sid": "s4", "cat": "system", "kind": "session", "label": "voice.down"}),
        (NOW - 1 * MIN, {"sid": "s5", "cat": "widget", "kind": "ui", "label": "orb:power", "src": "user"})])
    assert flows.is_active(_row("s2"), NOW), "he spoke two minutes ago"
    assert flows.is_active(_row("s3"), NOW), "the voice room is up"
    assert not flows.is_active(_row("s4"), NOW), "the voice closed and nobody did anything since"
    assert flows.is_active(_row("s5"), NOW), "a tap is a person"


def test_work_on_the_engines_own_clock_is_stored_marked_and_opens_no_session(monkeypatch):
    monkeypatch.setattr(identity, "session_id", lambda: pytest.fail("a paced event must not open a session"))
    monkeypatch.setattr(identity, "session_info", lambda: {"session_id": ""})
    with identity.paced():
        ev = observer.stamp_identity({"kind": "ui", "label": "tab:visibility"})
    assert ev.get("paced") is True
    assert ev.get("sid") == ""
