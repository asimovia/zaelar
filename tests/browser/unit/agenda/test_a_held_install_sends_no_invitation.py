"""The outbound switch holds an invitation and the answer to one (contention M1, node 5.77).

The agenda's two acts that reach somebody outside — `invite` (by the calendar, or an .ics by mail) and `rsvp_meeting`
(his answer on Google) — ask the one exit door (`connectors/exit`, lane `invite`) before they reach out. Held → a
refusal he hears in his language and nothing reaches the calendar facade nor the bus. The .ics rung leaves through
`exit.leave` with its lane, so it is counted like any other message. Without the variable both behave as before.
Nothing here touches a real calendar or mailbox: the Google facade and the bus publisher are doubles.
"""
from __future__ import annotations

import datetime as _dt

import pytest

from connectors import exit as door

AHEAD = (_dt.date.today() + _dt.timedelta(days=5)).isoformat()


class _Cal:
    def __init__(self):
        self.calls = []

    def connected(self):
        return True

    def invite(self, m, emails):
        self.calls.append(("invite", tuple(emails)))
        return {"ok": True, "added": list(emails), "already": []}

    def rsvp(self, m, answer):
        self.calls.append(("rsvp", answer))
        return {"ok": True, "meeting": {"responseStatus": answer}}


@pytest.fixture
def ag(tmp_path, monkeypatch):
    from widgets import store
    from widgets.agenda import gcal
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.delenv(door.ENV, raising=False)
    door._reset_counters()
    cal = _Cal()
    monkeypatch.setattr(gcal, "svc", lambda: cal)
    published = []
    from connectors.messaging import ingest
    monkeypatch.setattr(ingest, "publish_send", lambda order: published.append(order))
    monkeypatch.setattr(ingest, "publish_send_failed", lambda order, why: None)
    from connectors.email import config as mailcfg
    monkeypatch.setattr(mailcfg, "address", lambda: "me@example.com")
    from widgets.agenda import data as _d
    db = _d.load_db()
    db["meetings"] = [{"title": "Kickoff", "date": AHEAD, "startTime": "10:00", "endTime": "11:00",
                       "source": "google", "googleId": "ev1", "googleCalendarId": "primary"},
                      {"title": "Standup", "date": AHEAD, "startTime": "09:00", "endTime": "09:15"}]
    store.save("agenda", db)
    _d.cal, _d.published = cal, published
    return _d


def test_without_the_switch_the_calendar_invites_and_the_ics_leaves_by_the_door_with_its_lane(ag):
    assert ag.apply_action("invite", {"who": "rowan@example.com", "meeting": "Kickoff"})["ok"]
    assert ("invite", ("rowan@example.com",)) in ag.cal.calls
    res = ag.apply_action("invite", {"who": "rowan@example.com", "meeting": "Standup"})
    assert res["ok"] and res["how"] == "email", res
    assert [o["lane"] for o in ag.published] == [door.INVITE]
    assert door.counters().get("send/invite/out") == 1, door.counters()


@pytest.mark.parametrize("meeting", ["Kickoff", "Standup"])
def test_with_the_switch_on_no_invitation_leaves_by_either_rung(ag, monkeypatch, meeting):
    monkeypatch.setenv(door.ENV, "invite")
    res = ag.apply_action("invite", {"who": "rowan@example.com", "meeting": meeting})
    assert res["ok"] is False and door.is_held(res.get("error")), res
    assert str(res.get("message") or "").strip(), "he hears why"
    assert not ag.cal.calls and not ag.published
    assert door.counters().get("invite/invite/held") == 1, door.counters()


def test_without_the_switch_his_answer_reaches_google(ag):
    res = ag.apply_action("rsvp_meeting", {"title": "Kickoff", "answer": "acepto"})
    assert ("rsvp", "accepted") in ag.cal.calls, (res, ag.cal.calls)


def test_with_the_switch_on_his_answer_does_not_reach_google_and_the_row_is_untouched(ag, monkeypatch):
    monkeypatch.setenv(door.ENV, "all")
    res = ag.apply_action("rsvp_meeting", {"title": "Kickoff", "answer": "acepto"})
    assert res["ok"] is False and str(res.get("error") or "").strip(), res
    assert not ag.cal.calls
    m = next(x for x in ag.load_db()["meetings"] if x["title"] == "Kickoff")
    assert "responseStatus" not in m
    assert door.counters().get("rsvp/invite/held") == 1, door.counters()
