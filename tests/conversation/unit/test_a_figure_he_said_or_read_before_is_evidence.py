"""A figure rests on what is still valid: his own words, an earlier read, two reads at once, and the scale it is said in
(node 13.106, V2-941, v3.1 B7l — the final personas' «couldn't check» right after a search).

The personas found the honest line said again and again right after a search. Their refusals were the checker's, not
the model's:

  · «how many more people does Japan have than Germany» rests on TWO reads (one search each) and cites one: a derived
    figure's operands are now figures of any evidence still valid;
  · a figure said in a scale — «123.8 million» for 123,767,642 — is that figure (two significant digits at least: a
    bare «5» would match anything of its magnitude);
  · a read of an EARLIER run of this conversation, still valid, is evidence like this run's; counted
    (`evidence_earlier_run`);
  · his own words are TEXT evidence with their figures (he said «we are 3», the reply uses 3); counted
    (`evidence_his_words`). Never our earlier lines: what we said is no evidence for itself.
"""
from __future__ import annotations

from conversation.manager.claims import Claim, check
from conversation.ports import Done, ToolCall, ToolResult
from conversation.testing.scripted_model import reply
from conversation.types import Evidence
from nucleo.conversation_host import boot
from tests.conversation.unit.convkit import Harness

JAPAN = Evidence("ev_j", "search", numbers=(2026.0, 123767642.0))
GERMANY = Evidence("ev_g", "search", numbers=(2026.0, 83644258.0))


def _c(value, ev_id, **kw):
    return {"entity": "", "period": "", "metric": "", "direction": "", "value": value, "evidence_id": ev_id, **kw}


def _ok(claim, evidence):
    return check([Claim.from_args(claim)], {e.id: e for e in evidence}) == []


def test_a_derived_figure_rests_on_two_reads_said_in_millions():
    diff = _c(40.1, ["ev_j", "ev_g"], derived=True, op="difference", operands=[123.77, 83.64])
    assert _ok(diff, (JAPAN, GERMANY))                                  # the en-05 spiral, answered: it cites both
    assert not _ok(diff, (JAPAN,))                                      # Germany's figure read nowhere: refused
    one = _c(40.1, "ev_j", derived=True, op="difference", operands=[123.77, 83.64])
    assert not _ok(one, (JAPAN, GERMANY))                               # TK-3: an operand of an evidence NOT cited


def test_a_figure_said_in_a_scale_is_that_figure_and_a_bare_digit_is_not():
    assert _ok(_c(123.8, "ev_j"), (JAPAN,)) and _ok(_c(83.6, "ev_g"), (GERMANY,))
    assert not _ok(_c(124.5, "ev_j"), (JAPAN,))                         # another figure of that magnitude
    assert not _ok(_c(2, "ev_j"), (JAPAN,)) and not _ok(_c(5, "ev_g"), (Evidence("e", "s", numbers=(4987210.0,)),))


class _Words:
    def line(self, key, near=""):
        return {"mute_lines": "w_lost", "unverified_fact": "w_honest"}.get(key, "")


def _h(store, rounds, figures=True):
    h = Harness(store, grace=False)
    h.conv.words = _Words()
    if figures:
        h.conv.figures = boot.readers()["figures"]                       # the host's reader, as the boot wires it
    h.model.default = lambda ids: rounds[min(len(h.model.calls) - 1, len(rounds) - 1)]
    return h


def _commands(h, name):
    return [p.get("claims") for k, lab, p in h.tel.events if p.get("command") == name]


def test_his_own_figure_is_evidence_and_counted(store):
    h = _h(store, [[reply("w9 30", [_c(3, "iv_000001"), _c(30, "iv_000001", derived=True, op="ratio",
                                                            operands=[90, 3])]), Done()]])
    h.typed("w1 3 w2 90", 0)
    h.settle(2000)
    assert [o.text for o in h.mouth.orders] == ["w9 30"] and _commands(h, "evidence_his_words") == [2]


def test_our_own_line_is_never_evidence_for_itself(store):
    h = _h(store, [[reply("w9 7"), Done()]])
    h.typed("w1", 0)
    h.settle(2000)
    our = h.mouth.orders[0].say_id
    h.model.default = lambda ids: [reply("w8 7", [_c(7, our)]), Done()]
    h.typed("w2", 20_000)
    h.settle(30_000)
    assert [o.text for o in h.mouth.orders][-1] != "w8 7"                # refused: what we said proves nothing


