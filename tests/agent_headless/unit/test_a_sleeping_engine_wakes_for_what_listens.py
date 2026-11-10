"""A sleeping engine is woken for ONE instant: its next job, its next deadline, or — only while something listens to a
channel that can be caught up — its next listen pass (V2-872 F2, node 2.841).

The wake report used to carry the scheduler's jobs alone. An errand's expiry, a waiting row's deadline and an owed
notice's retry ran on the same pulse and were never reported, so an engine asleep through them acted on none. And an
engine whose user had a rule over arriving mail was either woken for nothing or never: there was no notion of a
listener. Now: a channel LISTENS when it is connected, can be caught up, and something declared reacts to it; with no
job, no deadline and no listener the report is `null` and the engine may sleep for a month.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from nucleo.pulse import deadlines, listeners, scheduler, wake

NOW = 1_900_000_000.0


# ── the listener definition (pure) ──────────────────────────────────────────────────────────────────────────────
def test_a_connected_channel_nothing_reacts_to_is_not_a_listener():
    """The default triage only sorts an inbox: the next start sorts it just the same."""
    assert listeners.decide({"email", "telegram"}) == set()


def test_nothing_connected_is_never_a_listener_whatever_reacts():
    assert listeners.decide(set(), subscriptions=[{"topic": "mail.in", "match": {}}], prefs={"email"}) == set()


def test_a_rule_subscribed_to_arriving_mail_makes_the_mailbox_listen():
    assert listeners.decide({"email", "whatsapp"}, subscriptions=[{"topic": "mail.in", "match": {"sender": "sender@example.com"}}]) \
        == {"email"}


def test_a_rule_over_messages_listens_where_its_platform_says_or_on_every_messenger():
    subs = [{"topic": "connector.msg", "match": {"platform": "telegram"}}]
    assert listeners.decide({"email", "whatsapp", "telegram"}, subscriptions=subs) == {"telegram"}
    subs = [{"topic": "connector.msg", "match": {"sender": "+34600"}}]
    assert listeners.decide({"email", "whatsapp", "telegram"}, subscriptions=subs) == {"whatsapp", "telegram"}


def test_a_spoken_note_not_yet_read_could_be_about_arrivals_only_by_its_scope():
    domains = {"email": "messaging", "whatsapp": "messaging"}
    assert listeners.decide({"email"}, note_scopes=["global"], channel_domains=domains) == {"email"}
    assert listeners.decide({"email"}, note_scopes=["subject:c-1"], channel_domains=domains) == {"email"}
    assert listeners.decide({"email"}, note_scopes=["messaging/email"], channel_domains=domains) == {"email"}
    assert listeners.decide({"email"}, note_scopes=["widget:agenda", "voice"], channel_domains=domains) == set()


def test_a_row_waiting_for_an_arrival_listens_on_its_channel():
    assert listeners.decide({"email", "whatsapp"}, waits=["event:mail.in:email:sender@example.com"]) == {"email"}
    assert listeners.decide({"email", "whatsapp"}, waits=["event:connector.msg:whatsapp:346@s"]) == {"whatsapp"}
    assert listeners.decide({"email"}, waits=["user_answer", "worker"]) == set(), "his answer is not a connector"


def test_a_live_errand_listens_where_its_conversation_is_or_everywhere_before_it_has_one():
    assert listeners.decide({"email", "whatsapp"}, errand_threads=[["whatsapp"]]) == {"whatsapp"}
    assert listeners.decide({"email", "whatsapp"}, errand_threads=[[]]) == {"email", "whatsapp"}


def test_his_notify_preference_is_a_listener():
    assert listeners.decide({"email", "telegram"}, prefs={"telegram"}) == {"telegram"}


def test_a_channel_with_no_backlog_cannot_be_caught_up_and_never_listens():
    """A MeshKore cluster relays to whoever is connected now: a periodic pass catches nothing up."""
    assert listeners.decide({"meshkore"}, subscriptions=[{"topic": "cluster.msg"}], prefs={"meshkore"}) == set()


def test_the_listen_instant_is_a_fixed_grid_so_one_report_covers_a_whole_interval():
    a = listeners.next_listen(NOW, 600)
    assert NOW < a <= NOW + 600
    assert listeners.next_listen(a - 599, 600) == a == listeners.next_listen(a - 1, 600)
    assert listeners.next_listen(a, 600) == a + 600


def test_the_interval_is_declared_once_in_the_resources_policy():
    assert listeners.listen_every_s() == 600.0


def test_the_readings_come_from_what_the_engine_stores(monkeypatch):
    """`active_listeners` over the real stores: a stored subscription over arriving mail, with the mailbox connected."""
    import rules
    from connectors.email import config as email_cfg
    monkeypatch.setattr(email_cfg, "enabled", lambda: True)
    monkeypatch.setattr(email_cfg, "has_credentials", lambda: True)
    assert listeners.active_listeners() == set()
    rules.add("global", "pref", "on_event", {"topic": "mail.in", "match": {"sender": "sender@example.com"}, "do": "add a task"},
              text="when sender@example.com writes, add a task")
    assert listeners.active_listeners() == {"email"}


# ── the one instant ───────────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def _quiet(monkeypatch):
    monkeypatch.setattr(scheduler, "next_due", lambda: None)
    monkeypatch.setattr(deadlines, "upcoming", lambda now: {})
    monkeypatch.setattr(listeners, "active_listeners", lambda: set())
    return monkeypatch


def test_no_job_no_deadline_no_listener_reports_null(_quiet):
    assert wake.next_due(NOW) == (None, {})


def test_a_listener_asks_for_the_next_listen_pass(_quiet):
    _quiet.setattr(listeners, "active_listeners", lambda: {"email"})
    nxt, why = wake.next_due(NOW)
    assert nxt == listeners.next_listen(NOW, 600) and list(why) == ["listen:email"]


def test_a_deadline_earlier_than_everything_wins(_quiet):
    _quiet.setattr(scheduler, "next_due", lambda: NOW + 7200)
    _quiet.setattr(listeners, "active_listeners", lambda: {"email"})
    _quiet.setattr(deadlines, "upcoming", lambda now: {"errand": now + 90})
    assert wake.next_due(NOW)[0] == NOW + 90


def test_the_scheduler_still_wins_when_it_is_first(_quiet):
    _quiet.setattr(scheduler, "next_due", lambda: NOW + 30)
    _quiet.setattr(deadlines, "upcoming", lambda now: {"waiting": now + 90})
    assert wake.next_due(NOW) == (NOW + 30, {"scheduler": NOW + 30, "waiting": NOW + 90})


def test_an_unreadable_listener_or_deadline_never_hides_the_job(_quiet):
    def boom(*_a):
        raise RuntimeError("unreadable")
    _quiet.setattr(scheduler, "next_due", lambda: NOW + 30)
    _quiet.setattr(deadlines, "upcoming", boom)
    _quiet.setattr(listeners, "active_listeners", boom)
    assert wake.next_due(NOW)[0] == NOW + 30


# ── the deadlines the pulse acts on by itself ──────────────────────────────────────────────────────────────────
def test_an_errand_expiry_and_a_waiting_row_deadline_are_reported_only_ahead():
    from nucleo import errands
    from nucleo.circuit import ledger
    now = time.time()
    row = errands.start("book a table for two at the bistro", window_s=3600, now=now)
    try:
        got = deadlines.upcoming(now)
        assert got.get("errand") == float(row["expires_at"])
        assert "errand" not in deadlines.upcoming(row["expires_at"] + 1), "a past expiry is the awake pulse's"
        ts = ledger.store()
        ts.task_put({"id": "w-1", "goal": "ask him", "state": "running", "created_at": int(now)})
        ledger.waiting("w-1", ledger.USER_ANSWER, "a1", "which day?", now=now)
        assert deadlines.upcoming(now)["waiting"] == pytest.approx(now + ledger.answer_wait_s(now), abs=2)
    finally:
        errands.close(row["id"], "closed", now=now)
        ledger.store().task_forget("w-1")


def test_an_owed_notice_is_retried_only_when_a_device_can_take_it(monkeypatch):
    from memory.api import notices as store
    from nucleo.pulse import notices
    now = int(time.time())
    store.insert("k-owed", "reminder", "t", "b", "", now, "{}")
    store.update(store.by_key("k-owed")["id"], state="owed", next_try_at=now + 300)
    monkeypatch.setattr(notices, "devices", lambda: [])
    assert "owed" not in deadlines.upcoming(now), "with no device a retry only owes it again"
    monkeypatch.setattr(notices, "devices", lambda: [{"id": "d1"}])
    assert deadlines.upcoming(now)["owed"] == now + 300


# ── the report itself ─────────────────────────────────────────────────────────────────────────────────────────
class _Client:
    posts: list = []

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None, headers=None):
        _Client.posts.append(json)
        return type("R", (), {"status_code": 200})()


def test_a_listening_engine_re_reports_once_its_pass_has_come_and_never_needs_a_writer(_quiet):
    import httpx
    wake._reset_for_tests()
    _Client.posts = []
    _quiet.setattr(httpx, "AsyncClient", _Client)
    _quiet.setenv("ZAELAR_WAKE_URL", "https://cp.example/wake")
    _quiet.setattr(listeners, "active_listeners", lambda: {"email"})
    first = listeners.next_listen(NOW, 600)
    assert asyncio.run(wake.flush(NOW)) is True and _Client.posts == [{"next_due": int(first)}]
    assert asyncio.run(wake.flush(NOW + 30)) is False, "nothing changed and nothing is stale yet"
    assert asyncio.run(wake.flush(first + 1)) is True and _Client.posts[-1] == {"next_due": int(first + 600)}
    # a rule removed with nobody calling note_changed: the recheck still reports null within _RECHECK_S
    _quiet.setattr(listeners, "active_listeners", lambda: set())
    assert asyncio.run(wake.flush(first + 2)) is False
    assert asyncio.run(wake.flush(first + 1 + wake._RECHECK_S)) is True and _Client.posts[-1] == {"next_due": None}
    wake._reset_for_tests()
