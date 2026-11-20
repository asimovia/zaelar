"""A refused figure is restated, and the honest line is never said twice in a row (node 13.87, V2-941).

The personas' runs found the honest line («I couldn't check that…») said again and again, even right after a read.
Now a claim the checker refuses asks the model for the answer AGAIN WITHOUT the figures it cannot back — what was
found, or a question — and the honest line is said only when that fails too. When the honest line was already our last
line, one more restate is mandatory; if that fails as well it is said, counted apart (`figures_withheld_again`). Every
blocked reply records what each refused claim said and the figures its evidence holds nearest to it, so a refusal can
be judged afterwards. A text writes a fall as «down 4.98»: against a text, a figure matches whatever its sign. A reply
after an act the gateway refused is counted (`act_refused_then_reply`) — the reply goes out, flagged for the judge.
"""
from __future__ import annotations

from conversation.manager.claims import Claim, check
from conversation.ports import Done, ToolCall, ToolResult
from conversation.testing.scripted_model import reply
from conversation.types import Evidence
from tests.conversation.unit.convkit import Harness

TEXT = Evidence("ev_t", "search", numbers=(145.98, 4.98, 3.3, 150.96))
LINE = "w_honest"


class _Words:
    def line(self, key):
        return LINE if key == "unverified_fact" else ""


def _bad(value=999.0):
    return [{"entity": "", "period": "", "metric": "", "direction": "", "value": value, "evidence_id": "ev_t"}]


def _h(store, rounds):
    h = Harness(store, grace=False)
    h.conv.words = _Words()
    h.tools.answers["market_data"] = ToolResult("ok", {}, (TEXT,))
    h.model.default = lambda ids: rounds[min(len(h.model.calls) - 1, len(rounds) - 1)]
    return h


def _commands(h):
    return [p.get("command") for k, lab, p in h.tel.events if k == "conv_run" and lab == "command"]


READ = [ToolCall("c1", "market_data", {}), Done()]


def test_a_refused_figure_asks_for_the_answer_again_without_it(store):
    h = _h(store, [READ, [reply("w9 999", _bad()), Done()], [reply("w8"), Done()]])
    h.typed("w1", 0)
    h.settle(2000)
    assert [o.text for o in h.mouth.orders] == ["w8"]                         # the answer, without the figure
    repair = h.model.calls[-1].prompt.steps[-1][1].data
    assert repair["mismatch"] == ["value"] and "without them" in repair["restate"]
    assert "restated" in _commands(h) and "figures_withheld" not in _commands(h)
    blocked = next(p for k, lab, p in h.tel.events if p.get("command") == "reply_blocked")
    assert blocked["detail"][0]["value"] == 999.0 and blocked["detail"][0]["near"][0] == 150.96   # judged afterwards


def test_the_honest_line_only_when_the_restate_fails_too(store):
    h = _h(store, [READ, [reply("w9 999", _bad()), Done()]])
    h.typed("w1", 0)
    h.settle(2000)
    assert [o.text for o in h.mouth.orders] == [LINE] and "figures_withheld" in _commands(h)


def test_the_honest_line_is_never_said_twice_in_a_row(store):
    h = _h(store, [READ, [reply("w9 999", _bad()), Done()]])
    h.typed("w1", 0)
    h.settle(2000)
    assert [o.text for o in h.mouth.orders] == [LINE]
    n = len(h.model.calls)
    rounds = [READ, [reply("w9 999", _bad()), Done()], [reply("w9 999", _bad()), Done()], [reply("w7"), Done()]]
    h.model.default = lambda ids: rounds[min(len(h.model.calls) - n - 1, len(rounds) - 1)]
    h.typed("w2", 20_000)
    h.settle(30_000)
    assert [o.text for o in h.mouth.orders] == [LINE, "w7"]                    # a third round, and the answer
    assert "restate_forced" in _commands(h)


def test_when_the_forced_restate_fails_as_well_it_is_said_and_counted_apart(store):
    h = _h(store, [READ, [reply("w9 999", _bad()), Done()]])
    h.typed("w1", 0)
    h.settle(2000)
    h.typed("w2", 20_000)
    h.settle(30_000)
    assert [o.text for o in h.mouth.orders] == [LINE, LINE]
    assert _commands(h).count("restate_forced") == 1 and "figures_withheld_again" in _commands(h)


def test_against_a_text_a_figure_matches_whatever_its_sign():
    down = Claim.from_args({"value": -4.98, "evidence_id": "ev_t", "direction": "down"})
    assert check([down], {"ev_t": TEXT}) == []
    derived = Claim.from_args({"value": -3.3, "evidence_id": "ev_t", "derived": True, "op": "percent",
                               "operands": [-4.98, 150.96]})
    assert check([derived], {"ev_t": TEXT}, frozenset({"ev_t"})) == []
    assert check([Claim.from_args({"value": 4.97, "evidence_id": "ev_t"})], {"ev_t": TEXT}) == []   # rounding
    assert [w for _c, w in check([Claim.from_args({"value": 49.8, "evidence_id": "ev_t"})], {"ev_t": TEXT})] == \
        ["value"]                                                              # a figure not there stays refused


def test_a_reply_after_an_act_the_gateway_refused_is_flagged(store):
    h = _h(store, [[ToolCall("c1", "send_message", {"to": "w2", "text": "w3"}), Done()], [reply("w_done"), Done()]])
    h.typed("w1", 0)
    h.settle(2000)
    assert h.tools.calls == [] and [o.text for o in h.mouth.orders] == ["w_done"]
    flagged = [p for k, lab, p in h.tel.events if p.get("command") == "act_refused_then_reply"]
    assert [p["tools"] for p in flagged] == [["send_message"]]
