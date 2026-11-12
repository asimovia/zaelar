"""`hbmesh call <agent> <skill>`: ONE declared skill, free direct or priced through the relay, and its questions heard.

Measured before: `serve` put every errand to an agent's FIRST declared skill, so a booking errand to an agent whose
card declares `search`, `book` and `book-by-phone` came back as a search and never reached `book`. Now the worker
calls the skill it chose from the card, and:

  · a free skill goes direct; a priced one goes ONLY through the deployment's relay (`<egress>/p/mesh/<host><path>`,
    the egress credential, never the agent's) and only when the account can price it (an `agent` tariff row) —
    self-host, or no price, refuses BEFORE anything is sent;
  · an agent's questions come back as `agent_asks_user` with a thread; his answers (`reply`) rewrite the request
    and send it again whole; a standing answer of his is applied without asking him again;
  · `409` is said as the agent's refusal and never retried; `402` is never paid;
  · the request key is the thread id when the skill's own examples use one; a served skill teaches the route.

Disarm: make `mesh_relay.route` answer RELAY for a priced skill on self-host → red; drop the prefill round in
`mesh_call._exchange` → red.
"""
from __future__ import annotations

import pytest

from nucleo import mesh_agents, mesh_call, mesh_relay

EP = "https://dining.example.test"
CARD = {"skills": [
    {"id": "search", "pricing": {"amount": 0, "currency": "free"}},
    {"id": "book", "pricing": {"amount": 0, "currency": "free"}},
    {"id": "book-by-phone", "pricing": {"unit": "booking", "amount": 12300000, "currency": "lamports"},
     "examples": ['{"restaurant": {}, "idempotency_key": "order-1"}']}],
    "pricing": {"amount": 0, "currency": "free"}}
ASKS = {"status": "NEEDS_MANDATE", "questions": [
    {"id": "seating.any", "text": "¿Alguna mesa imprescindible?",
     "choices": [{"label": "Cualquier mesa", "set": {"seating.any": True}},
                 {"label": "Sí", "set": {"seating.must": None}, "needsValue": "seating"}]}]}


@pytest.fixture
def net(tmp_path, monkeypatch):
    from memory import db as memdb
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    import rules
    rules._reset_for_tests()
    sent, answers = [], []
    monkeypatch.setattr(mesh_call, "_agent", lambda aid, errand: {"agent_id": aid, "endpoint": EP})
    monkeypatch.setattr(mesh_agents, "_card_of", lambda ep: CARD)
    monkeypatch.setattr(mesh_agents, "_bearer_for", lambda agent, ep: None)
    monkeypatch.setattr(mesh_agents, "_note_answer", lambda *a: None)

    def _post(url, body, timeout=0, bearer=None):
        sent.append({"url": url, "body": body, "bearer": bearer})
        return answers.pop(0) if answers else (200, {"status": "CONFIRMED_API"})
    monkeypatch.setattr(mesh_agents, "_post", _post)
    learned = []
    from nucleo import routes
    monkeypatch.setattr(routes, "plan", lambda errand, locale=None: routes.store.Plan(domain="restaurant"))
    monkeypatch.setattr(routes, "learn", lambda domain, ch, **k: learned.append((domain, ch, k.get("target"))))
    yield sent, answers, learned, monkeypatch
    rules._reset_for_tests()


def _mediated(monkeypatch, *, priced: bool):
    from nucleo.energy import egress, tariffs
    monkeypatch.setattr(egress, "mediated", lambda: True)
    monkeypatch.setenv("ZAELAR_GATEWAY_URL", "https://egress.example.test/v1")
    monkeypatch.setenv("CONTROL_PLANE_SERVICE_TOKEN", "account-credential")
    monkeypatch.setattr(tariffs, "has_rate", lambda fam, key: priced and key == "tablescout.book-by-phone")
    monkeypatch.setattr(mesh_relay, "admit", lambda: True)


