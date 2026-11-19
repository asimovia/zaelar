"""P2 (node 13.20): recorded sessions, replayed as tokens through the whole manager, break no invariant, and the
ear respects every FIRM boundary of the person in both directions.

Each fixture is a real session converted to ear signals with every word a token (`fixtures/sessions/`). Each labelled
boundary carries its evidence (`labels.json` › `boundaries`): only `transcript` boundaries — the agent spoke between —
are firm; `old_prompt_only` and `none` only reproduce where the old engine cut: they are unscored — reported, never
deciding (review 2, NM4/NM5). Scored, both at zero: a FUSION — a firm boundary the ear does not
respect (two of the person's interventions glued into one) — and an unrelated SPLIT — the ear cutting where no boundary
is labelled with no `amends` chain between the pieces and no line of ours played between them. A split that amends (the
reply was out, the revision sealed, the person went on: I3) and one after a line we played (the scripted model answered
inside the person's pause: timing, which P4 measures) are counted and reported. Every intervention that closed reaches the model's prompt within one
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
#: splits after a line we played, measured 2026-11-19 with the replay speaking on a live device: only go down
AFTER_VOICE_CEILING = {"s1": 1, "s2": 1}


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
    voiced = [p["t_ms"] for k, lab, p in rep.tel.events if k == "conv_mouth" and lab == "say" and "voice" in p["channels"]]
    amends = {}
    snap = rep.store.snapshot("replay")
    for _k, row in snap.scan("inbox") + snap.scan("inbox.done"):          # archived rows too (NM2)
        body = row["env"]["body"]
        if row["kind"] in (str(EnvelopeKind.USER_UTTERANCE), str(EnvelopeKind.INTERVENTION_STATE)) and body.get("amends"):
            amends[body["intervention_id"]] = body["amends"]
    support = {k: s for k, s in labels["boundaries"]}
    cuts = [k for k in range(1, len(owner)) if owner[k] != owner[k - 1]]
    splits = [k for k in cuts if k not in support]
    closed, opened = {}, {}                  # when the ear ended the earlier piece and opened the later one
    for k, lab, p in rep.tel.events:
        if k == "conv_ear" and lab in ("closed", "incomplete"):
            closed[p["refs"]["iv"]] = p["t_ms"]
        elif k == "conv_ear" and lab == "opened":
            opened.setdefault(p["refs"]["iv"], p["t_ms"])
    spoke = {k for k in splits if any(closed.get(owner[k - 1], 0) <= t <= opened.get(owner[k], 0) for t in voiced)}
    return {"fusions": [k for k, s in support.items() if s == "transcript" and owner[k] == owner[k - 1]],
            "unrelated_splits": [k for k in splits if amends.get(owner[k]) != owner[k - 1] and k not in spoke],
            "amending_splits": [k for k in splits if amends.get(owner[k]) == owner[k - 1]],
            "after_our_voice_splits": sorted(spoke),
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
    # a split after a line we played is the scripted model's timing, not the ear's; still a ratchet: never more
    assert len(got["after_our_voice_splits"]) <= AFTER_VOICE_CEILING[name], got["after_our_voice_splits"]


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


@pytest.mark.parametrize("name", SESSIONS)
def test_the_replay_acts_and_hears_its_own_voice(name):
    """Review 2, MINOR 7 and 8: the replay's model also writes to the agenda (every third request), so the gateway's
    seal, reservation and receipt are exercised and I1/I8 have something to check; and our own voice reaches the ear as
    the device's playback, so a sentence after a line we played is new — it never amends what came before it."""
    rep, _sig = _replay(name)
    assert rep.tools.calls and "conv_effect/receipt" in rep.tel.labels("conv_effect")
    snap = rep.store.snapshot("replay")
    sealed = {k: r.get("sealed_ms") for k, r in snap.scan("interventions") + snap.scan("interventions.done")}
    voiced = [p["t_ms"] for k, lab, p in rep.tel.events if k == "conv_mouth" and lab == "say" and "voice" in p["channels"]]
    assert voiced, "the replay never spoke"
    wrong = []
    for _k, row in snap.scan("inbox") + snap.scan("inbox.done"):
        body = row["env"]["body"]
        if row["kind"] == str(EnvelopeKind.USER_UTTERANCE) and body.get("amends") and sealed.get(body["amends"]):
            if any(sealed[body["amends"]] <= t <= row["env"]["onset_ms"] for t in voiced):
                wrong.append(body["intervention_id"])
    assert not wrong, f"amends across a line we played: {wrong}"
