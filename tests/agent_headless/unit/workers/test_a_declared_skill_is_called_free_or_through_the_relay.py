"""`hbmesh call <agent> <skill>`: ONE declared skill, free direct or priced through the relay, one order at a time.

Measured before: `serve` put every errand to an agent's FIRST declared skill (a booking errand came back as a search).
Now the worker calls the skill it chose from the card (`nucleo/mesh_call`), and:

  · a free skill goes direct; a priced one ONLY through the deployment's relay (`<egress>/p/mesh/<host><path>`, the
    account's egress credential) and only when the account can price it (an `agent` tariff row) — refused before
    anything leaves otherwise (self-host, or no price);
  · the request key is the ENGINE's, derived from the order — never the body's, never the card's example — so a retry
    of an order whose answer never came carries the same key, and two orders never share one (audit P1-1);
  · while an order has a step whose outcome is unknown, no OTHER skill of the agent is called for it (P2-8);
  · an agent's questions come back as `agent_asks_user` (they are put on his row, see the job test), a standing answer
    of his is applied without asking; `409` is said and never retried; `402` is never paid; a served skill teaches
    the playbook route; a skill's price is a tariff row that travels with the lease.

The send goes through the real `mesh_agents.ask` (only `_post` is replaced, with its full signature).

Disarm: make `route` answer RELAY for a priced skill on self-host → red; keep the body's key → red.
"""
from __future__ import annotations

import pytest

from nucleo import mesh_agents, mesh_call