def test_the_chosen_free_skill_is_called_direct_and_teaches_its_route(net):
    sent, _answers, learned, _mp = net
    out = mesh_call.call("tablescout", "book", {"date": "2026-11-27"}, errand="reservar mesa")
    assert out["ok"] and sent[0]["url"] == f"{EP}/v1/book" and sent[0]["bearer"] is None
    assert learned == [("restaurant", "mesh", "tablescout/book")]


def test_a_skill_the_card_does_not_declare_is_never_called(net):
    sent, *_ = net
    out = mesh_call.call("tablescout", "cancel", {})
    assert not out["ok"] and not sent and [s["id"] for s in out["skills"]] == ["search", "book", "book-by-phone"]


def test_a_priced_skill_is_refused_on_self_host_before_anything_leaves(net):
    sent, *_ = net
    out = mesh_call.call("tablescout", "book-by-phone", {"date": "2026-11-27"})
    assert not out["ok"] and out["priced"] and not sent


def test_a_priced_skill_without_a_price_here_is_refused_even_with_a_relay(net):
    sent, _a, _l, mp = net
    _mediated(mp, priced=False)
    out = mesh_call.call("tablescout", "book-by-phone", {"date": "2026-11-27"})
    assert not out["ok"] and "cannot be charged" in out["reason"] and not sent


def test_a_priced_skill_goes_through_the_relay_with_the_account_credential(net):
    sent, answers, _l, mp = net
    _mediated(mp, priced=True)
    answers.append((202, {"jobId": "j1", "status": "PENDING_CALL", "poll": "/v1/jobs/j1", "jobToken": "jt"}))
    out = mesh_call.call("tablescout", "book-by-phone", {"date": "2026-11-27"})
    assert sent[0]["url"] == "https://egress.example.test/p/mesh/dining.example.test/v1/book-by-phone"
    assert sent[0]["bearer"] == "account-credential"
    assert sent[0]["body"]["idempotency_key"] == out["thread"]        # one order, one key
    assert out["ok"] and out["pending"] and out["job"] == "j1" and "do NOT claim" in out["next"]


def test_his_answers_rewrite_the_request_and_a_standing_one_is_not_asked_again(net):
    sent, answers, *_ = net
    answers.append((422, ASKS))
    out = mesh_call.call("tablescout", "book", {"date": "2026-11-27"})
    assert not out["ok"] and out["agent_asks_user"][0]["id"] == "seating.any" and "hbmesh reply" in out["next"]
    back = mesh_call.reply(out["thread"], [("seating.any", 0, None)])
    assert back["ok"] and sent[-1]["body"]["seating"] == {"any": True} and sent[-1]["body"]["date"] == "2026-11-27"
    answers.extend([(422, ASKS), (200, {"status": "CONFIRMED_API"})])
    again = mesh_call.call("tablescout", "book", {"date": "2026-12-04"})
    assert again["ok"] and again["applied_his_standing_answers"] == ["seating.any: Cualquier mesa"]
    assert sent[-1]["body"]["seating"] == {"any": True}


def test_a_refusal_to_repeat_is_said_and_never_retried_and_a_charge_never_paid(net):
    sent, answers, *_ = net
    answers.append((409, {"error": "duplicate_risk"}))
    out = mesh_call.call("tablescout", "book", {})
    assert out["conflict"] and len(sent) == 1
    answers.append((402, {"x402": {}}))
    out = mesh_call.call("tablescout", "book", {})
    assert out["payment_required"] and len(sent) == 2


def test_a_skill_price_is_a_tariff_row_that_travels_with_the_lease(net):
    from nucleo.energy import meter, tariffs
    tariffs._reset_for_tests()
    try:
        assert not tariffs.has_rate("agent", "tablescout.book-by-phone")           # the engine ships no agent price
        assert meter.agent_cost_to_energy(provider="tablescout.book-by-phone") == 0
        assert tariffs.update({"agent": {"tablescout.book-by-phone": 0.5}})
        assert tariffs.has_rate("agent", "TableScout.Book-By-Phone")
        assert meter.agent_cost_to_energy(provider="tablescout.book-by-phone") == pytest.approx(
            0.5 * meter.MARGIN_MULTIPLIER / meter.EUR_PER_ENERGY_UNIT)
    finally:
        tariffs._reset_for_tests()
