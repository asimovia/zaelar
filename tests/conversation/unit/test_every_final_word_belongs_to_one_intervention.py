"""I2: every final word of the speech-to-text belongs to exactly one intervention (node 13.3).

Revisions REPLACE a provider turn's words (they rewrite words already given, adapter doc A4); a late partial never
undoes a final; a turn without its final leaves the intervention uncovered and it ends `incomplete`, not closed; the
person going on after a close is another intervention, which amends the first and owns only its own words; a turn
that comes back after its intervention ended gives the next one only the words PAST what was delivered, and the same
final delivered again changes nothing. A word is
identified by its provider turn and its place in it, never by its text or time. Checked on fixed cases and on seeded
random revision streams.
"""
from __future__ import annotations

import random
from collections import Counter

import pytest

from conversation.ear import signals as S
from conversation.ear.spans import Spans
from tests.conversation.unit.earkit import D, INCOMPLETE, feed, span, states, utterances, words


def _assigned_once(ear) -> None:
    owners = Counter(word_id for _iv, word_id in ear.spans.final_word_ids())
    assert all(n == 1 for n in owners.values()), [k for k, n in owners.items() if n > 1]


def test_a_revision_replaces_the_words_it_rewrites():
    sp = Spans()
    sp.add(D, 1, 1, False, words("w1", "w2"), "iv1")
    sp.add(D, 1, 2, False, words("w1", "w3", "w4"), "iv1")
    sp.add(D, 1, 3, True, words("w1", "w3", "w5"), "iv1")
    assert [w[0] for w in sp.words("iv1")] == ["w1", "w3", "w5"] and sp.covered("iv1")


def test_a_late_partial_never_undoes_a_final():
    sp = Spans()
    sp.add(D, 1, 3, True, words("w1", "w2", "w3"), "iv1")
    sp.add(D, 1, 2, False, words("w1"), "iv1")
    assert [w[0] for w in sp.words("iv1")] == ["w1", "w2", "w3"] and sp.covered("iv1")


def test_a_turn_without_its_final_is_a_gap_and_the_intervention_ends_incomplete(ear):
    out = feed(ear, S.VadEdge(D, "rise", 0), span(1, 1, True, words("w1", "w2")),
               span(2, 1, False, words("w3", t0=600)), S.VadEdge(D, "fall", 900), S.EotHint(D, "flux", "end", .9, 950),
               S.Tick(950 + 2600))
    assert not utterances(out) and states(out)[-1][0] == INCOMPLETE
    assert not ear.spans.covered(ear.spans.owner(D, 1))


def test_the_person_going_on_after_a_close_is_another_intervention_that_amends_it(ear):
    out = feed(ear, span(1, 1, False, words("w1")), span(1, 2, True, words("w1", "w2")),
               S.EotHint(D, "flux", "end", .8, 500),                                    # closes after seq 1
               span(2, 1, False, words("w3", t0=1500)),                                  # the person went on
               span(2, 2, True, words("w3", "w4", t0=1500)), S.EotHint(D, "flux", "end", .8, 2000))
    first, second = utterances(out)
    assert (first.body.text, second.body.text) == ("w1 w2", "w3 w4")
    assert second.body.intervention_id != first.body.intervention_id
    assert second.body.amends == first.body.intervention_id
    _assigned_once(ear)


def test_the_same_word_at_the_same_instant_in_two_turns_is_two_words(ear):
    """Two provider turns may carry the same token at the same time: each is a word of its own (the I2 key is the
    turn and the place, never the text and the time)."""
    sp = Spans()
    sp.add(D, 1, 1, True, words("w1", t0=100), "iv1")
    sp.add(D, 2, 1, True, words("w1", t0=100), "iv1")
    ids = [w for _iv, w in sp.final_word_ids()]
    assert len(ids) == len(set(ids)) == 2


