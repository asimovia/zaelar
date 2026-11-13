"""A document an act of the turn is WRITING is never denied by a later pass of the same turn (words follow the act).

Demo sandbox 2026-11-13, F1 (build 138): «write me a one page summary of the bitcoin whitepaper, in a document». The
commission pass took the compose rung (`card_commission.before_worker`, kind `compose`): the page is written in ONE
background request and lands on `documento` ~10 s later. The same turn had also searched the web, and the search's
answer pass — which sees no calls — was told only what was ALREADY on screen (`canvas_focus.this_turn_cards`). The
document was not there yet, so it answered «I can't create or save a document for you here…» over the document that
appeared seconds later; the mouth then added «… is on your screen», contradicting the words.

The class: an act of the turn that is under way is a fact for every later pass of that turn. The compose rung records
the card it is writing (`canvas_focus.writing`); the search's answer pass is told it (`compose_system(writing=…)`), and
the order-after-search repair never runs a second act on the card already being written. Disarms (named in the test):
no `writing` record → the answer pass is told nothing; no `writing` tail → the prompt says nothing of it.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo import canvas_focus as cf
from nucleo.acts import search as st


@pytest.fixture(autouse=True)
def _clean():
    cf._reset()
    yield
    cf._reset()


def _compose_decision(monkeypatch):
    from nucleo.flash import card_commission as cc, compose_rung

    async def _got(*a, **k):
        return {"kind": "compose", "widget_id": "documento", "action": "show", "title": "Bitcoin — summary",
                "brief": "a one-page summary"}

    async def _run(*a, **k):
        return True

    monkeypatch.setattr(cc, "commission_call", _got)
    monkeypatch.setattr(compose_rung, "run", _run)
    return cc


@pytest.mark.parametrize("said", ["write me a one page summary of the bitcoin whitepaper, in a document",
                                  "escríbeme en un documento un resumen de una página del whitepaper de bitcoin"])
def test_the_compose_rung_records_the_card_it_is_writing(monkeypatch, said):
    cc = _compose_decision(monkeypatch)
    esc, read = {"v": said, "more": []}, {"v": None}

    async def _go():
        return await cc.before_worker(esc, read, brief=None, operator_text=said, spec=None,
                                      emit=lambda *a, **k: None, present=lambda *a, **k: True,
                                      apply_widget_data=lambda *a, **k: None)

    assert asyncio.run(_go()) == "call"
    assert cf.this_turn_writes() == ["documento"], "the turn's later passes were not told the card is being written"


def test_the_record_belongs_to_one_turn():
    cf.writing("documento::abc")
    assert cf.this_turn_writes() == ["documento"]
    cf.begin_turn()
    assert cf.this_turn_writes() == []


def test_the_search_answer_pass_is_told_the_document_is_being_written():
    res = {"answer": "Published in 2008 by Satoshi Nakamoto…", "results": [], "source": "gemini"}
    plain = st.compose_system("write me a summary in a document", "bitcoin whitepaper", res, "RESPUESTA: …")
    told = st.compose_system("write me a summary in a document", "bitcoin whitepaper", res, "RESPUESTA: …",
                             writing=["documento"])
    assert "documento" not in plain
    assert "EN MARCHA" in told and "documento" in told and "no digas que no puedes crearlo" in told


def test_the_order_after_search_never_runs_again_on_a_card_being_written(monkeypatch):
    from nucleo.acts import repair_after_lookup as ra
    monkeypatch.setattr(ra, "order_card_after_search", lambda brief, answer="": "documento")
    cf.writing("documento")
    assert ra._order_with_a_fact("write it in a document", "I can't create a document here", None) is None
