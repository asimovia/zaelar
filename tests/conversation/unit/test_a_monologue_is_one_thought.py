"""A monologue is one thought, whatever the ear's cap cut (node 13.123, V2-941, plan v3.2 §4, R3 — commit 4).

The ear's cap (`intervention_max_ms`) bounds a PIECE, not his thought: past it what was heard is delivered incomplete
(`too_long`) and, with his voice still up, the next piece starts. Such a piece no longer starts a run: it waits in the
inbox for the next one to close, and they enter together — one run, one reply, said once he is done. Past
`monologue_max_ms` with his voice still open the batch runs with what there is, and its reply goes to the wall as
text, never over his voice.

Disarms seen red: a `too_long` piece running at once; the ceiling released by voice.
"""
from __future__ import annotations

from conversation.config import Config
from conversation.ear import signals as S
from conversation.ports import Done
from conversation.testing.scripted_model import reply
from tests.conversation.unit.convkit import Harness


def _monologue(h, ms, t0=10, ep="d1"):
    """He talks for `ms`, his words growing, never an end of turn: the ear's cap cuts it into pieces."""
    h.hear(S.VadEdge(ep, "rise", t0))
    for i, t in enumerate(range(t0 + 250, t0 + ms, 250)):
        toks = [f"w{j}" for j in range(1, 2 + i // 4)]
        h.hear(S.WordSpan(ep, 1, 1 + i, False, h.words(toks, t0, step=(t - t0) // max(1, len(toks))), (t0, t)),
               h.beats(t, t + 249, ep))
        h.at(t).pump()
    return t0 + ms


def _started(h):
    return [p for k, lab, p in h.tel.events if k == "conv_run" and lab == "started"]


def test_a_piece_cut_by_its_length_waits_for_the_rest_and_one_reply_answers_all(store):
    h = Harness(store, grace=False, config=Config(intervention_max_ms=3000))
    h.model.default = lambda ids: [reply("w99"), Done()]
    end = _monologue(h, 8000)
    assert any(lab == "incomplete" and p.get("reason") == "too_long" for k, lab, p in h.tel.events if k == "conv_ear")
    assert _started(h) == [] and h.mouth.orders == [], "a piece cut by its length started a run while he spoke"
    h.hear(S.VadEdge("d1", "fall", end + 10), h.beats(end, end + 300), S.EotHint("d1", "flux", "end", .9, end + 300))
    h.settle(6000)
    assert len(_started(h)) == 1 and [o.text for o in h.mouth.orders] == ["w99"]


def test_past_the_monologue_ceiling_the_reply_goes_to_the_wall(store):
    h = Harness(store, grace=False, config=Config(intervention_max_ms=3000, monologue_max_ms=7000))
    h.model.default = lambda ids: [reply("w99"), Done()]
    _monologue(h, 9000)
    assert len(_started(h)) == 1, "at the ceiling the batch runs with what there is"
    assert [(o.text, sorted(o.channels)) for o in h.mouth.orders] == [("w99", ["text"])]
