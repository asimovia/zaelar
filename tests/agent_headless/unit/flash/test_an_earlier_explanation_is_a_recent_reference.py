"""An earlier explanation is a reference to the recent conversation (V2-865).

The failure: «I did explain that some messages ago today» fired nothing — the English side of `needs_recent`
knew «earlier» and «you said», not a span of messages, minutes or hours ago, nor «I explained / told you /
asked you»; the Spanish side did not know «te pedí / te expliqué / hace horas».
"""
import pytest

from nucleo.flash.recall_heuristics import needs_recent


@pytest.mark.parametrize("said", [
    "I did explain that some messages ago today",
    "I did ask you some time ago to put some music here",
    "I told you a few minutes ago which one",
    "the song from some messages ago",
    "but I did explain which artist it was",
    "the one from a while ago, play it",
    "lo que salió hace unas horas",
    "te pedí hace horas que pusieras esa canción",
    "ya te expliqué lo del viaje",
    "te he pedido antes que lo apuntaras",
])
def test_an_earlier_explanation_reaches_for_the_recent_conversation(said):
    assert needs_recent(said), said


@pytest.mark.parametrize("said", ["put some music here", "what time is it", "hola", "pon música aquí"])
def test_a_plain_order_or_greeting_does_not(said):
    assert not needs_recent(said), said
