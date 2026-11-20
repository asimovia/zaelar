"""Every rule of the test plan (R1–R19) goes red on a record that breaks it, green on one that does not, and INFRA
when it evaluates nothing or lacks its data (plan §2.4) — so a renamed field can never read as a pass."""
from __future__ import annotations

import copy
import json

import pytest

from tests.conversation.tools import verdicts as V


def ev(k, lab, t, /, **kw):
    refs = kw.pop("refs", {})
    return (k, lab, {"t_ms": t, "refs": refs, "trace": kw.pop("trace", "iv_1"), **kw})


def base() -> dict:
    """One clean conversation: a thought typed in two pieces, answered once by a run that read the web."""
    return {
        "thoughts": [{"id": 1, "pieces": ["how much is gold", "per ounce today"], "start_ms": 1000, "end_ms": 2000,
                      "lang": "en", "expect": {"search"}, "forbid": {"agenda"}, "act_refused": False,
                      "needs_answer": True, "reqs": ["r_iv_1"], "refers_to": [], "foreign": ["did you feed the cat"]},
                     {"id": 2, "pieces": ["and silver"], "start_ms": 6000, "end_ms": 6500, "lang": "en",
                      "expect": {"search"}, "forbid": set(), "act_refused": False, "needs_answer": True,
                      "reqs": ["r_iv_2"], "refers_to": [1], "foreign": []}],
        "events": [
            ev("conv_inbox", "accepted", 1000, kind="user.text", refs={"env": "e1", "iv": "iv_1", "channel": "text"}),
            ev("conv_ledger", "opened", 1000, item_kind="request", refs={"req": "r_iv_1", "item": "r_iv_1"}),
            ev("conv_run", "started", 2100, batch_envs=["e1"], refs={"run": "run_1", "req": "r_iv_1"}),
            ev("conv_run", "input", 2100, text=["how much is gold per ounce today"], refs={"run": "run_1", "req": "r_iv_1"}),
            ev("conv_effect", "read", 2300, tool="web_search", refs={"run": "run_1", "req": "r_iv_1"}),
            ev("conv_mouth", "say", 3000, channels=["text"], refs={"run": "run_1", "req": "r_iv_1", "say": "s1"}),
            ev("conv_mouth", "started", 3000, refs={"run": "run_1", "req": "r_iv_1", "say": "s1"}),
            ev("conv_inbox", "accounted", 3100, outcome="told", refs={"env": "e1", "iv": "iv_1"}),
            ev("conv_close", "answered", 3100, total_ms=2100, refs={"req": "r_iv_1"}),
            ev("conv_inbox", "accepted", 6000, kind="user.text", refs={"env": "e2", "iv": "iv_2", "channel": "text"},
               trace="iv_2"),
            ev("conv_ledger", "opened", 6000, item_kind="request", refs={"req": "r_iv_2", "item": "r_iv_2"}, trace="iv_2"),
            ev("conv_run", "started", 6600, batch_envs=["e2"], refs={"run": "run_2", "req": "r_iv_2"}, trace="iv_2"),
            ev("conv_run", "input", 6600, text=["and silver"], refs={"run": "run_2", "req": "r_iv_2"}, trace="iv_2"),
            ev("conv_effect", "read", 6700, tool="web_search", refs={"run": "run_2", "req": "r_iv_2"}, trace="iv_2"),
            ev("conv_mouth", "say", 7000, channels=["text"], refs={"run": "run_2", "req": "r_iv_2", "say": "s2"},
               trace="iv_2"),
            ev("conv_mouth", "started", 7000, refs={"run": "run_2", "req": "r_iv_2", "say": "s2"}, trace="iv_2"),
            ev("conv_close", "answered", 7100, total_ms=1100, refs={"req": "r_iv_2"}, trace="iv_2"),
        ],
        "replies": {"r_iv_1": "Gold is at 2650 dollars an ounce today.", "r_iv_2": "Silver is at 31 dollars."},
        "evidence": {"r_iv_1": ["2650"], "r_iv_2": ["31"]},
        "proof": {"manager_runs": 2, "livekit_turns": 0, "old_prompts": 0, "jev_reads": 0, "generate_reply": 0},
        "exits": {"out": 0, "held": 0}, "tasks_new": 0, "drafts_new": 0,
        "notices": [{"key": "n1", "state": "spoken"}], "stops": [],
        "prompts": {"run_1": "… how much is gold per ounce today", "run_2": "… how much is gold per ounce today … and silver"},
        "family": lambda name: "search" if name == "web_search" else name,
    }


