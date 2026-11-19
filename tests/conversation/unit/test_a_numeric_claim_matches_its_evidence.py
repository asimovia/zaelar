"""D9: a numeric claim about data is published only when it matches its evidence — whole (node 13.18).

The claim (entity, period, metric, direction, value) must match what a tool of this run, or of an earlier run still
valid, returned. «18 up, 12 down» with the right numbers and the wrong direction does not pass; a claim citing
evidence that never came, or that expired, does not pass; a blocked reply is not said and the request ends in a
deliberate silence with its reason. The checker never chooses a tool: what tools ran is what the model asked for.
"""
from __future__ import annotations

from conversation.config import Config
from conversation.manager.claims import Claim, check
from conversation.ports import Done, ToolCall, ToolResult
from conversation.testing.fakes import evidence
from conversation.testing.scripted_model import reply
from tests.conversation.unit.convkit import Harness

EV = evidence("ev1", "ACME", "fridays-2026-q3", "sessions_up", "up", 18)


def _claim(**kw) -> dict:
    base = {"entity": "ACME", "period": "fridays-2026-q3", "metric": "sessions_up", "direction": "up", "value": 18,
            "evidence_id": "ev1"}
    return {**base, **kw}


def test_the_whole_claim_must_match_not_only_the_number():
    ok = Claim.from_args(_claim())
    assert check([ok], {"ev1": EV}) == []
    for field_name, wrong in (("direction", "down"), ("entity", "OTHER"), ("period", "mondays-2026-q3"),
                              ("metric", "sessions_down"), ("value", 12)):
        bad = Claim.from_args(_claim(**{field_name: wrong}))
        assert [why for _c, why in check([bad], {"ev1": EV})] == [field_name]
    assert [why for _c, why in check([Claim.from_args(_claim(evidence_id="ev9"))], {"ev1": EV})] == ["no_evidence"]


def _run(store, claim: dict, *, earlier: bool = False, ttl: int = 600_000):
    h = Harness(store, config=Config(evidence_ttl_ms=ttl))
    h.tools.answers["market_data"] = ToolResult("ok", data={"n": 18}, evidence=(EV,))
    plan = []
    if earlier:
        plan.append([ToolCall("c0", "market_data", {"q": "w1"}), Done()])
        plan.append([reply("w0"), Done()])
        plan.append([reply("w8", [claim]), Done()])
    else:
        plan.append([ToolCall("c1", "market_data", {"q": "w1"}), Done()])
        plan.append([reply("w8", [claim]), Done()])
        plan.append([reply("w8", [claim]), Done()])                    # the repair round, if it is asked for
    h.model.default = lambda ids: plan.pop(0)
    h.typed("w1", 1)
    h.at(1000).pump()
    if earlier:
        h.at(h.clock.mono + 2000)
        h.typed("w2", h.clock.mono)
        h.at(h.clock.mono + 1000).pump()
    return h


def test_a_matching_claim_is_said(store):
    h = _run(store, _claim())
    assert [o.text for o in h.mouth.orders] == ["w8"] and [lab for lab, _ in h.closes()] == ["answered"]


def test_a_wrong_direction_with_the_right_number_is_not_said(store):
    h = _run(store, _claim(direction="down"))
    assert "w8" not in [o.text for o in h.mouth.orders]
    assert ("silent", "claims_unverified") in [(lab, p.get("reason")) for lab, p in h.closes()]
    assert [c[0] for c in h.tools.calls] == ["market_data"]


def test_evidence_of_an_earlier_run_counts_while_it_is_valid(store):
    h = _run(store, _claim(), earlier=True)
    assert [o.text for o in h.mouth.orders] == ["w0", "w8"]


def test_expired_evidence_does_not(store):
    h = _run(store, _claim(), earlier=True, ttl=1000)
    assert [o.text for o in h.mouth.orders] == ["w0"]


def test_m6_a_wrong_claim_gets_one_repair_round_with_its_reason(store):
    h = Harness(store)
    h.tools.answers["market_data"] = ToolResult("ok", data={"n": 18}, evidence=(EV,))
    plan = [[ToolCall("c1", "market_data", {"q": "w1"}), Done()], [reply("w8", [_claim(direction="down")]), Done()],
            [reply("w7", [_claim()]), Done()]]
    h.model.default = lambda ids: plan.pop(0)
    h.typed("w1", 1)
    h.at(1000).pump()
    assert [o.text for o in h.mouth.orders] == ["w7"] and [lab for lab, _ in h.closes()] == ["answered"]
    repair = h.model.calls[-1].prompt.steps[-1]
    assert repair[0].name == "claims_check" and repair[1].data == {"mismatch": ["direction"]}
