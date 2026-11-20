"""The ear against another voice and a background that keeps talking (node 13.34, v3.1 §1.6 bis).

The ear does not tell speakers apart; what it guarantees around another voice:
  E2  a provider end that lands with the voice still UP (a rise with no fall since) closes on its coverage, and the
      next intervention is born there — a voice open on that device right after the close; words of a later provider
      turn (or late words of an ended one) are the successor's, never the ended one's;
  E3  a successor that falls before `min_voice_ms` with no word was the tail of the voice that closed: discarded at once;
  E4  the publication hold applies before a run starts too: a batch waits while a voice is open on the device of its
      last entry (even one that began before that entry closed — he went on while the provider was ending);
  E5  that wait is bounded by `resume_hold_max_ms` from the close of the batch's last entry, never reset by words;
  E6  an intervention lasts at most `intervention_max_ms` from its onset: past it, what was heard is delivered
      incomplete (`too_long`), and the voice still up starts the next one.

Regressions: the tester's five scenarios streamed through the real provider, exported as token fixtures in arrival
order (`fixtures/audio3a/`, with their truth in `labels.json`), checked against the table of §1.6 bis; and the
scripted cases — the provider's end before the fall, a continuation that comes back while the watermark is still
catching up with the fall (review TA-1: no half answer), a background with words and no end, a voice open before a
run starts.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from conversation.config import Config
from conversation.ear import signals as S
from conversation.ports import Done
from conversation.replay import KEEP_TIME_MS, Replay
from conversation.testing.generate import SPEC, check
from conversation.testing.scripted_model import reply
from tests.conversation.benchmarks.audio.score import score
from tests.conversation.unit.convkit import Harness

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "audio3a"
LABELS = json.loads((FIX / "labels.json").read_text(encoding="utf-8"))["scenarios"]


TV_GOES_ON_MS = 40_000


def _signals(sid: str) -> list[dict]:
    sig = [json.loads(line) for line in (FIX / f"{sid}.jsonl").read_text(encoding="utf-8").splitlines() if line]
    if sid != "en-tv-and-cough":
        return sig
    # the TV does not stop when the recording does: the provider keeps beating and its turn keeps growing with the
    # TV's words, the VAD stays up — so «nothing open at the end» has to come from the turn's maximum, not a silence
    last = next(s for s in reversed(sig) if s["sig"] == "WordSpan")
    words, rev, t0 = list(last["words"]), last["revision"], sig[-1]["arrived_ms"]
    for i, t in enumerate(range(t0 + 240, t0 + TV_GOES_ON_MS, 240)):
        sig.append({"sig": "Watermark", "stream": "d1", "processed_through_ms": t - 200, "t_ms": t, "arrived_ms": t})
        if i % 4 == 3:
            rev += 1
            words.append([f"w{9000 + rev}", t - 400, t - 250, 0.99])
            sig.append({"sig": "WordSpan", "stream": "d1", "seq": last["seq"], "revision": rev, "final": False,
                        "window": [last["window"][0], t - 200], "words": [list(w) for w in words], "t_ms": t,
                        "arrived_ms": t})
    return sig


def _replay(sid: str) -> Replay:
    sig = _signals(sid)
    rep = Replay(sig)
    rep.queue = sig                                 # in arrival order, as delivered: no synthetic beats
    return rep.run()


def _measure(rep: Replay, labels: dict) -> dict:
    ev = rep.tel.events
    env_iv: dict = {}
    for k, _lab, p in ev:
        refs = p.get("refs") or {}
        if k == "conv_inbox" and refs.get("env") and refs.get("iv"):
            env_iv.setdefault(refs["env"], refs["iv"])
    runs = [(p["refs"]["run"], p["t_ms"], tuple(env_iv.get(e) for e in p.get("batch_envs") or []))
            for k, lab, p in ev if k == "conv_run" and lab == "started"]
    last_run: dict = {}
    for run in runs:
        for iv in run[2]:
            if iv:
                last_run[iv] = run
    spans = rep.conv.ear.spans
    units = [{"id": r[0], "end_ms": r[1], "words": [[w[0], w[1], w[2]] for iv in dict.fromkeys(r[2]) if iv
                                                    for w in spans.words(iv)]}
             for r in sorted(set(last_run.values()), key=lambda r: r[1])]
    says = [p["t_ms"] for k, lab, p in ev if k == "conv_mouth" and lab == "say"]
    opened = {p["refs"]["iv"]: p["t_ms"] for k, lab, p in ev if k == "conv_ear" and lab == "opened"}
    ended = {p["refs"]["iv"]: p["t_ms"] for k, lab, p in ev
             if k == "conv_ear" and lab in ("closed", "incomplete", "discarded")}
    return {"score": score(labels, units),
            "spoke_over": sum(1 for tr in labels["turns"] for t in says if tr["start_ms"] <= t < tr["end_ms"]),
            "longest": max((ended[iv] - opened[iv] for iv in ended if iv in opened), default=0),
            "closes": [(p["t_ms"], p["refs"]["iv"]) for k, lab, p in ev if k == "conv_ear" and lab == "closed"],
            "runs": runs, "requests": [lab for k, lab, _p in ev if k == "conv_close"]}


@pytest.mark.parametrize("sid", sorted(LABELS))
def test_the_recorded_scenarios_meet_their_targets(sid):
    """Judged against the design's frozen numbers (`SPEC`), never the configuration the replay ran with."""
    rep = _replay(sid)
    labels = dict(LABELS[sid])
    if sid == "en-tv-and-cough":
        labels["duration_ms"] += TV_GOES_ON_MS
    m = _measure(rep, labels)
    sc, was = m["score"], labels["measured"]
    assert check(rep.as_case()) == []                                       # I1–I9 on what it left
    assert not rep.conv.ear.open_ids()                                      # nothing open once the audio is over
    assert m["longest"] <= SPEC["intervention_max_ms"] + 500                 # one beat and the provider's lag
    assert sc["lost_turns"] == 0
    if sid != "en-tv-and-cough":                 # a background that never pauses: its pieces chain (R3), see below
        assert sc["unclosed_turns"] == 0 and len(sc["eot_delay_ms"]) == len(labels["turns"])
    if sid == "en-crosstalk-in-pause":           # three pieces in one prompt with the stranger's words, no cut, nothing
        assert sc["false_cuts"] == 0 and m["spoke_over"] == 0               # said over him (the stranger's words are
        assert sc["exposure"] == [1, 1] and sc["merged_with_stranger"] == 1  # the declared limit)
    elif sid == "en-tv-and-cough":
        first = labels["turns"][0]["end_ms"]     # his first question, by the label: within the hold's bound of its close
        close = min(t for t, iv in m["closes"] if any(a <= first + 700 and b >= labels["segments"][1]["start_ms"]
                                                      for _w, a, b, *_ in rep.conv.ear.spans.words(iv)))
        started = next(t for _run, t, ivs in m["runs"] if any(c == close for c, _iv in m["closes"]))
        assert started - close <= SPEC["resume_hold_max_ms"] + KEEP_TIME_MS
        # his second question sits in the TV's turn, which never pauses: the ear cuts it by its length and, with the
        # voice still up, the pieces chain (R3, plan v3.2 §4) — it reaches the model, with the TV, once the background
        # ends (or at `monologue_max_ms`, to the wall), never lost and never answered over a voice
        assert m["spoke_over"] == 0 and sc["unclosed_turns"] <= 2
        # the price of the bound (§1.6 bis, «Coste»): what he went on with sits in a background that never ends, so
        # his first question is answered without its last piece — one cut, never more
        assert sc["false_cuts"] <= 1
    elif sid == "es-cut-off-and-correction":     # the fused unit cannot be split; its delay stays bounded
        assert sc["false_cuts"] <= was["false_cuts"]
        assert all(d <= SPEC["intervention_max_ms"] for d in sc["eot_delay_ms"])
    else:                                        # the pauses and the switch: no cut, nothing said over him, and no
        assert sc["false_cuts"] == 0 and m["spoke_over"] == 0      # line before the grace of the close it answers
        closes = sorted(t for t, _iv in m["closes"])
        says = [p["t_ms"] for k, lab, p in rep.tel.events if k == "conv_mouth" and lab == "say"]
        assert all(t - max(c for c in closes if c <= t) >= SPEC["terminal_grace_ms"] for t in says), says