def _drop(rec, kind, label):
    rec["events"] = [e for e in rec["events"] if not (e[0] == kind and e[1] == label)]


def _add(rec, *events):
    rec["events"] = sorted(rec["events"] + list(events), key=lambda e: e[2]["t_ms"])


def _break(rule: str, rec: dict) -> dict:
    if rule == "R1":
        _add(rec, ev("conv_close", "silent", 3200, refs={"req": "r_iv_1"}))
    elif rule == "R2":
        rec["events"][3] = ev("conv_run", "input", 2100, text=["how much is gold"], refs={"run": "run_1", "req": "r_iv_1"})
    elif rule == "R3":
        _add(rec, ev("conv_mouth", "started", 1500, refs={"run": "run_0", "say": "s0"}))
    elif rule == "R4":
        _add(rec, ev("conv_inbox", "accounted", 3150, outcome="told", refs={"env": "e1", "iv": "iv_1"}))
    elif rule == "R5":
        rec["proof"]["jev_reads"] = 11
    elif rule == "R6":
        rec["drafts_new"] = 1
    elif rule == "R7":
        _drop(rec, "conv_effect", "read")
    elif rule == "R8":
        rec["replies"]["r_iv_1"] = "Gold is at 2900 dollars an ounce today."
    elif rule == "R9":
        rec["events"][3] = ev("conv_run", "input", 2100, text=["how much is gold did you feed the cat per ounce today"],
                              refs={"run": "run_1", "req": "r_iv_1"})
    elif rule == "R10":
        rec["stops"] = [3500]
        _add(rec, ev("conv_mouth", "cut", 3900, stop_to_silence_ms=400))
    elif rule == "R11":
        _add(rec, ev("conv_mouth", "say", 3050, channels=["voice"], refs={"run": "run_1", "say": "s1b"}))
    elif rule == "R12":
        for e in rec["events"]:
            if e[0] == "conv_inbox" and e[1] == "accepted":
                e[2]["onset_ms"] = {"e1": 1000, "e2": 900}[e[2]["refs"]["env"]]
        rec["events"][2][2]["batch_envs"] = ["e1", "e2"]
    elif rule == "R13":
        _add(rec, ev("conv_mouth", "say", 8000, notice_key="n1", channels=["voice", "text"], refs={"say": "s3"}),
             ev("conv_mouth", "say", 9000, notice_key="n1", channels=["voice", "text"], refs={"say": "s4"}))
    elif rule == "R14":
        _add(rec, ("conv_inbox", "accepted", {"t_ms": 9000, "refs": {"env": "e9"}, "kind": "user.text"}))
    elif rule == "R15":
        rec["replies"]["r_iv_1"] = "El oro está hoy a 2650 dólares la onza, que es lo que hay."
    elif rule == "R18":
        _add(rec, ev("conv_inbox", "accepted", 8000, kind="worker.update", refs={"env": "e7", "channel": "worker"}))
    elif rule == "R19":
        rec["prompts"]["run_2"] = "… and silver"
    return rec


GREEN = [r for r in V.RULES if r not in ("R10", "R12", "R17")]   # need data a clean record does not carry (below)


@pytest.mark.parametrize("rule", GREEN)
def test_a_clean_record_passes(rule):
    v = V.RULES[rule](base())
    assert v.status == V.PASS and v.n > 0, v


@pytest.mark.parametrize("rule", [r for r in V.RULES if r != "R17"])
def test_a_record_that_breaks_the_rule_fails_it(rule):
    v = V.RULES[rule](_break(rule, base()))
    assert v.status == V.FAIL, v


