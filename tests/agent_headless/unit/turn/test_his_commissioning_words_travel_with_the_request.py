"""His sentence that commissions an errand travels with the request to the errand it opens (refactor2710-02 input).

find-concert-tickets ES: «Búscame entradas para un concierto de Rosalía en Madrid este mes» became a worker errand
whose sheet never had `asked` — the row door judges rows by his words, so it judged nothing and offered rows that were
not about Rosalía. The old text channel noted his sentence at launch (`commission_words`, node 2.630) and the voice
turn never did; refactor2710-01 deleted the old channel's half. The class is the Request's: born once with his words,
it carries them to the worker and the sheet (`request.model.heard` → the escalation's context → `SessionRecord.heard`
→ `sheets._hear` → the row door). Disarm: return "" from `request.model.heard` → the first test goes red.
"""
from __future__ import annotations

from tests.platform import turn_harness as H

HEARD = "Búscame entradas para un concierto de Rosalía en Madrid este mes."


def test_the_sheet_hears_the_words_its_record_carries(monkeypatch):
    from types import SimpleNamespace

    from nucleo import sheets
    from widgets.results import category_gate
    heard: list = []
    monkeypatch.setattr(category_gate, "hear", lambda sheet, words: heard.append((sheet, words)) or True)
    sheets._hear("results::t1", HEARD)
    sheets._hear("results::t2", "")
    assert heard == [("results::t1", HEARD)]
    assert SimpleNamespace(heard=HEARD).heard     # the record field the dispatcher fills from the context