# ── scripted ──────────────────────────────────────────────────────────────────────────────────────────────────────

def _first_part(h: Harness, toks=("w1", "w2"), t: int = 10, seq: int = 1) -> int:
    """He says a part: rise, the words (final), beats to just past them. Returns the end of the last word."""
    h.hear(S.VadEdge("d1", "rise", t))
    ws = h.words(list(toks), t)
    end = ws[-1][2]
    h.hear(S.WordSpan("d1", seq, 1, True, ws, (ws[0][1], end)), h.beats(end, end + 100))
    return end


def test_the_providers_end_before_the_fall_costs_nothing(store):
    """E2 + E3: the end lands with the voice still up — closed on its coverage, a successor born; the fall 30 ms later
    discards it at once (no voice), and the run is not held for the cap."""
    h = Harness(store)
    end = _first_part(h)
    h.hear(S.EotHint("d1", "flux", "end", .9, end + 200))
    h.hear(S.VadEdge("d1", "fall", end + 230), h.beats(end + 240, end + 600))
    discarded = [p for k, lab, p in h.tel.events if k == "conv_ear" and lab == "discarded"]
    assert [p["reason"] for p in discarded] == ["no_voice"] and discarded[0]["t_ms"] == end + 230
    started = [p["t_ms"] for k, lab, p in h.tel.events if k == "conv_run" and lab == "started"]
    assert started and started[0] <= end + 200 + 300                     # the run starts at once; its reply, at its grace
    h.settle()
    assert [o.text for o in h.mouth.orders]


