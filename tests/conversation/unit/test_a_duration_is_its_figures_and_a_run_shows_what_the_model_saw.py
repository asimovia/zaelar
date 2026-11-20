"""A duration is its figures in every unit, a derived result may be said rounded, figures that fail twice get the honest
line's second wording, and a run shows what the model saw and who answered (node 13.108, V2-941, v3.1 B7l — «¿Y en
avión?» failing every run; the tester's observability gap).

  · «1 h 20 min» in a source is also 80 minutes and 1.33 hours: the host reads a figure, then a word the language
    packs name as a unit (`duration_units`, every pack: a source is not in his language) — characters, no table here;
  · a derived result is matched as a person says it, rounded too (a mean of 1.3 and 1.4 said «1.4»);
  · when the honest line was our last answer and the figures fail again, the pack's second wording is said
    (`unverified_fact_alt`) — never «say it again» for a clear question; the failure line stays for real failures;
  · `model_done` and every close name the model and the provider that answered: a relay is visible;
  · `input` carries each entry's facts as INPUT writes them (id, channel, time, coverage, «cut off»); `prompt` carries
    the composed prompt — NOW, STATE, OPEN, the conversation and INPUT in full, the shared prefix by its hash.
"""
from __future__ import annotations

from conversation.ear import signals as S
from conversation.manager.claims import Claim, check
from conversation.ports import Done, ToolCall, ToolResult
from conversation.testing.scripted_model import reply
from conversation.types import Evidence
from nucleo.conversation_host.figures import durations, figures
from tests.conversation.unit.convkit import Harness

#: a flight-time source as the tester's search returned it: its figures were 1, 1.3, 1.4, 20, 25, 10, 50, 55, 65…
SOURCE = "Vuelo directo Madrid–Lisboa: 1 h 20 min (unos 1,3 h); con escala 1 hora y 25 minutos; embarque 10 min."


def _c(value, **kw):
    return Claim.from_args({"entity": "", "period": "", "metric": "", "direction": "", "value": value,
                            "evidence_id": "ev", **kw})


def test_a_duration_is_also_itself_in_the_other_units_in_either_language():
    assert {80.0, 1.333333, 85.0, 1.416667} <= set(durations(SOURCE))
    assert {90.0, 1.5} <= set(durations("about 1.5 hours")) and 85.0 in durations("1 hour 25 minutes")
    assert durations("3 semanas y 2 sesiones") == ()                     # a figure and a word: not every word a unit


def test_the_runs_refused_flight_times_now_match():
    ev = {"ev": Evidence("ev", "search", numbers=figures(SOURCE))}
    assert check([_c(80.0)], ev) == [] and check([_c(1.33)], ev) == []  # «80 minutos», «1,33 horas»
    assert check([_c(95.0)], ev) != []                                   # a time the source does not hold


def test_a_derived_result_said_rounded_matches_and_a_wrong_one_does_not():
    ev = {"ev": Evidence("ev", "search", numbers=(1.3, 1.4))}
    mean = {"derived": True, "op": "mean", "operands": [1.3, 1.4]}
    assert check([_c(1.4, **mean)], ev) == [] and check([_c(1.35, **mean)], ev) == []
    assert check([_c(1.6, **mean)], ev) != []


class _Words:
    def __init__(self, alt=True):
        self.lines = {"mute_lines": "w_lost", "unverified_fact": "w_honest"}
        if alt:
            self.lines["unverified_fact_alt"] = "w_honest_alt"

    def line(self, key, near=""):
        return self.lines.get(key, "")


def _twice(store, alt=True):
    bad = [{"entity": "", "period": "", "metric": "", "direction": "", "value": 999.0, "evidence_id": "ev_t"}]
    rounds = [[ToolCall("c1", "market_data", {}), Done()], [reply("w9 999", bad), Done()]]
    h = Harness(store, grace=False)
    h.conv.words = _Words(alt)
    h.tools.answers["market_data"] = ToolResult("ok", {}, (Evidence("ev_t", "search", numbers=(1.0,)),))
    h.model.default = lambda ids: rounds[min(len(h.model.calls) - 1 - h.n0, 1)]
    h.n0 = 0
    h.typed("w1", 0)
    h.settle(2000)
    h.n0 = len(h.model.calls)
    h.typed("w2", 20_000)
    h.settle(30_000)
    return h


def test_figures_that_fail_twice_get_the_second_honest_wording_never_say_it_again(store):
    h = _twice(store)
    assert [o.text for o in h.mouth.orders] == ["w_honest", "w_honest_alt"]
    assert [lab for lab, _ in h.closes()] == ["answered", "answered"]
    rows = [row for _k, row in h.store.view(h.conv.account).recent("says", 4)]
    assert "unverified_fact_alt" in [row.get("origin") for row in rows]


def test_a_pack_without_the_second_wording_keeps_the_failure_line(store):
    h = _twice(store, alt=False)
    assert [o.text for o in h.mouth.orders] == ["w_honest", "w_lost"]


def test_the_model_and_provider_that_answered_are_on_model_done_and_the_close(store):
    h = Harness(store, grace=False)
    h.model.default = lambda ids: [Done({"model": "w_m2", "provider": "w_p2"}), reply("w9")]   # the port says Done first
    h.typed("w1", 0)
    h.settle(2000)
    done = [p for k, lab, p in h.tel.events if lab == "model_done"]
    assert [(p["model"], p["provider"]) for p in done] == [("w_m2", "w_p2")]
    assert [(p["model"], p["provider"]) for _lab, p in h.closes()] == [("w_m2", "w_p2")]


def test_a_cut_piece_shows_cut_off_in_the_input_and_the_prompt_rows(store):
    h = Harness(store, grace=False)
    h.model.default = lambda ids: [reply("w9"), Done()]
    h.hear(S.VadEdge("d1", "rise", 10), S.WordSpan("d1", 1, 1, False, (("w1", 10, 150, 1.0),), (10, 150)))
    h.hear(S.LinkGap("d1", 2000))                                          # the line lost the rest of it
    h.settle(10_000)
    entries = [p["entries"] for k, lab, p in h.tel.events if lab == "input"][0]
    assert [(e["iv"], e["tag"], e["coverage"]) for e in entries] == [("iv_000001", "cut off", "incomplete")]
    prompt = [p for k, lab, p in h.tel.events if lab == "prompt"][0]
    assert "cut off" in prompt["input"] and prompt["input"].startswith("INPUT") and prompt["state"].startswith("NOW")
    assert len(prompt["prefix_hash"]) == 12 and "conversation" in prompt
