"""P2 (node 13.20): recorded sessions, replayed as tokens through the whole manager, break no invariant, and the
ear respects every FIRM boundary of the person in both directions.

Each fixture is a real session converted to ear signals with every word a token (`fixtures/sessions/`). Each labelled
boundary carries its evidence (`labels.json` › `boundaries`): only `transcript` boundaries — the agent spoke between —
are firm; `old_prompt_only` and `none` only reproduce where the old engine cut, and are reported, never scored, until
the operator reviews them (review 2, NM4/NM5). Scored, both at zero: a FUSION — a firm boundary the ear does not
respect (two of the person's interventions glued into one) — and an unrelated SPLIT — the ear cutting where no boundary
is labelled with no `amends` chain between the pieces. A split that amends (the reply was out, the revision sealed,
the person went on: I3) is counted and reported. Every intervention that closed reaches the model's prompt within one
second of simulated time.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from conversation.replay import Replay, load
from conversation.testing.generate import check
from conversation.types import EnvelopeKind

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "sessions"
LABELS = json.loads((FIX / "labels.json").read_text())
THINK_MS = 1000
SESSIONS = sorted(k for k in LABELS if not k.startswith("_"))


def _replay(name: str) -> tuple[Replay, list[dict]]:
    sig = load((FIX / f"{name}.jsonl").read_text().splitlines())
    return Replay(sig, think_ms=THINK_MS).run(), sig


@pytest.mark.parametrize("name", SESSIONS)
def test_the_session_replays_with_no_invariant_broken(name):
    rep, _sig = _replay(name)
    assert check(rep.as_case()) == []
    assert rep.tel.labels("conv_run").count("conv_run/started") >= 3


def score(rep: Replay, labels: dict) -> dict:
    """Fusions at firm boundaries, splits where nothing is labelled (unrelated or amending), and the disagreements at
    boundaries that are not firm — the numbers P2 publishes."""
    owner = [iv for iv, _w in rep.conv.ear.spans.all_final_words()]
    assert len(owner) == labels["tokens"], "the ear did not keep every final word of the session"
    amends = {}
    for _k, row in rep.store.snapshot("replay").scan("inbox"):
        body = row["env"]["body"]
        if row["kind"] in (str(EnvelopeKind.USER_UTTERANCE), str(EnvelopeKind.INTERVENTION_STATE)) and body.get("amends"):
            amends[body["intervention_id"]] = body["amends"]
    support = {k: s for k, s in labels["boundaries"]}
    cuts = [k for k in range(1, len(owner)) if owner[k] != owner[k - 1]]
    splits = [k for k in cuts if k not in support]
    return {"fusions": [k for k, s in support.items() if s == "transcript" and owner[k] == owner[k - 1]],
            "unrelated_splits": [k for k in splits if amends.get(owner[k]) != owner[k - 1]],
            "amending_splits": [k for k in splits if amends.get(owner[k]) == owner[k - 1]],
            "not_firm_missed": [k for k, s in support.items() if s != "transcript" and owner[k] == owner[k - 1]]}


@pytest.mark.parametrize("name", SESSIONS)
def test_the_ear_respects_every_firm_boundary_in_both_directions(name, record_property):
    rep, _sig = _replay(name)
    got = score(rep, LABELS[name])
    for key, ks in got.items():
        record_property(key, len(ks))
    assert any(s == "transcript" for _k, s in LABELS[name]["boundaries"]), "a session with no firm boundary scores nothing"
    assert not got["fusions"], f"firm boundaries glued into one intervention: {got['fusions']}"
    assert not got["unrelated_splits"], f"the ear cut where nothing is labelled, with no amends: {got['unrelated_splits']}"


@pytest.mark.parametrize("name", SESSIONS)
def test_a_closed_intervention_reaches_the_prompt_within_a_second(name):
    rep, _sig = _replay(name)
    closed = [p["t_ms"] for k, lab, p in rep.tel.events if k == "conv_ear" and lab == "closed"]
    prompts = sorted(p["t_ms"] for k, lab, p in rep.tel.events if k == "conv_run" and lab == "prompt")
    late = [t for t in closed if not any(t <= p <= t + 1000 for p in prompts)]
    assert closed and not late, f"{len(late)} of {len(closed)} closes waited more than 1 s for the model"


@pytest.mark.parametrize("name", SESSIONS)
def test_the_ear_closes_only_on_the_providers_end_or_its_cap(name):
    """An eager hint never closes: every close by end of turn answers one recorded `EotHint(end)`."""
    rep, sig = _replay(name)
    ends = sum(1 for s in sig if s["sig"] == "EotHint" and s["kind"] == "end")
    by_eot = sum(1 for k, lab, p in rep.tel.events if k == "conv_ear" and lab == "closed" and p["closed_by"] == "eot")
    assert 0 < by_eot <= ends
