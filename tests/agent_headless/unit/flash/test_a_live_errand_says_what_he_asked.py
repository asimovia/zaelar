"""A live errand carries what he ASKED for, whatever the dialog window still holds (node 2.1667, V2-874).

Measured on a demo turn (2026-11-10): «abre el que sea mejor oferta» while a monitors search ran with no results yet.
The prompt's running-errands block carried the errand only by the title the worker wrote, cut at 60 characters, and
the turn that commissioned it had left the last-ten-messages window — the model answered «No sé a qué me remites…
no hay nada en pantalla con ofertas». His commissioning sentence (`SessionRecord.heard`) now rides on the errand's own
line, bounded (`ASKED_MAX`, cut on a word and marked), so a reference to what is still to come can bind to it.
Disarm: `name_of` ignores `heard` → red. Since V2-878 §2 his words REPLACE the title on the line (one name).
"""
from __future__ import annotations

import time

import pytest

from nucleo import dispatch
from nucleo.turn.prompt import live_tasks

ASKED = {
    "es": "búscame tres monitores de 27 pulgadas 4k por menos de 400 euros o por ahí, y me los enseñas cuando los tengas",
    "en": "can you find me like three 27 inch 4k monitors, under 400 bucks or so? show me when you've got them",
}
TITLE = {"es": "Buscar monitores de 27 pulgadas con resolución 4K (UHD) con precio", "en": "Find 27-inch 4K UHD monitors"}


@pytest.fixture(autouse=True)
def _clean():
    dispatch._SESSIONS.clear()
    yield
    dispatch._SESSIONS.clear()


@pytest.fixture(params=["es", "en"])
def lang(request):
    return request.param


def _errand(lang, heard, tid="t1"):
    r = dispatch.SessionRecord(task_id=tid, goal=TITLE[lang], kind="web", heard=heard)
    r.status = "running"
    r.started = r.last_event_at = time.time() - 30
    dispatch._SESSIONS[tid] = r
    return r


def _block() -> str:
    return " ".join(live_tasks.pending_task_lines())


def test_the_errand_says_what_he_asked_although_his_turn_left_the_window(lang):
    _errand(lang, ASKED[lang])
    assert ASKED[lang][:60] in _block(), "his commissioning words are on the errand's line"


def test_a_long_request_is_cut_on_a_word_and_marked(lang):
    long = (ASKED[lang] + " ") * 4
    _errand(lang, long)
    line = live_tasks.name_of(dispatch.pending_summaries()[0])
    asked = line.split("«", 1)[1].split("»", 1)[0]
    assert len(asked) <= live_tasks.ASKED_MAX + 1 and asked.endswith("…")


def test_one_name_per_errand_his_words_or_the_title_never_both(lang):
    assert live_tasks.name_of({"request": TITLE[lang], "heard": ""}).startswith("«" + TITLE[lang][:20])
    named = live_tasks.name_of({"request": TITLE[lang], "heard": ASKED[lang]})
    assert ASKED[lang][:40] in named and TITLE[lang][:30] not in named


def test_every_live_errand_carries_its_own(lang):
    _errand(lang, ASKED[lang], "t1")
    _errand(lang, "y otra cosa distinta" if lang == "es" else "and something else entirely", "t2")
    block = _block()
    assert ASKED[lang][:40] in block and ("otra cosa distinta" in block or "something else entirely" in block)
