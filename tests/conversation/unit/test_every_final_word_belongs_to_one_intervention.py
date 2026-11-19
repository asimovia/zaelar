"""I2: every final word of the speech-to-text belongs to exactly one intervention (node 13.3).

Revisions REPLACE a provider turn's words (they rewrite words already given, adapter doc A4); a late partial never
undoes a final; a turn without its final leaves the intervention uncovered and it ends `incomplete`, not closed; a
reopen that loses to a seal moves the words heard since, all of them, to the amending intervention. Checked on fixed
cases and on seeded random revision streams.
"""
from __future__ import annotations

import random
from collections import Counter

from conversation.ear import signals as S
from conversation.ear.spans import Spans
from tests.conversation.unit.earkit import D, INCOMPLETE, feed, span, states, utterances, words


def _assigned_once(ear) -> None:
    keys = [(iv, w[0], w[1]) for iv, w in ear.spans.all_final_words()]
    word_keys = Counter((w, t0) for _iv, w, t0 in keys)
    assert all(n == 1 for n in word_keys.values()), [k for k, n in word_keys.items() if n > 1]


def test_a_revision_replaces_the_words_it_rewrites():
    sp = Spans()
    sp.add(D, 1, 1, False, words("w1", "w2"), "iv1", 1)
    sp.add(D, 1, 2, False, words("w1", "w3", "w4"), "iv1", 1)
    sp.add(D, 1, 3, True, words("w1", "w3", "w5"), "iv1", 1)
    assert [w[0] for w in sp.words("iv1")] == ["w1", "w3", "w5"] and sp.covered("iv1")


def test_a_late_partial_never_undoes_a_final():
    sp = Spans()
    sp.add(D, 1, 3, True, words("w1", "w2", "w3"), "iv1", 1)
    sp.add(D, 1, 2, False, words("w1"), "iv1", 1)
    assert [w[0] for w in sp.words("iv1")] == ["w1", "w2", "w3"] and sp.covered("iv1")


def test_a_turn_without_its_final_is_a_gap_and_the_intervention_ends_incomplete(ear):
    out = feed(ear, S.VadEdge(D, "rise", 0), span(1, 1, True, words("w1", "w2")),
               span(2, 1, False, words("w3", t0=600)), S.VadEdge(D, "fall", 900), S.EotHint(D, "flux", "end", .9, 950),
               S.Tick(950 + 2600))
    assert not utterances(out) and states(out)[-1][0] == INCOMPLETE
    assert not ear.spans.covered(ear.spans.owner(D, 1))


def test_two_provider_turns_of_one_intervention_close_with_every_word_once(ear):
    out = feed(ear, span(1, 1, False, words("w1")), span(1, 2, True, words("w1", "w2")),
               S.EotHint(D, "flux", "end", .8, 500),                                    # closes after seq 1
               span(2, 1, False, words("w3", t0=1500)),                                  # the person went on: reopened
               span(2, 2, True, words("w3", "w4", t0=1500)), S.EotHint(D, "flux", "end", .8, 2000))
    closed = utterances(out)
    assert [u.body.revision for u in closed] == [1, 2]
    assert closed[-1].body.text == "w1 w2 w3 w4"
    _assigned_once(ear)


def test_a_reopen_that_loses_to_the_seal_moves_its_words_to_the_amendment(ear):
    out = feed(ear, span(1, 1, True, words("w1", "w2")), S.EotHint(D, "flux", "end", .8, 500))
    first = utterances(out)[0]
    out = feed(ear, span(2, 1, True, words("w3", t0=1000)),                             # reopen, revision 2
               S.Sealed(first.body.intervention_id, 1),                                  # …but revision 1 sealed first
               S.EotHint(D, "flux", "end", .8, 1500))
    amend = utterances(out)[-1]
    assert amend.body.intervention_id != first.body.intervention_id
    assert amend.body.amends == first.body.intervention_id and amend.body.text == "w3"
    assert [w[0] for w in ear.spans.words(first.body.intervention_id)] == ["w1", "w2"]
    _assigned_once(ear)


def test_seeded_revision_streams_never_put_a_word_in_two_interventions(ear):
    for seed in range(40):
        rng = random.Random(seed)
        sp = Spans()
        for seq in range(1, rng.randint(2, 6)):
            iv = f"iv{rng.randint(1, 3)}"
            n = rng.randint(1, 5)
            for rev in range(1, rng.randint(2, 5)):
                ws = words(*[f"w{seq}{i}{rng.randint(0, 2)}" for i in range(rng.randint(1, n))], t0=seq * 10_000)
                sp.add(D, seq, rev, rng.random() < .3, ws, iv, 1)
            sp.add(D, seq, 99, True, words(*[f"w{seq}{i}" for i in range(n)], t0=seq * 10_000), iv, 1)
            assert len(sp.words(iv)) == len({(w[0], w[1]) for w in sp.words(iv)})
        finals = sp.all_final_words()
        assert len(finals) == len({(w[0], w[1]) for _iv, w in finals}), seed
