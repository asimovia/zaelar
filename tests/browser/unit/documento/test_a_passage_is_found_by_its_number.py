"""A number in the passage he names is the passage's IDENTITY, never noise (V2-884 step 5, found in passing).

Measured while building documento's state: `goto «Paso 2»` marked «Paso 1». The matcher dropped every token shorter
than four letters, so the digit vanished and «paso» alone tied every heading — the first won. Same class in English
(«Step 3» → «Step 1») and in the exact-phrase path («step 12» sat inside «step 120»). Now the numbers a target names —
a digit, a digit with its ordinal mark («2º», «3rd») or a spoken number from the ONE table every reader shares
(`refs.number_words`: «segundo», «third») — must all be carried by the block, read by `widgets/numbers_said.numbers_in`; a number no
block carries is «not found», never the nearest words. Disarms (named in the test): numbers ignored → the first
heading wins; only digits read → a spoken ordinal lands on the first step.
"""
from __future__ import annotations

import pytest

from widgets import store
from widgets.documento.blocks import _best_block
from widgets.numbers_said import numbers_in

ES = "\n\n".join(["# Receta"] + [f"## Paso {k}\n\nTexto de este paso." for k in (1, 2, 3, 12)])
EN = "\n\n".join(["# Guide"] + [f"## Step {k}\n\nSome text for this step." for k in (1, 2, 3, 120, 12)])


@pytest.mark.parametrize("body,said,lands", [
    (ES, "Paso 2", "Paso 2"), (ES, "el segundo paso", "Paso 2"), (ES, "paso dos", "Paso 2"), (ES, "2º paso", "Paso 2"),
    (ES, "Paso 12", "Paso 12"), (ES, "paso 1", "Paso 1"), (ES, "paso 9", ""),
    (EN, "Step 3", "Step 3"), (EN, "the third step", "Step 3"), (EN, "3rd step", "Step 3"),
    (EN, "step 12", "Step 12"), (EN, "step 9", "")])
def test_the_number_he_says_is_the_passage_he_gets(body, said, lands):
    assert _best_block(body, said) == lands, f"«{said}» → «{_best_block(body, said)}»"


def test_a_target_without_a_number_still_matches_by_its_words():
    assert _best_block(ES, "texto de este paso") and _best_block(EN, "some text for this step")


def test_the_numbers_a_text_names():
    assert numbers_in("el 2º paso y el tercero") == {2, 3}
    assert numbers_in("the 3rd step, 1.250 € and twelve") == {3, 1, 250}
    assert numbers_in("sin números") == frozenset()


def test_the_goto_door_marks_the_numbered_passage(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.documento import data
    data.apply_action("show", {"title": "Receta", "body": ES})
    assert data.apply_action("goto", {"text": "Paso 2"})["found"] == "Paso 2"
    assert data.apply_action("goto", {"text": "paso 9"})["ok"] is False, "a step the page does not have was marked"
