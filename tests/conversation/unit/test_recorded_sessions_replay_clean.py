"""P2 (node 13.20): recorded sessions, replayed as tokens through the whole manager, break no invariant and keep
every labelled intervention of the person whole.

Each fixture is a real session converted to ear signals with every word a token (`fixtures/sessions/`, the labels
reviewed against the original). Replayed with a scripted model that thinks a second of simulated time before it
answers, the session leaves I1–I9 clean. Every labelled intervention reaches the model WHOLE — in one intervention of
the ear — or, where the person went on only after a pause longer than the model's think window (the reply was out:
the revision sealed), it continues as a new intervention that AMENDS the earlier one (I3): never two unrelated
pieces. Every intervention that closed reaches the model's prompt within one second of simulated time.
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


@pytest.mark.parametrize("name", SESSIONS)
def test_every_labelled_intervention_comes_out_whole_or_as_an_amendment(name):
    rep, _sig = _replay(name)
    owner = [iv for iv, _w in rep.conv.ear.spans.all_final_words()]
    assert len(owner) == LABELS[name]["tokens"], "the ear did not keep every final word of the session"
    amends = {}
    for _k, row in rep.store.snapshot("replay").scan("inbox"):
        if row["kind"] == str(EnvelopeKind.USER_UTTERANCE) and row["env"]["body"].get("amends"):
            amends[row["env"]["body"]["intervention_id"]] = row["env"]["body"]["amends"]
    broken = []
    for a, b in LABELS[name]["interventions"]:
        ivs = list(dict.fromkeys(owner[a:b]))
        chained = all(amends.get(later) == earlier for earlier, later in zip(ivs, ivs[1:]))
        if len(ivs) > 1 and not chained:
            broken.append((a, b, ivs))
    assert not broken, f"labelled interventions split into unrelated pieces: {broken}"


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
