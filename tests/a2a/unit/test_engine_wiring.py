"""T580 · the engine's wiring of a2a: off by default (no thread, routes 404), grants as rules rows, the policy seam,
the calendar item's intervals and the outbound scanner."""
from __future__ import annotations

import pytest

from a2a.grants import Grant, Grants
from a2a.items import default_items


@pytest.fixture
def rules_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    from rules import store
    store._reset_for_tests()
    yield store
    store._reset_for_tests()


def test_off_by_default_starts_nothing_and_the_routes_are_absent():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from config import v2
    from server import a2a_api
    assert v2._DEFAULTS["a2a"]["enabled"] is False
    a2a_api.stop()
    a2a_api._state.update(agent=None, jobs=None, gate=None)
    assert a2a_api.start() is False and a2a_api._state["thread"] is None
    app = FastAPI()
    app.include_router(a2a_api.router)
    c = TestClient(app)
    assert c.post("/api/a2a/wake", content="{}").status_code == 404
    assert c.get("/api/a2a/status").status_code == 404


def test_a_grant_is_one_rules_row_under_the_contacts_subject(rules_db):
    from server.a2a_wiring import RULE_KEY, RulesGrantStore
    st = RulesGrantStore()
    g = Grants(st, default_items()).grant("calendar", "contact:c7", ["see"], expires_at=2e9)
    rows = [r for r in rules_db.rows() if r["key"] == RULE_KEY]
    assert [r["scope"] for r in rows] == ["subject:c7/a2a/calendar"] and rows[0]["until"] == 2e9
    assert [x.id for x in st.list()] == [g.id] and isinstance(st.list()[0], Grant)
    st.delete(g.id)
    assert st.list() == []


def test_the_policy_reads_his_standing_never_for_that_person(rules_db, monkeypatch):
    from nucleo import consent
    from server import a2a_wiring
    monkeypatch.setattr(consent, "decide_act", lambda *a, **k: {"verdict": consent.REFUSE})
    assert a2a_wiring.policy("c7", "calendar", "see") == "never"
    monkeypatch.setattr(consent, "decide_act", lambda *a, **k: {"verdict": consent.RUN})
    assert a2a_wiring.policy("c7", "calendar", "see") is None


def test_the_calendar_item_gives_intervals_and_never_a_title(monkeypatch):
    from server import a2a_wiring
    from widgets.agenda import data
    monkeypatch.setattr(data, "load_db", lambda: {"meetings": [
        {"date": "2030-01-02", "startTime": "10:00", "endTime": "11:30", "title": "Dentist"}]})
    out = a2a_wiring.busy("2030-01-01", "2030-01-03")
    assert out and all(set(iv) == {"start", "end"} for iv in out)
    assert out[0]["start"] == "2030-01-02T10:00" and "Dentist" not in str(out)


def test_the_outbound_scanner_is_the_engines(monkeypatch):
    from connectors.meshkore import security
    from server import a2a_wiring
    monkeypatch.setattr(security, "scan_outbound", lambda t: (t, "secret" if "sk-" in t else None))
    assert a2a_wiring.scan_outbound("my key sk-123") == "secret"
    assert a2a_wiring.scan_outbound("hello") is None
