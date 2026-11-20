"""A failed run of typed entries is answered in place, and a derived figure carries what it rests on (node 13.85,
V2-941).

A provider that fails mid-run used to leave a typed request with a 🔔 notice on the wall and an empty answer: the line
was OWED, and with no voice of the manager it went its usual ways. On a batch of typed entries the language's line is
now the request's own answer — sealed, said once on the text channel, closed `recovered` — and nothing is owed. With
his voice in the batch, or no line in the pack, it is owed as before (`test_every_request_closes_once`).

The live suite's first T1-en reply was blocked by two `derived` claims with no `op`: the order's schema makes a claim
EITHER a figure in the evidence OR a derived one whose `op` and `operands` are required, the operations being the
package's own (`claims.OPS`).
"""
from __future__ import annotations

from conversation.manager.claims import OPS
from conversation.ports import Failed
from nucleo.conversation_host import model
from tests.conversation.unit.convkit import Harness


class _Words:
    def line(self, key, near=""):
        return "w_lost" if key == "mute_lines" else ""


def _failing(h):
    h.model.default = lambda ids: [Failed("ReadError: ", "provider")]


def test_a_typed_request_whose_run_fails_hears_the_line_as_its_answer_once(store):
    h = Harness(store, grace=False)
    h.conv.words = _Words()
    _failing(h)
    h.typed("w1", 0)
    h.settle(2000)
    assert [(o.text, tuple(sorted(o.channels))) for o in h.mouth.orders] == [("w_lost", ("text",))]
    assert [(lab, p["reason"]) for lab, p in h.closes()] == [("recovered", "provider:ReadError: ")]
    assert h.owed.rows == {}                                                       # answered: nothing owed
    ended = [p for k, lab, p in h.tel.events if k == "conv_run" and lab == "ended"]
    assert [(p["outcome"], p["said"]) for p in ended] == [("failed", True)]


def test_his_voice_in_the_batch_keeps_the_line_owed(store):
    h = Harness(store, grace=False)
    h.conv.words = _Words()
    _failing(h)
    h.utter([(["w1"], 0)])
    assert "conv:failed:r_iv_000001" in h.owed.rows
    assert all(o.text != "w_lost" for o in h.mouth.orders)


def test_with_no_line_in_the_pack_a_typed_failure_is_owed(store):
    h = Harness(store, grace=False)
    _failing(h)
    h.typed("w1", 0)
    h.settle(2000)
    assert list(h.owed.rows) == ["conv:failed:r_iv_000001"]


def test_a_derived_claim_requires_its_operation_and_operands():
    items = model.ORDERS["reply"]["properties"]["claims"]["items"]["anyOf"]
    fact, derived = items
    assert {"op", "operands", "derived"} <= set(derived["required"]) and derived["properties"]["derived"]["enum"] == \
        [True]
    assert fact["properties"]["derived"]["enum"] == [False] and "op" not in fact["properties"]
    assert set(derived["properties"]["op"]["enum"]) == set(OPS) and derived["properties"]["operands"]["minItems"] == 1
