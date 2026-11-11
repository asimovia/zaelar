"""V2-887 step 3 — an open card says which accounts feed it, read from its manifest, never from a fixed list.

Measured 2026-11-11 (local, T12/T13): Contacts open, Google Contacts connected — the prompt said «GOOGLE conectado:
no» because the Google fact entered only with agenda/mensajeria/fotos/archivos/youtube open. The model promised an
import, called nothing and then said «no veo la fuente de Google». Every open card whose manifest declares
`connector_families` now carries one line: each live connector that feeds it, connected or not.
"""
from __future__ import annotations

from nucleo.turn.prompt import catalogs


def _live(monkeypatch, rows):
    from connectors import registry
    monkeypatch.setattr(registry, "descriptors", lambda: rows)
    monkeypatch.setattr(registry, "serves", lambda d, fam: fam in d.get("families", ()))


def test_an_open_contacts_card_names_its_connected_google_source(monkeypatch):
    _live(monkeypatch, [{"id": "google-contacts", "label": "Google Contacts", "connected": True, "families": ["contactos"]},
                        {"id": "whatsapp", "label": "WhatsApp", "connected": False, "families": ["contactos", "mensajeria"]}])
    line = catalogs._sources_of_open_cards({"contactos"})
    assert line == "[contactos] sources: Google Contacts (connected), WhatsApp (not connected)"
    assert line in catalogs.connector_facts({"contactos"})


def test_a_card_without_declared_families_adds_nothing(monkeypatch):
    _live(monkeypatch, [{"id": "google-contacts", "label": "Google Contacts", "connected": True, "families": ["contactos"]}])
    assert catalogs._sources_of_open_cards({"clock"}) == ""
    assert catalogs._sources_of_open_cards(set()) == ""


def test_the_google_fact_no_longer_reads_a_fixed_card_list():
    import inspect
    assert '"agenda", "mensajeria", "fotos", "archivos", "youtube"' not in inspect.getsource(catalogs.connector_facts)
