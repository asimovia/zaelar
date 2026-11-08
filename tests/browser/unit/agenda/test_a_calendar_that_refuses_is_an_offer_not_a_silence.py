"""A calendar that refuses is an OFFER in the reply, never a silence nor a dead stop (2026-11-08).

Two doors of the agenda talk to Google, and both ended badly when Google said no:

  · `add_meeting` kept the local write (right) and said nothing (wrong): «Hecho» over an appointment that is in the
    agenda and NOT in the Google Calendar he actually looks at. The answer now carries `mirror: {mirrored: false,
    reason}` and a spoken `message` that offers to reconnect — only when a calendar IS connected (an operator who
    never linked Google is not asked at every appointment).
  · `invite` stopped dead when the calendar refused the guest. Sending the .ics anyway would be wrong (an unlinked
    copy, and a send to a third party is his to grant), so the reply OFFERS it: the same call with `via: email`.
    With no mail connected, it offers to connect one. He can also NAME the mail rung for one call (`via: email`).

And `add_meeting` takes an optional `calendar` — the destination he names for that write; a name that matches none
of his calendars falls to the default one and is said back (`calendar_unknown`), never refused.
Nothing here touches a real calendar or mailbox: the Google facade and the mail door are doubles.
"""
from __future__ import annotations

import datetime as _dt

import pytest

AHEAD = (_dt.date.today() + _dt.timedelta(days=5)).isoformat()


class _Cal:
    """The calendar facade the agenda reaches (`gcal.svc()`), with the answer the test chooses."""

    def __init__(self, *, connected=True, create=None, invite=None):
        self._connected, self.calls = connected, []
        self._create = create if create is not None else {"ok": True, "meeting": {}}
        self._invite = invite if invite is not None else {"ok": True, "added": [], "already": []}

    def connected(self):
        return self._connected

    def create_event(self, m, cal=""):
        self.calls.append(("create", cal))
        res = dict(self._create)
        if res.get("ok"):
            res["meeting"] = {**m, "googleId": "g1", "googleCalendarId": cal or "primary", "source": "google"}
        return res

    def invite(self, m, emails):
        self.calls.append(("invite", tuple(emails)))
        return dict(self._invite)


