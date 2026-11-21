"""A status sentence never says the browser's micro-step — «pulsando en la página» is the card's, not his ear's.

rental-car-automatic-airport (ES, 2026-10-11): «Perdona, pero me estás dando precios… ¿Me lo puedes confirmar?» →
«Así va todo: Alquiler coche automático aeropuerto Málaga 12-16 oct 20 — pulsando en la página.» The phase is read
off `progress._SAY`'s browser family (`progress.is_mechanical`), so the status line says the worker's own milestone
note instead, or «under way» when there is none.
"""
from __future__ import annotations

import threading

import pytest

from nucleo.workers import progress as P


@pytest.fixture(autouse=True)
def _spanish_instance(monkeypatch):
    """The phases are produced in the instance's language (`progress.say`); this file pins the Castilian ones."""
    monkeypatch.setenv("ZAELAR_LANGUAGE", "es")

ERRAND = "Buscar alquiler de coche automático en el aeropuerto de Málaga"
NOTE = "Kayak descartado (carrusel sin filtro de cambio); DiscoverCars a punto de buscar"


def _brief():
    ev = threading.Event()
    ev.set()
    return {"event": ev, "result": {"wants_words": {"choice": "tell", "confidence": 0.99, "probs": {"tell": 0.99}},
                                    "request_type": {"choice": "question", "confidence": 0.99,
                                                     "probs": {"question": 0.99}}},
            "_call_id": "t", "turn_id": "t", "open_ids": []}


@pytest.mark.parametrize("phase", ["pulsando en la página", "usando el teclado — lleva 4s",
                                   "entrando en discovercars.com", "escribiendo «12/10/2026»…",
                                   "recogiendo lo que hay en la página"])
def test_a_browser_micro_step_is_mechanical(phase):
    assert P.is_mechanical(phase)


@pytest.mark.parametrize("phase", [NOTE, "12 resultados", "buscando «sitio preferido» en la memoria", ""])
def test_a_milestone_or_an_outcome_is_not(phase):
    assert not P.is_mechanical(phase)

