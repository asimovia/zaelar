"""A stop that names the ACTIVITY to stop is an order about it, not a silence order (bank case msg-en-mail-hide).

«Stop showing me the Social tab in my mail» is read as a hard interrupt by the grammar: before refactor2710-07 the turn
ended before the model and the mail order it carried was lost. Telling the two apart by the sentence's shape (a gerund,
«de» + infinitive, a token count) is a rule on his words (CRIT-W10); since refactor2710-07 the brief's `screen_action`
verdict decides it, asked before the turn and reused by it (`brief.verdict_before_the_turn`): a stop whose verdict
names a declared action on a card runs the turn; one that names nothing is still silence.

Disarm: make `hard_turn.names_an_act_on_screen` return False and the first test goes red.
"""

import pytest

from voice.interrupt_grammar import hard_interrupt


@pytest.mark.parametrize("line", ["stop", "stop talking", "stop talking now", "para de hablar", "para de hablar ya",
                                  "silencio, por favor", "basta ya por favor"])
def test_a_bare_stop_is_still_silence(line):
    assert hard_interrupt(line) == "stop"