@pytest.fixture
def ag(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.agenda import data as _d
    return _d


def _use(monkeypatch, cal):
    from widgets.agenda import gcal
    monkeypatch.setattr(gcal, "svc", lambda: cal)


def _rows(title):
    from widgets import store
    return [m for m in store.load("agenda", {}).get("meetings", []) if m.get("title") == title]


# ── add_meeting: the mirror ───────────────────────────────────────────────────────────────────────────────

def test_a_refused_mirror_keeps_the_write_and_offers_to_reconnect(ag, monkeypatch):
    _use(monkeypatch, _Cal(create={"ok": False, "error": "401 invalid_grant"}))
    res = ag.apply_action("add_meeting", {"title": "Dentist", "date": AHEAD, "startTime": "10:00"})
    assert res.get("ok") is not False and _rows("Dentist"), "the local write is never lost"
    assert res.get("mirror", {}).get("mirrored") is False, res.get("mirror")
    assert "401" in res["mirror"]["reason"] and res["mirror"]["offer"] == "reconnect_calendar"
    assert str(res.get("message") or "").strip(), "a refused mirror is SAID, never silent"


def test_a_mirror_that_raised_is_offered_too(ag, monkeypatch):
    cal = _Cal()
    cal.create_event = lambda m, c="": (_ for _ in ()).throw(RuntimeError("timeout"))
    _use(monkeypatch, cal)
    res = ag.apply_action("add_meeting", {"title": "Physio", "date": AHEAD, "startTime": "12:00"})
    assert res.get("mirror", {}).get("mirrored") is False and "timeout" in res["mirror"]["reason"]


def test_a_mirrored_write_offers_nothing(ag, monkeypatch):
    _use(monkeypatch, _Cal())
    res = ag.apply_action("add_meeting", {"title": "Gym", "date": AHEAD, "startTime": "08:00"})
    assert "mirror" not in res and not str(res.get("message") or "").strip(), res.get("message")


def test_with_no_calendar_connected_nothing_is_offered(ag, monkeypatch):
    _use(monkeypatch, _Cal(connected=False))
    res = ag.apply_action("add_meeting", {"title": "Walk", "date": AHEAD, "startTime": "19:00"})
    assert "mirror" not in res, "an operator who never linked Google is not asked at every appointment"


def test_the_calendar_he_names_is_where_the_write_goes(ag, monkeypatch):
    cal = _Cal()
    _use(monkeypatch, cal)
    db = ag.load_db()
    db["google"] = {"calendars": [{"id": "primary", "summary": "Me", "primary": True},
                                  {"id": "work@group", "summary": "Trabajo"}], "defaultCalendarId": "primary"}
    from widgets import store
    store.save("agenda", db)
    ag.apply_action("add_meeting", {"title": "Board", "date": AHEAD, "startTime": "09:00", "calendar": "trabajo"})
    assert ("create", "work@group") in cal.calls, cal.calls
    res = ag.apply_action("add_meeting", {"title": "Coffee", "date": AHEAD, "startTime": "11:00",
                                          "calendar": "Holidays"})
    assert ("create", "primary") in cal.calls and res.get("calendar_unknown") == "Holidays", res.get("calendar_unknown")
    assert "calendar" not in (res.get("ignored") or []), "the key is read, never reported as unknown"


# ── invite: the second rung is offered ────────────────────────────────────────────────────────────────────

def _meeting_on_google(ag):
    from widgets import store
    db = ag.load_db()
    db["meetings"] = [{"title": "Kickoff", "date": AHEAD, "startTime": "10:00", "endTime": "11:00",
                       "source": "google", "googleId": "ev1", "googleCalendarId": "primary"}]
    store.save("agenda", db)


def test_a_refused_invite_offers_the_ics_by_mail(ag, monkeypatch):
    _meeting_on_google(ag)
    _use(monkeypatch, _Cal(invite={"ok": False, "error": "403 forbidden"}))
    from widgets.agenda import invite
    monkeypatch.setattr(invite, "_mail_from", lambda: "me@example.com")
    sent = []
    monkeypatch.setattr(invite, "_mail_invitation", lambda m, g, n: sent.append(g) or {"ok": True})
    res = ag.apply_action("invite", {"who": "rowan@example.com", "meeting": "Kickoff"})
    assert res["ok"] is False and not sent, "a refusal never sends the .ics behind his back"
    assert res["offer"]["action"] == "invite" and res["offer"]["payload"]["via"] == "email", res.get("offer")
    assert str(res.get("message") or "").strip(), "the offer is a line he hears"
    # his yes is the same call with the rung he named
    ag.apply_action("invite", res["offer"]["payload"])
    assert sent and sent[0]["emails"] == ["rowan@example.com"]


def test_a_refused_invite_with_no_mail_offers_to_connect_one(ag, monkeypatch):
    _meeting_on_google(ag)
    _use(monkeypatch, _Cal(invite={"ok": False, "error": "403 forbidden"}))
    from widgets.agenda import invite
    monkeypatch.setattr(invite, "_mail_from", lambda: "")
    res = ag.apply_action("invite", {"who": "rowan@example.com", "meeting": "Kickoff"})
    assert res["ok"] is False and res.get("offer") == {"connect": "email"}, res
    assert str(res.get("message") or "").strip()


def test_he_can_name_the_mail_rung_for_one_call(ag, monkeypatch):
    _meeting_on_google(ag)
    cal = _Cal()
    _use(monkeypatch, cal)
    from widgets.agenda import invite
    sent = []
    monkeypatch.setattr(invite, "_mail_invitation", lambda m, g, n: sent.append(g) or {"ok": True, "invited": g["emails"]})
    ag.apply_action("invite", {"who": "rowan@example.com", "meeting": "Kickoff", "via": "email"})
    assert sent and not any(c[0] == "invite" for c in cal.calls), cal.calls
