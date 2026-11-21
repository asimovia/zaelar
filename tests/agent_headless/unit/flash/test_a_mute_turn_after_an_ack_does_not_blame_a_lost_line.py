"""A mute turn after «sounds good 👍» with a build running is not «Sorry, I lost that» (V2-781).

Measured in `build-workout-tracker-widget__us` (2026-10-10): the widget build was live, the operator acknowledged
with «sounds good 👍», the model returned nothing, and the backstop — which demotes live work that is not about
THIS line — answered «Sorry, I lost that. Could you say it again?». An acknowledgement asks for nothing new, so
the live work IS what it is about.
"""
from types import SimpleNamespace

from voice import endpointing


LANG = SimpleNamespace(filler_still_working="Still on it.", mute_lines=("Sorry, I lost that.",))


def test_the_english_acks_are_backchannels():
    for t in ("sounds good 👍", "cool", "great, thanks", "sure", "perfect", "alright"):
        assert endpointing.is_backchannel(t), t
    assert not endpointing.is_backchannel("open telegram")