def test_another_voice_in_the_pause_travels_with_his_sentence_and_nothing_is_said_before(store):
    """E2 + E4: the provider ends a turn while the voice is still up (another voice in his pause, no fall); a successor
    opens there, the batch waits for it, and the words of the next provider turn are the successor's — one prompt, no
    line said before, no word in two interventions."""
    h = Harness(store)
    end = _first_part(h)
    h.hear(S.EotHint("d1", "flux", "end", .9, end + 200))               # no fall: the voice is still up
    assert not h.model.calls, "a run started while a voice was open on his device"
    t = end + 300
    ws = h.words(["w3", "w4", "w5"], t)
    h.hear(S.WordSpan("d1", 2, 1, True, ws, (ws[0][1], ws[-1][2])), S.VadEdge("d1", "fall", ws[-1][2] + 10),
           h.beats(ws[-1][2], ws[-1][2] + 300), S.EotHint("d1", "flux", "end", .9, ws[-1][2] + 300))
    h.settle()
    assert len(h.model.calls) == 1 and len(h.mouth.orders) == 1
    said = h.model.calls[0].prompt.input
    assert "«w1 w2»" in said and "«w3 w4 w5»" in said
    owners: dict = {}
    for iv, word in h.conv.ear.spans.final_word_ids():
        owners.setdefault(word, set()).add(iv)
    assert all(len(ivs) == 1 for ivs in owners.values())