def test_without_the_hosts_reader_his_words_are_not_evidence(store):
    h = _h(store, [[reply("w9 3", [_c(3, "iv_000001")]), Done()]], figures=False)
    h.typed("w1 3", 0)
    h.settle(2000)
    assert [o.text for o in h.mouth.orders] != ["w9 3"]


def test_an_earlier_reads_figure_still_valid_answers_a_follow_up(store):
    rounds = [[ToolCall("c1", "market_data", {"q": "w1"}), Done()], [reply("w9 123.8", [_c(123.8, "ev_j")]), Done()]]
    h = _h(store, rounds)
    h.tools.answers["market_data"] = ToolResult("ok", {}, (JAPAN,))
    h.typed("w1", 0)
    h.settle(2000)
    n = len(h.model.calls)
    diff = _c(40.1, ["ev_g", "ev_j"], derived=True, op="difference", operands=[123.77, 83.64])
    later = [[ToolCall("c2", "market_data", {"q": "w2"}), Done()], [reply("w8 40.1", [diff]), Done()]]
    h.model.default = lambda ids: later[min(len(h.model.calls) - n - 1, 1)]
    h.tools.answers["market_data"] = ToolResult("ok", {}, (GERMANY,))
    h.typed("w2", 20_000)
    h.settle(30_000)
    assert [o.text for o in h.mouth.orders] == ["w9 123.8", "w8 40.1"]   # Japan from the run before, Germany now


def test_mix02_a_quantity_he_gave_times_a_rate_read_before(store):
    """mix-02: «how much are 300 pounds in euros?» after a search gave 1.1936 — a product (no operation multiplied)."""
    rate = Evidence("ev_r", "search", numbers=(1.1936,))
    rounds = [[ToolCall("c1", "market_data", {"q": "w1"}), Done()], [reply("w9", [_c(1.1936, "ev_r")]), Done()]]
    h = _h(store, rounds)
    h.tools.answers["market_data"] = ToolResult("ok", {}, (rate,))
    h.typed("w1", 0)
    h.settle(2000)
    n = len(h.model.calls)
    times = _c(358.08, ["iv_000005", "ev_r"], derived=True, op="product", operands=[300, 1.1936])  # his entry + read
    h.model.default = lambda ids: [reply("w8 358.08", [times]), Done()]
    h.typed("wa 300 wb", 20_000)
    h.settle(30_000)
    assert [o.text for o in h.mouth.orders][-1] == "w8 358.08" and len(h.model.calls) == n + 1


def test_a_derived_figure_may_cite_his_entry_with_no_figure_in_digits(store):
    """«trescientas libras»: his entry holds no digit; the figure cites it, its operands read elsewhere."""
    rate = Evidence("ev_r", "search", numbers=(300.0, 1.1936))
    rounds = [[ToolCall("c1", "market_data", {"q": "w1"}), Done()],
              [reply("w9 358.08", [_c(358.08, ["iv_000001", "ev_r"], derived=True, op="product",
                                      operands=[300, 1.1936])]),
               Done()]]
    h = _h(store, rounds)
    h.tools.answers["market_data"] = ToolResult("ok", {}, (rate,))
    h.typed("wa wb", 0)                                                     # no digit in what he wrote
    h.settle(2000)
    assert [o.text for o in h.mouth.orders] == ["w9 358.08"]


def test_tk3_a_derived_result_is_never_read_in_another_scale():
    """TK-3: a derived figure's result is matched as said, rounded — never in a scale. From a pool of figures almost
    any value is some operation's result read in thousands or millions."""
    diff = {"derived": True, "op": "difference", "operands": [123767642, 83644258]}
    assert _ok(_c(40123384, ["ev_j", "ev_g"], **diff), (JAPAN, GERMANY))
    assert _ok(_c(40100000, ["ev_j", "ev_g"], **diff), (JAPAN, GERMANY))          # rounded, the same scale
    assert not _ok(_c(40.1, ["ev_j", "ev_g"], **diff), (JAPAN, GERMANY))          # «40.1» of a result in units