EP = "https://dining.example.test"
CARD = {"skills": [
    {"id": "search", "pricing": {"amount": 0, "currency": "free"}},
    {"id": "book", "pricing": {"amount": 0, "currency": "free"}},
    {"id": "book-by-phone", "pricing": {"unit": "booking", "amount": 12300000, "currency": "lamports"},
     "examples": ['{"restaurant": {}, "idempotency_key": "order-123"}']}],
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

    def _post(url, body, timeout=0, bearer=None, headers=None):
        sent.append({"url": url, "body": body, "bearer": bearer})
        return answers.pop(0) if answers else (200, {"status": "CONFIRMED"})
    monkeypatch.setattr(mesh_agents, "_post", _post)
    learned = []
    from nucleo import routes
    monkeypatch.setattr(routes, "plan", lambda errand, locale=None: routes.store.Plan(domain="restaurant"))
    monkeypatch.setattr(routes, "learn", lambda domain, ch, **k: learned.append((domain, ch, k.get("target"))))
    yield sent, answers, learned, monkeypatch
    rules._reset_for_tests()


def _mediated(monkeypatch, *, priced: bool):
    from nucleo.energy import egress, lease_gate, tariffs
    monkeypatch.setattr(egress, "mediated", lambda: True)
    monkeypatch.setenv("ZAELAR_GATEWAY_URL", "https://egress.example.test/v1")
    monkeypatch.setenv("CONTROL_PLANE_SERVICE_TOKEN", "account-credential")
    monkeypatch.setattr(tariffs, "has_rate", lambda fam, key: priced and key == "dining-agent.book-by-phone")
    monkeypatch.setattr(lease_gate, "check", lambda kind="": True)


def test_the_chosen_free_skill_is_called_direct_and_teaches_its_route(net):
    sent, _answers, learned, _mp = net
    out = mesh_call.call("dining-agent", "book", {"date": "2026-11-27", "idempotency_key": "order-123"},
                         errand="reservar mesa")
    assert out["ok"] and sent[0]["url"] == f"{EP}/v1/book" and sent[0]["bearer"] is None
    assert sent[0]["body"] == {"date": "2026-11-27"}                      # a key the caller brought never travels
    assert learned == [("restaurant", "mesh", "dining-agent/book")]


def test_a_skill_the_card_does_not_declare_is_never_called(net):
    sent, *_ = net
    out = mesh_call.call("dining-agent", "cancel", {}, errand="x")
    assert not out["ok"] and not sent and [s["id"] for s in out["skills"]] == ["search", "book", "book-by-phone"]


def test_a_priced_skill_is_refused_on_self_host_and_without_a_price_before_anything_leaves(net):
    sent, _a, _l, mp = net
    assert mesh_call.call("dining-agent", "book-by-phone", {"date": "2026-11-27"}, errand="x")["priced"]
    _mediated(mp, priced=False)
    assert "cannot be charged" in mesh_call.call("dining-agent", "book-by-phone", {}, errand="x")["reason"]
    assert not sent


def test_a_priced_skill_goes_through_the_relay_with_the_engines_own_key(net):
    sent, answers, _l, mp = net
    _mediated(mp, priced=True)
    answers.append((202, {"jobId": "j1", "poll": "/v1/jobs/j1", "jobToken": "jt"}))
    out = mesh_call.call("dining-agent", "book-by-phone", {"date": "2026-11-27", "idempotency_key": "order-123"},
                         errand="x", task_id="41")
    assert sent[0]["url"] == "https://egress.example.test/p/mesh/dining.example.test/v1/book-by-phone"
    assert sent[0]["bearer"] == "account-credential"
    key = sent[0]["body"]["idempotency_key"]
    assert key != "order-123" and len(key) == 24                          # never the body's, never the card's
    assert out["pending"] and out["job"] == "j1" and "jt" not in str(out)  # the job's token never reaches the worker


def test_a_retry_of_an_unanswered_order_carries_its_key_and_another_skill_waits(net):
    sent, answers, _l, mp = net
    _mediated(mp, priced=True)
    answers.append((0, {"transport": "timeout"}))
    first = mesh_call.call("dining-agent", "book-by-phone", {"date": "2026-11-27"}, errand="x", task_id="41")
    assert not first["ok"] and "same key" in first["reason"]
    answers.append((200, {"jobId": "j1", "poll": "/v1/jobs/j1", "duplicate": True}))   # the agent's answer to a retry
    again = mesh_call.call("dining-agent", "book-by-phone", {"date": "2026-11-27"}, errand="x", task_id="41")
    assert sent[0]["body"]["idempotency_key"] == sent[1]["body"]["idempotency_key"]
    assert again["pending"] and again["job"] == "j1" and again["thread"] == first["thread"]   # a job, not a result
    other = mesh_call.call("dining-agent", "book", {"date": "2026-11-27"}, errand="x", task_id="41")
    assert other["duplicate"] and len(sent) == 2                          # not retried blindly on another channel
    mesh_call.call("dining-agent", "book-by-phone", {"date": "2026-11-28"}, errand="x", task_id="42")
    assert sent[2]["body"]["idempotency_key"] != sent[0]["body"]["idempotency_key"]   # another order, another key


def test_an_agent_that_asks_is_heard_and_his_standing_answer_is_not_asked_again(net):
    sent, answers, *_ = net
    answers.append((422, ASKS))
    out = mesh_call.call("dining-agent", "book", {"date": "2026-11-27"}, errand="x")
    assert not out["ok"] and out["agent_asks_user"] == ["¿Alguna mesa imprescindible?"]
    from nucleo import mesh_dialog
    q = mesh_dialog.questions_in(ASKS)[0]
    assert mesh_dialog.remember("dining-agent", "book", q, 0)
    answers.extend([(422, ASKS), (200, {"status": "CONFIRMED"})])
    again = mesh_call.call("dining-agent", "book", {"date": "2026-12-04"}, errand="x")
    assert again["ok"] and again["applied_his_standing_answers"] == ["seating.any: Cualquier mesa"]
    assert sent[-1]["body"]["seating"] == {"any": True}


def test_a_refusal_is_said_and_never_retried_and_a_charge_never_paid(net):
    sent, answers, *_ = net
    answers.append((409, {"error": "duplicate_risk"}))
    assert mesh_call.call("dining-agent", "book", {}, errand="x")["conflict"] and len(sent) == 1
    answers.append((402, {"x402": {}}))
    assert mesh_call.call("dining-agent", "book", {"a": 1}, errand="x")["payment_required"] and len(sent) == 2


def test_a_skill_price_is_a_tariff_row_that_travels_with_the_lease(net):
    from nucleo.energy import meter, tariffs
    tariffs._reset_for_tests()
    try:
        assert not tariffs.has_rate("agent", "dining-agent.book-by-phone")  # the engine ships no agent price
        assert meter.agent_cost_to_energy(provider="dining-agent.book-by-phone") == 0
        assert tariffs.update({"agent": {"dining-agent.book-by-phone": 0.25}})
        assert tariffs.has_rate("agent", "Dining-Agent.Book-By-Phone")
        assert meter.agent_cost_to_energy(provider="dining-agent.book-by-phone") == pytest.approx(
            0.25 * meter.MARGIN_MULTIPLIER / meter.EUR_PER_ENERGY_UNIT)
    finally:
        tariffs._reset_for_tests()


def test_a_read_that_got_no_answer_blocks_nothing_and_an_unkeyed_silence_is_never_called_safe(net):
    sent, answers, *_ = net
    answers.append((0, {"transport": "timeout"}))
    out = mesh_call.call("dining-agent", "search", {"city": "Madrid"}, errand="x", task_id="41")
    assert "do not repeat it" in out["reason"]                            # no key: its outcome is unknown, not «safe»
    assert mesh_call.call("dining-agent", "book", {"date": "2026-11-27"}, errand="x", task_id="41")["ok"]
    assert len(sent) == 2
