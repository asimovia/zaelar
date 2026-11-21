"""V2-713 R5 · La FORMA del turno es una política del operador, no una receta escrita en el prompt.

## Qué decía la auditoría y qué se ha hecho con ello

`nucleo/flash/prompt.py:277-287` conservaba «Respondes SIEMPRE al instante en 1-2 frases habladas […] UNA
ACCIÓN por turno». `principles.md` nombra esa clase sin ambigüedad — *«Rail on JUDGEMENT — a LIMIT, remove
it»*, con ejemplos que son literalmente de esta forma — y desde V2-633 hay dónde ponerla: `genesis.json`
como defecto de fábrica, `<workspace>/config/style.json` como lo que el operador diga, leído por uso.

No se ha vaciado el bloque `ops` entero: se han movido las DOS que ya tenían forma de política. Las demás
irán cuando cada una tenga la suya, no antes.

## La contabilidad honesta, dicha y no redondeada

Mover las dos frases quitó **110 bytes** de `prompt.py` y añadió **198** en `shape_line()`: lo que el modelo
lee **creció 88 bytes**. No se vende como una reducción. Lo que compra es que dos constantes que fijaba quien
estuviera trabajando ese día son ahora dato que él cambia hablando.

Y al contarlas apareció una tercera fuente que el trinquete de prosa no veía: los **402 bytes** de
`prompt_line()` viajan en cada turno desde V2-633 sin haber aparecido nunca en ningún número.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from nucleo import style_policy as sp

ENGINE = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    """Workspace de usar y tirar: el fichero de override nunca puede ser el real del operador."""
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    sp._reset_for_tests()
    yield
    sp._reset_for_tests()


# ── 1 · los defaults son los que ya se comportaban así ──────────────────────────────────────────────────


def _set(knobs: dict) -> None:
    """His rows for these style knobs (V2-806: rows of the rules table at the `voice` scope)."""
    for k, v in knobs.items():
        sp.set_pref(k, v)

def test_los_defaults_viven_en_el_GENESIS_que_es_dato_commiteado():
    g = json.loads((ENGINE / "nucleo" / "genesis.json").read_text(encoding="utf-8"))["style"]
    assert g["max_sentences"] == 2 and g["one_action_per_turn"] is True


# ── 2 · es una política: él la cambia y el turno siguiente la obedece ────────────────────────────────────

# ── 3 · llega al turno de verdad ────────────────────────────────────────────────────────────────────────

# ── 4 · lo que NO se hizo, afirmado ─────────────────────────────────────────────────────────────────────
