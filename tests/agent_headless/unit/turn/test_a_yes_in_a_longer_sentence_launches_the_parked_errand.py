"""A yes inside a longer sentence launches the parked errand, and the reply says what the gate did (node 2.456).

three-tasks-at-once (2026-10-11 02:58), the game parked on «¿La hago?» / «Shall I?»:
  · ES «Sí, justo eso, y ponle que el muñeco salte más alto, que si no no hay quien pase las plataformas. ¿El monitor
    cómo va?» — `classify_reply` reads the LAST word, «no» (from «si no»), and the game stayed parked;
  · EN «yeah go ahead with the game, and add coins to it too. btw for the monitor it has to be at least 27 inches» —
    the judge, seeing the monitor, answered OTHER; parked again, and the monitor's refinement was dropped with it;
  · EN «ok. just ping me when it's up» resolved the yes — and the reply asked «shall I start it? Say the word»;
  · ES «Vale, perfecto. Del monitor, que no pase de 150» → the model re-escalated the game and said «va en marcha»
    over an errand still parked.

Mechanism pinned here (V2-878 §4b): the parked errand waits on its ROW, and a reply decides it by word only when it
IS one of the row's declared answers — never the word a longer sentence opens with (`opening_answer` and the yes/no
tables went). A longer reply is routed to the row by the switchboard at the turn's gate (V2-931).
"""
from __future__ import annotations





def test_an_if_is_not_a_yes(monkeypatch):
    from nucleo.request import consent_ask
    monkeypatch.setenv("ZAELAR_LANGUAGE", "es")
    assert consent_ask.declared_answer("Si no te importa, espera un poco") is None
    assert consent_ask.declared_answer("Sí") == "yes" and consent_ask.declared_answer("no") == "no"
    assert consent_ask.declared_answer("Sí, venga") is None          # longer: the brief's pick reads it
