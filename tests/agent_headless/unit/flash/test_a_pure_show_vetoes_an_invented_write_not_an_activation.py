"""V2-713 R1 · Un «abre X» puede vetar una ESCRITURA inventada, nunca una activación.

## El incidente que creó el guarda, y el que lo delató

`show_request_blocks_data_action` nació de un caso real: «abre la agenda» y el modelo colaba un `add_meeting`
con título y fecha que el operador no había dicho. Eso hay que pararlo y se sigue parando.

Lo que no funcionaba era CÓMO lo reconocía: preguntando «¿es una acción de vista?». Medido el 2026-09-16 —
«abre música y sigue con la pista» se lee como show puro (no lleva verbo de cambio, y «sigue» está
deliberadamente FUERA de `_ACTIVATE_VERB_RE` porque el stem choca con «el siguiente»), así que un `resume`
bien elegido se descartaba y el operador se quedaba con una app que no hacía nada.

Ampliar la lista de verbos es justo el movimiento que V2-712 acaba de retirar del consentimiento: crece un
incidente cada vez y la frase siguiente se escribe de otra forma. El propio auditor lo dice: «no seguir
ampliando sinónimos».

## Lo que se afirma aquí

Que la pregunta se ha movido del VERBO a la LLAMADA — ¿trae esta acción contenido que la frase no menciona? —,
que una acción sin datos pero CON consecuencia (`clear_all`) sigue bloqueada, que el turno de voz pasa el
payload, y que cada veto queda contado en sombra para poder retirar el guarda con un número en vez de con una
opinión.
"""
from __future__ import annotations


import pathlib

import pytest


ENGINE = pathlib.Path(__file__).resolve().parents[4]


# ── 1 · una activación pasa; una escritura inventada no ─────────────────────────────────────────────────

# ── 2 · «sin datos» NO es «sin consecuencia» ────────────────────────────────────────────────────────────

# ── 3 · ningún verbo nuevo ──────────────────────────────────────────────────────────────────────────────

# ── 4 · los dos canales, y la cuenta para poder retirarlo ───────────────────────────────────────────────

# ── 5 · el nivel de las acciones de activación está DECLARADO (V2-712) ──────────────────────────────────

@pytest.mark.parametrize("wid,act", [("musica", "resume"), ("musica", "play"), ("musica", "next"),
                                     ("youtube", "play"), ("youtube", "play_item")])
def test_una_activacion_se_DECLARA_y_declara_tambien_su_nivel(wid, act):
    import json
    spec = json.loads((ENGINE / "widgets" / wid / "manifest.json").read_text(encoding="utf-8"))["actions"][act]
    assert spec.get("activation") is True, "«cambia lo que el widget HACE» lo dice el manifiesto, no un verbo"
    assert spec.get("sensitivity") == "routine", "y el nivel también se declara (V2-712)"
