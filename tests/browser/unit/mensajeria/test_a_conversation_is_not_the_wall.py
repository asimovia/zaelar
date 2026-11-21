"""«Abre el chat de Marta» is HER conversation, not the agent's chat wall — and a tie between the two is a doubt.

Measured with the messaging decision bank (2026-10-23): «Abre el chat de Marta» opened the wall's chat tab 3/3,
decided by the wall lane in 130 ms without the model. The name resolver saw «chat» (the wall's alias) and no card.
Two pieces of declared data and one rule fix the class: the messaging card names a conversation («chat de», «chat
con», «chat with»), and a tie between a system surface and a card is AMBIGUOUS — no lane acts on a coin toss.
"""
from __future__ import annotations



def test_a_named_conversation_resolves_to_the_messaging_card():
    from widgets import runtime
    assert runtime.identify("Abre el chat de Marta")["match"] == "mensajeria"


def test_a_tie_between_a_surface_and_a_card_is_ambiguous():
    from widgets import runtime
    r = runtime.identify("muéstrame la conversación con Luis")
    assert r["match"] is None and r["ambiguous"] is True