def test_zero_cases_or_missing_data_is_infra_never_a_pass():
    empty = {**base(), "events": [], "thoughts": [], "replies": {}}
    for rule in ("R1", "R2", "R3", "R4", "R7", "R9", "R10", "R14", "R15", "R18", "R19"):
        assert V.RULES[rule](copy.deepcopy(empty)).status == V.INFRA, rule
    for key, rule in (("proof", "R5"), ("exits", "R6"), ("evidence", "R8"), ("notices", "R13")):
        rec = base()
        rec[key] = None
        assert V.RULES[rule](rec).status == V.INFRA, rule
    assert V.r12_order(base()).status == V.INFRA          # no onset on the inbox events: the order cannot be read
    assert V.r17_clean_start(base()).status == V.INFRA    # no restart in the record
    assert V.r16_latency(base(), 2500, 3750).status == V.PASS
    assert V.r16_latency(base(), 1000, 1500).status == V.FAIL


def test_a_stop_answered_in_time_passes_and_a_follow_up_without_its_prompt_is_not_a_pass():
    rec = base()
    rec["stops"] = [3500]
    _add(rec, ev("conv_mouth", "cut", 3700, stop_to_silence_ms=200))
    assert V.r10_stop(rec).status == V.PASS
    rec = base()
    rec["prompts"] = None
    assert V.r19_context(rec).status == V.INFRA


def test_the_order_rule_passes_when_onsets_are_in_order():
    rec = base()
    for e in rec["events"]:
        if e[0] == "conv_inbox" and e[1] == "accepted":
            e[2]["onset_ms"] = {"e1": 1000, "e2": 6000}[e[2]["refs"]["env"]]
    assert V.r12_order(rec).status == V.PASS


def test_events_read_back_from_the_engine_keep_the_packages_clock_and_envelope_kind():
    stored = [{"kind": "conv_inbox", "label": "accepted", "corr_id": "iv_1",
               "payload": json.dumps({"t_ms": 999, "extra_t_ms": 1000, "kind": "conv_inbox", "extra_kind": "user.text",
                                      "refs": {"env": "e1"}})},
              {"kind": "brain", "label": "jev read x", "payload": "{}"}]
    (k, lab, p), = V.from_observer(stored)
    assert (k, lab, p["t_ms"], p["kind"], p["trace"]) == ("conv_inbox", "accepted", 1000, "user.text", "iv_1")
    assert V.r18_contract({"events": [(k, lab, p)]}).status == V.PASS


def test_a_label_the_manifest_calls_debatable_is_never_counted():
    """Corpus v1.2: U19-en-012's second thought expected a search; answered from general knowledge it is right. A
    debatable label is judged and shown, never counted — by the rules here and by the driver's own judge."""
    import pathlib
    from tests.conversation.tools import corpus_drive
    rec = base()
    rec["thoughts"][1]["expect"] = {"agenda"}                              # a label the run does not meet
    rec["id"] = "U99-en-001"
    assert V.r7_route(rec).status == V.FAIL
    rec["debatable"] = V.debatable({"debatable": {"U99-en-001:2": "w"}})
    got = V.r7_route(rec)
    assert got.status == V.PASS and got.n == 1                                # one thought counted, not two
    manifest = json.loads(pathlib.Path("tests/conversation/fixtures/corpus/v1/manifest.json").read_text())
    assert "U19-en-012:2" in V.debatable(manifest) and manifest["version"] == "v1.2"
    corpus = json.loads(pathlib.Path("tests/conversation/fixtures/corpus/v1/U19.en.json").read_text())
    turn = next(t for c in corpus if c["id"] == "U19-en-012" for t in c["turns"] if t["thought"] == 2)
    row = {"turn": turn,
           "answers": [{"reply": "w9", "tool_calls": [], "action": "", "flow": {"search_events": 0, "prompts": 1,
                                                                                  "jev_reads": 0}, "wall_ms": 1}]}
    conv = {"id": "U19-en-012", "class": "U19", "lang": "en", "thoughts": [row], "new_tasks": []}
    assert not corpus_drive.judge(conv)["pass"]                            # no search for a U19 search thought…
    judged = corpus_drive.judge(conv, V.debatable(manifest))
    assert judged["thoughts"][0]["debatable"] and judged["pass"]           # …listed debatable it never fails the run
