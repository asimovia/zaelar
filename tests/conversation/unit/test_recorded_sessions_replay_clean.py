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


def final_batches(rep: Replay) -> list[set[str]]:
    """The interventions each run carried in its prompt — the runs that ENDED their batch (answered, silent, stopped,
    failed), not the ones substituted or fenced, whose batch went back to the queue."""
    snap = rep.store.snapshot("replay")
    iv_of = {r["id"]: r["env"]["refs"].get("intervention_id")
             for _k, r in snap.scan("inbox") + snap.scan("inbox.done")}
    batch = {p["refs"]["run"]: p["batch_envs"] for k, lab, p in rep.tel.events if k == "conv_run" and lab == "started"}
    for k, lab, p in rep.tel.events:            # a run that answered a reply waiting for his voice carried its words too
        if k == "conv_run" and lab == "command" and p.get("command") == "absorbed":
            batch[p["refs"]["run"]] = list(batch.get(p["refs"]["run"], [])) + list(p["batch_envs"])
    gave_back = {p["refs"]["run"] for k, lab, p in rep.tel.events if k == "conv_run" and lab in ("superseded", "fenced")}
    return [{iv_of.get(e) for e in envs} - {None} for run, envs in batch.items() if run not in gave_back]


def score(rep: Replay, labels: dict) -> dict:
    """The sentence reaches the model WHOLE, in one prompt — scored only where the evidence is firm. A labelled
    intervention bounded by firm boundaries (or the session's edges) must lie inside ONE final prompt (else a
    `split`); the two sides of a firm boundary must never share one (else a `fusion`). Everything at boundaries that
    are not firm is reported."""
    owner = [iv for iv, _w in rep.conv.ear.spans.all_final_words()]
    assert len(owner) == labels["tokens"], "the ear did not keep every final word of the session"
    prompts = final_batches(rep)
    firm = {k for k, s in labels["boundaries"] if s == "transcript"} | {0, labels["tokens"]}

    def together(i: int, j: int) -> bool:
        return any(owner[i] in b and owner[j] in b for b in prompts)

    def whole(a: int, b: int) -> bool:
        need = set(owner[a:b])
        return any(need <= p for p in prompts)

    spans = [tuple(x) for x in labels["interventions"]]
    return {"fusions": [k for k, s in labels["boundaries"] if s == "transcript" and together(k - 1, k)],
            "splits": [(a, b) for a, b in spans if a in firm and b in firm and not whole(a, b)],
            "not_firm_split": [(a, b) for a, b in spans if not (a in firm and b in firm) and not whole(a, b)],
            "not_firm_fused": [k for k, s in labels["boundaries"] if s != "transcript" and together(k - 1, k)]}


@pytest.mark.parametrize("name", SESSIONS)
def test_the_sentence_reaches_the_model_whole_in_one_prompt_both_ways(name, record_property):
    rep, _sig = _replay(name)
    got = score(rep, LABELS[name])
    for key, ks in got.items():
        record_property(key, len(ks))
    assert any(s == "transcript" for _k, s in LABELS[name]["boundaries"]), "a session with no firm boundary scores nothing"
    assert not got["fusions"], f"two firmly separate interventions in one prompt: {got['fusions']}"
    assert not got["splits"], f"a firmly bounded intervention never reached one prompt whole: {got['splits']}"


@pytest.mark.parametrize("name", SESSIONS)
def test_a_closed_intervention_reaches_the_prompt_within_a_second(name):
    """Within a second of its close — unless a voice was already open on its device when it closed (the voice still
    up: its successor, v3.1 §1.6 bis E2), and then within the hold's bound. These recordings carry the old pipeline's
    VAD, whose falls come late or never: what the bound costs them is what E1's short tail removes live."""
    rep, _sig = _replay(name)
    ev = rep.tel.events
    closed = [(p["t_ms"], p["refs"].get("endpoint")) for k, lab, p in ev if k == "conv_ear" and lab == "closed"]
    opened = [(p["t_ms"], p["refs"].get("endpoint")) for k, lab, p in ev if k == "conv_ear" and lab == "opened"]
    prompts = sorted(p["t_ms"] for k, lab, p in ev if k == "conv_run" and lab == "prompt")
    bound = rep.config.resume_hold_max_ms + 1000

    def reached(t, within):
        return any(t <= p <= t + within for p in prompts)

    held = {(t, ep) for t, ep in closed if (t, ep) in set(opened)}       # a voice open there as it closed
    stopped = {p["t_ms"] for k, lab, p in ev if k == "conv_inbox" and lab == "accounted" and p.get("reason") == "stopped"}
    late = [t for t, ep in closed if (t, ep) not in held and not reached(t, 1000)]
    unbounded = [t for t, ep in closed if not reached(t, bound)          # a stop pressed while it waited cancels it
                 and not any(t <= s <= t + bound for s in stopped)]
    assert closed and not late, f"{len(late)} of {len(closed)} closes waited more than 1 s for the model"
    assert not unbounded, f"{len(unbounded)} closes waited past the hold's bound"


@pytest.mark.parametrize("name", SESSIONS)
def test_the_ear_closes_only_on_the_providers_end_or_its_cap(name):
    """An eager hint never closes: every close by end of turn answers one recorded `EotHint(end)`."""
    rep, sig = _replay(name)
    ends = sum(1 for s in sig if s["sig"] == "EotHint" and s["kind"] == "end")
    by_eot = sum(1 for k, lab, p in rep.tel.events if k == "conv_ear" and lab == "closed" and p["closed_by"] == "eot")
    assert 0 < by_eot <= ends


@pytest.mark.parametrize("name", SESSIONS)
def test_the_replay_acts_and_hears_its_own_voice(name):
    """The replay's model also reads and asks for a write (every third request), so the gateway is exercised — the read
    reaches the tools, the write never does (I8); and our own voice reaches the ear as the device's playback, so a
    sentence after a line we played is new — it never amends what came before it."""
    rep, _sig = _replay(name)
    assert rep.tools.calls and "conv_effect/refused" in rep.tel.labels("conv_effect")
    assert {name for name, _a, _e in rep.tools.calls} == {"search"}
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