@pytest.mark.parametrize("variant", ["late_fall", "early_fall", "caught_up"])
def test_he_goes_on_while_the_watermark_catches_up_and_no_half_answer_is_said(store, variant):
    """Review TA-1: the provider ends before the watermark passes the fall, and he goes on 28 ms later. The rise with an
    end pending is his voice going on: nothing is said while he talks, whatever the order of the fall and the beats."""
    h = Harness(store)
    state: dict = {}

    def his_words():
        if state.get("done"):
            return
        state["done"] = 1
        ws = h.words(["w3", "w4"], state["end"] + 340)
        h.hear(S.WordSpan("d1", 99, 1, False, ws, (ws[0][1], ws[-1][2])))

    h.model.script["iv_000001"] = [[his_words, reply("half"), Done()]]
    t = 10
    h.hear(S.VadEdge("d1", "rise", t))
    ws = h.words(["w1", "w2"], t)
    end = state["end"] = ws[-1][2]
    h.hear(S.WordSpan("d1", 1, 1, True, ws, (ws[0][1], end)),
           h.beats(end, end + (290 if variant == "caught_up" else 100)))
    fall = end + 550 if variant == "late_fall" else end + 10                  # the VAD's fall, stamped after its tail
    h.hear(S.VadEdge("d1", "fall", fall), S.EotHint("d1", "flux", "end", .9, end + 300))
    h.hear(S.VadEdge("d1", "rise", end + 328))                               # he goes on, 28 ms after the end
    h.hear(S.Watermark("d1", end + 568))
    assert "half" not in [o.text for o in h.mouth.orders]
    if variant == "late_fall":                   # the end was still pending: the next intervention starts AT the rise
        onsets = [p["t_onset_ms"] for k, lab, p in h.tel.events if k == "conv_ear" and lab == "onset"]
        assert end + 328 in onsets, onsets


def test_a_background_with_words_and_no_end_never_holds_a_turn_open(store):
    """E6: words keep coming, the provider never ends, the voice never falls: at `intervention_max_ms` from its onset
    what was heard goes as incomplete (`too_long`) and the next intervention starts there; none is longer."""
    cfg = Config(intervention_max_ms=9000, monologue_max_ms=20_000)
    h = Harness(store, config=cfg)
    h.hear(S.VadEdge("d1", "rise", 10))
    seq = 0
    for t in range(200, 24_000, 400):
        seq += 1
        ws = h.words([f"w{seq}"], t)
        h.hear(S.WordSpan("d1", seq, 1, True, ws, (ws[0][1], ws[-1][2])), h.beats(t, t + 399))
    too_long = [p for k, lab, p in h.tel.events if k == "conv_ear" and lab == "incomplete"]
    assert [p["reason"] for p in too_long][:2] == ["too_long", "too_long"]
    opened = {p["refs"]["iv"]: p["t_ms"] for k, lab, p in h.tel.events if k == "conv_ear" and lab == "opened"}
    assert all(p["t_ms"] - opened[p["refs"]["iv"]] <= cfg.intervention_max_ms + 400 for p in too_long)
    assert h.model.calls                       # what was heard reached the model at the monologue's ceiling (R3)
    started = [p["t_ms"] for k, lab, p in h.tel.events if k == "conv_run" and lab == "started"]
    assert min(started) - 10 >= cfg.monologue_max_ms                # never a piece of it before: the pieces chain


def test_a_turn_outlasts_the_hold_or_a_background_would_hold_every_batch():
    """The hold counts from the close of the batch's last entry; a background closes an entry every
    `intervention_max_ms`, so that must be longer than the hold or the batch would never run."""
    cfg = Config()
    assert cfg.intervention_max_ms > cfg.resume_hold_max_ms


def test_a_voice_open_before_the_run_starts_holds_it(store):
    """E4: the batch is ready but a voice is open on the device of its last entry: no run until it ends, then one."""
    h = Harness(store)
    h.live = False
    end = h.utter([(["w1", "w2"], 0)])
    h.hear(S.VadEdge("d1", "rise", end + 50))
    h.at(end + 1000).pump()
    assert not h.model.calls
    ws = h.words(["w3"], end + 60)
    h.hear(S.WordSpan("d1", 50, 1, True, ws, (ws[0][1], ws[-1][2])), S.VadEdge("d1", "fall", ws[-1][2] + 10),
           h.beats(ws[-1][2], ws[-1][2] + 300), S.EotHint("d1", "flux", "end", .9, ws[-1][2] + 300))
    h.pump()
    assert len(h.model.calls) == 1 and "«w3»" in h.model.calls[0].prompt.input