def test_seeded_revision_streams_never_put_a_word_in_two_interventions(ear):
    for seed in range(40):
        rng = random.Random(seed)
        sp = Spans()
        for seq in range(1, rng.randint(2, 6)):
            iv = f"iv{rng.randint(1, 3)}"
            n = rng.randint(1, 5)
            for rev in range(1, rng.randint(2, 5)):
                ws = words(*[f"w{seq}{i}{rng.randint(0, 2)}" for i in range(rng.randint(1, n))], t0=seq * 10_000)
                sp.add(D, seq, rev, rng.random() < .3, ws, iv)
            sp.add(D, seq, 99, True, words(*[f"w{seq}{i}" for i in range(n)], t0=seq * 10_000), iv)
            assert len(sp.words(iv)) == len({(w[0], w[1]) for w in sp.words(iv)})
        finals = sp.all_final_words()
        assert len(finals) == len({(w[0], w[1]) for _iv, w in finals}), seed


def test_minor_2_an_older_final_arriving_late_never_replaces_a_newer_final():
    sp = Spans()
    sp.add(D, 1, 5, True, words("w1", "w2", "w3"), "iv1")
    sp.add(D, 1, 3, True, words("w1", "w9"), "iv1")
    assert [w[0] for w in sp.words("iv1")] == ["w1", "w2", "w3"]


def _closed_turn(h, toks=("w1", "w2")):
    from conversation.ear import signals as S
    t = 10
    h.hear(S.VadEdge("d1", "rise", t))
    ws = h.words(list(toks), t)
    end = ws[-1][2]
    first = S.WordSpan("d1", 1, 1, True, ws, (ws[0][1], end))
    return t, end, ws, first


@pytest.mark.parametrize("revision", [1, 2])
def test_the_same_final_delivered_again_is_answered_once(store, revision):
    """Review TB-1: a re-delivered final of a turn whose intervention ended brings nothing new — no second
    intervention, no second run, no second answer — at the same revision or the next one."""
    from conversation.ear import signals as S
    from tests.conversation.unit.convkit import Harness
    h = Harness(store)
    _t, end, ws, first = _closed_turn(h)
    h.hear(first, S.VadEdge("d1", "fall", end + 10), h.beats(end, end + 300),
           S.EotHint("d1", "flux", "end", .9, end + 300))
    h.at(end + 2000)
    h.hear(S.WordSpan("d1", 1, revision, True, ws, (ws[0][1], end)))
    for k in range(1, 20):
        h.hear(S.Tick(end + 2000 + 250 * k))
    h.pump()
    assert len(h.model.calls) == 1 and len(h.mouth.orders) == 1
    assert [lab for k, lab, p in h.tel.events if k == "conv_ear" and lab == "opened"] == ["opened"]


def test_a_turn_grown_after_a_cap_close_gives_the_next_intervention_only_its_new_words(store):
    """Review TB-1: the ear closed the turn at its cap; the provider's turn then grows by a word — the next
    intervention carries that word alone, never the words already delivered."""
    from conversation.ear import signals as S
    from tests.conversation.unit.convkit import Harness
    h = Harness(store)
    t, end, ws, first = _closed_turn(h)
    h.hear(first, S.VadEdge("d1", "fall", end + 10), h.beats(end, end + 2700))          # closed at its cap
    grown = h.words(["w1", "w2", "w3"], t)
    h.hear(S.WordSpan("d1", 1, 2, True, grown, (grown[0][1], grown[-1][2])),
           S.EotHint("d1", "flux", "end", .9, end + 2800))
    for k in range(1, 20):
        h.hear(S.Tick(end + 2800 + 250 * k))
    h.pump()
    inputs = [c.prompt.input for c in h.model.calls]
    assert inputs[0].endswith("«w1 w2»") and inputs[-1].endswith("«w3»")
    assert sum(i.count("w1 w2") for i in inputs) == 1
    _assigned_once(h.conv.ear)
