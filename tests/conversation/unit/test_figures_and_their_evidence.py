"""Figures and their evidence (node 13.42, v3.1 §1.10 bis — 13.6o of the test plan).

A claim against a TEXT evidence passes when its value is among the figures of that text — the host's adapter reads
them from the tool's output, both ways numbers are written; a claim against STRUCTURED evidence keeps the whole
match. A DERIVED figure cites evidence with figures of THIS reply and passes with no repair round; with the repair
switch on it spends the one round; with the door closed it is refused, as it is with no read in the reply, with
evidence that holds no figure, or with an id of another reply. A figure that does not match and a derived one in the
same reply cost one repair round, not two.
"""
from __future__ import annotations

import pytest

from conversation.config import Config
from conversation.ports import Done, ToolCall, ToolResult
from conversation.testing.fakes import evidence
from conversation.testing.scripted_model import reply
from conversation.types import Evidence
from nucleo.conversation_host.figures import figures
from tests.conversation.unit.convkit import Harness

TEXT = Evidence("ev_t1", "search", numbers=figures("cerró a 1.105,34 $ el viernes; 13 de 30 días al alza"))
EMPTY = Evidence("ev_t0", "search", numbers=figures("cerró al alza"))


def _claim(value, ev_id, **kw):
    return {"entity": "", "period": "", "metric": "", "direction": "", "value": value, "evidence_id": ev_id, **kw}


def _run(store, claims_by_round, *, evidence_=(TEXT,), config=None, read=True, earlier=()):
    """One reply: a read (or none), then the model's reply with `claims`, once per round it is asked. `earlier`:
    evidence still valid from an EARLIER reply."""
    rounds = ([[ToolCall("c1", "market_data", {"q": "w1"}), Done()]] if read else [])
    rounds += [[reply("w9", c), Done()] for c in claims_by_round]
    h = Harness(store, config=config, grace=False)
    h.model.default = lambda ids: rounds[min(len(h.model.calls) - 1, len(rounds) - 1)]
    h.tools.answers["market_data"] = ToolResult("ok", {"text": "w"}, tuple(evidence_))
    if earlier:
        from conversation.manager import claims as CL
        with h.conv.store.tx(h.conv.lease) as tx:
            CL.remember(tx, tuple(earlier), 0, 10 ** 12)
    h.utter([(["w1"], 0)])
    return [o.text for o in h.mouth.orders], [lab for lab, _ in h.closes()], len(h.model.calls)


@pytest.mark.parametrize("value", [1105.34, 13.0])
def test_a_figure_in_the_text_it_cites_passes(store, value):
    said, closes, calls = _run(store, [[_claim(value, "ev_t1")]])
    assert said == ["w9"] and closes == ["answered"] and calls == 2


def test_a_figure_absent_from_the_text_repairs_once_then_is_silent(store):
    said, closes, calls = _run(store, [[_claim(999.0, "ev_t1")], [_claim(999.0, "ev_t1")]])
    assert said == [] and closes == ["silent"] and calls == 3


@pytest.mark.parametrize("text,value", [("1,234.5 USD", 1234.5), ("1.234,5 €", 1234.5), ("12 345 personas", 12345.0),
                                        ("−4,2 grados", -4.2)])
def test_the_same_figure_in_another_format_is_read(text, value):
    assert value in figures(text)


STRUCT = evidence("ev_s1", "ACME", "q3", "up_days", "up", 18)
OK = {"entity": "ACME", "period": "q3", "metric": "up_days", "direction": "up", "value": 18, "evidence_id": "ev_s1"}


def test_structured_evidence_matches_whole(store):
    said, _c, _n = _run(store, [[OK]], evidence_=(STRUCT,))
    assert said == ["w9"]


def test_structured_evidence_refuses_the_right_number_about_the_wrong_thing(store):
    wrong = {**OK, "entity": "OTHER"}
    said, closes, _n = _run(store, [[wrong], [wrong]], evidence_=(STRUCT,))
    assert said == [] and closes == ["silent"]


def test_a_derived_figure_citing_this_reply_passes_with_no_repair(store):
    said, closes, calls = _run(store, [[_claim(43.3, "ev_t1", derived=True)]])
    assert said == ["w9"] and calls == 2


def test_with_the_repair_switch_on_a_derived_figure_spends_the_one_round(store):
    c = [_claim(43.3, "ev_t1", derived=True)]
    said, closes, calls = _run(store, [c, c], config=Config(derived_claims_repair=True))
    assert said == ["w9"] and calls == 3


@pytest.mark.parametrize("case", ["closed", "no_read", "no_figures", "another_reply"])
def test_a_derived_figure_is_refused_outside_its_bounds(store, case):
    cfg = Config(derived_claims_open=False) if case == "closed" else None
    ev_id = {"no_figures": "ev_t0", "another_reply": "ev_old"}.get(case, "ev_t1")
    claim = [_claim(43.3, ev_id, derived=True)]
    h_ev = (EMPTY,) if case == "no_figures" else (TEXT,)
    old = (Evidence("ev_old", "search", numbers=(43.3,)),) if case == "another_reply" else ()
    said, closes, _n = _run(store, [claim, claim], evidence_=h_ev, config=cfg, read=case != "no_read", earlier=old)
    assert said == [] and closes == ["silent"]


def test_a_mismatch_and_a_derived_figure_cost_one_round(store):
    first = [_claim(999.0, "ev_t1"), _claim(43.3, "ev_t1", derived=True)]
    fixed = [_claim(1105.34, "ev_t1"), _claim(43.3, "ev_t1", derived=True)]
    said, _c, calls = _run(store, [first, fixed], config=Config(derived_claims_repair=True))
    assert said == ["w9"] and calls == 3


def test_derived_figures_are_counted_apart(store):
    h = Harness(store, script={"iv_000001": [[ToolCall("c1", "market_data", {}), Done()],
                                             [reply("w9", [_claim(43.3, "ev_t1", derived=True)]), Done()]]},
                grace=False)
    h.tools.answers["market_data"] = ToolResult("ok", {}, (TEXT,))
    h.utter([(["w1"], 0)])
    assert [p.get("derived") for k, lab, p in h.tel.events if k == "conv_run" and lab == "command"] == [1]
