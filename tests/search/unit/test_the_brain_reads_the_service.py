"""The brain's three seams into the service (V2-782 F4 / T4.4): the brief asks the routing question, the shadow route
is emitted, a network agent's rows keep their rating, and the research brief keeps the size its composer read."""
from __future__ import annotations

from nucleo.cli import mesh as mesh_cli
from nucleo.workers import brief as research


def test_a_network_agents_rows_keep_rating_phone_and_say_where_they_came_from():
    rows = mesh_cli._rows_in({"hotels": [
        {"name": "Humphreys Half Moon Inn", "price": "$785", "url": "https://h/1", "rating": 8.8, "phone": "+1 619"},
        {"title": "Inyectores De Coche", "amount": "260", "link": "https://e/2"}]})
    assert rows[0]["title"] == "Humphreys Half Moon Inn" and rows[0]["price"] == "$785"
    values = {f["value"] for f in rows[0]["facts"]}
    assert "8.8" in values and "+1 619" in values
    assert any(v in values for v in ("agente de la red", "network agent"))
    assert mesh_cli._MESH_ROWS_CAP <= 8


def test_the_brief_takes_the_size_from_the_composer_who_read_his_words():
    """V2-840 H1: «a couple of recipes» is read by the composer (its prompt: «si DIJO un número, pon ESE»); the
    brief keeps what it declared, and his words are not re-read by a numeral table."""
    raw = ('{"research": true, "goal": "recetas sin gluten", "hard": ["sin gluten"], "breadth": {"min_candidates": 6},'
           ' "deliverable": {"n_final": 2}}')
    b = research.parse(raw, request="pull a couple of gluten-free recipes")
    assert b["deliverable"]["n_final"] == 2 and b["breadth"]["min_candidates"] == 6
    assert "pon ESE" in research._SYSTEM
