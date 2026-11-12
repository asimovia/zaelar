"""A step a network agent HANDS BACK («your agent should do it») reaches the worker whole, is done once, and is reported.

Agents that resolve an errand but cannot finish it (a booking engine they hold no access to, a restaurant's own form,
a phone they do not dial) answer `200` with a `handoff` object. Before this the worker got it as raw `data` among other
fields: nothing told it the agent had handed it the job, nothing bound the outcome to that order, and nothing stopped
the same order from being placed again after a submit whose result was never seen. Now (`nucleo/mesh_handoff`, any
agent, read by shape):

  · `hbmesh call` returns `handed_back` — reason, link (and what it already carries), phone, the fields with HIS
    values (null = ask him), the platform's own `note` verbatim, the action, how to report, and the agent's own way to
    do it (`agent_can_do`) when it offers one — with the rules in `next`, never a platform table of ours;
  · the same order (whatever its request key) is refused while its handed-back step has no reported outcome;
  · `hbmesh report <thread> <outcome>` sends one of the agent's OWN outcomes in its `reportOutcome` shape, the
    placeholders filled from its own answer; after it the order may be placed again; a dry run guards nothing.

The handoff is the agent's documented shape (its handover, 2026-11-12) with the live dry-run's phone step.

Disarm: drop the `duplicate` check in `mesh_call.call` → red; make `of` read only `data` → red.
"""
from __future__ import annotations

import pytest

from nucleo import mesh_agents, mesh_call, mesh_handoff

EP = "https://dining.example.test"
CARD = {"skills": [{"id": "book", "pricing": {"amount": 0, "currency": "free"}}], "pricing": {"amount": 0}}
HANDED = {"status": "DELEGATE_TO_CLIENT", "tier": "platform", "bookingRef": "bk_1", "handoff": {
    "message": "TableScout cannot book this restaurant itself; your agent should do it.",
    "reason": "The booking runs on a third-party engine.", "tier": "platform", "provider": "sevenrooms",
    "bookingUrl": "https://www.sevenrooms.example/explore/x/reservations/create/search?date=2026-11-27&party_size=2",
    "prefilledFields": ["date", "guests"], "phone": "+34910000000",
    "fields": [{"name": "date", "value": "2026-11-27", "required": True},
               {"name": "email", "value": None, "required": False}],
    "providerNote": "This platform prohibits unauthorized AI automation; hand the link to the user.",
    "clientAction": "Open bookingUrl in the user's browser … Then report the outcome (reportOutcome).",
    "phoneNext": True,
    "reportOutcome": {"method": "POST", "path": "/v1/book/outcome",
                      "body": {"booking_ref": "<bookingRef>", "outcome": "booked|no_availability|failed|abandoned"}}},
    "next": {"action": "book-by-phone", "method": "POST", "path": "/v1/book-by-phone",
             "request": {"v": 2, "restaurant": {"name": "Casa"}, "date": "2026-11-27", "time": "21:00"}}}
ORDER = {"restaurant": {"name": "Casa"}, "date": "2026-11-27", "time": "21:00", "party_size": 2}


@pytest.fixture
def net(tmp_path, monkeypatch):
    from memory import db as memdb
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    sent = []
    monkeypatch.setattr(mesh_call, "_agent", lambda aid, errand: {"agent_id": aid, "endpoint": EP})
    monkeypatch.setattr(mesh_agents, "_card_of", lambda ep: CARD)
    monkeypatch.setattr(mesh_agents, "_bearer_for", lambda agent, ep: None)
    monkeypatch.setattr(mesh_agents, "_note_answer", lambda *a: None)
    monkeypatch.setattr(mesh_agents, "_post", lambda url, body, timeout=0, bearer=None:
                        sent.append((url, body)) or (200, HANDED))
    from nucleo import routes
    monkeypatch.setattr(routes, "plan", lambda errand, locale=None: routes.store.Plan())
    return sent


def test_the_handed_back_step_reaches_the_worker_whole_with_its_rules():
    h = mesh_handoff.of(HANDED)
    assert h["url"].startswith("https://www.sevenrooms.example/") and h["prefilled"] == ["date", "guests"]
    assert h["note"].startswith("This platform prohibits") and h["report_as"][0] == "booked"
    assert {"name": "email", "value": None, "required": False} in h["fields"]           # null = ask him, never invent
    assert h["agent_can_do"] == {"skill": "book-by-phone", "request": HANDED["next"]["request"]}
    assert mesh_handoff.of({"status": "CONFIRMED_API", "result": {}}) is None


def test_the_same_order_is_not_placed_twice_until_its_outcome_is_reported(net):
    first = mesh_call.call("tablescout", "book", dict(ORDER), errand="reservar")
    assert first["ok"] and first["handed_back"]["tier"] == "platform" and "Submit ONCE" in first["next"]
    again = mesh_call.call("tablescout", "book", dict(ORDER, idempotency_key="another"), errand="reservar")
    assert again["duplicate"] and again["thread"] == first["thread"] and len(net) == 1   # nothing left the machine
    assert not mesh_handoff.report(first["thread"], "maybe")["ok"]                        # only the agent's outcomes
    told = mesh_handoff.report(first["thread"], "abandoned")
    assert told["sent"] and net[-1] == (f"{EP}/v1/book/outcome", {"booking_ref": "bk_1", "outcome": "abandoned"})
    assert mesh_call.call("tablescout", "book", dict(ORDER), errand="reservar")["ok"]    # reported: placeable again


def test_a_dry_run_guards_nothing(net):
    mesh_call.call("tablescout", "book", dict(ORDER, dry_run=True), errand="reservar")
    assert mesh_call.call("tablescout", "book", dict(ORDER, dry_run=True), errand="reservar")["ok"]
