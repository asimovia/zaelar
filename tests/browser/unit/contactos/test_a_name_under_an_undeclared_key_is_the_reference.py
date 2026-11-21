"""A contact's name under a key the action does not declare is the row it names, not a loose pronoun.

Measured: the model called `widget_data contactos:set_favorite {"contacto": "<name>", "favorite": true}` with the
declared key `contactId` empty. `payload_ref` read nothing, the call read as a loose pronoun on a closed card
(`absent_widget_misroute`) and the home action went to a worker. After the declared id field and `name`/`contact`,
the ONE text the call carries under an undeclared key is the reference; two such texts name nothing, and an action
with no id field still points at no row.

Disarm (seen red, in memory): the manifest's payload spec unreadable → the fallback answers "" and the behaviour
tests go red.
"""
from __future__ import annotations

import pytest

from nucleo.acts import frontend as card_target   # the facade: importing `acts.card_target` first is circular
from nucleo.acts import payload_fill


@pytest.fixture
def ct(tmp_path, monkeypatch):
    """ISOLATED store — never the operator's real directory."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.contactos import data as d
    d.apply_action("add_contact", {"name": "Rowan"})
    return d


@pytest.fixture
def closed(monkeypatch):
    from memory import api as memapi
    monkeypatch.setattr(memapi, "state", lambda: {"open_widgets": []})


def _rowan_id(ct) -> str:
    return next(c["id"] for c in ct.load_db()["contacts"] if c["name"] == "Rowan")


def test_one_undeclared_text_is_the_reference():
    assert card_target.payload_ref("contactos", "set_favorite", {"contacto": "Rowan", "favorite": True}) == "Rowan"


def test_a_declared_id_with_named_only_reads_nothing():
    assert card_target.payload_ref("contactos", "set_favorite", {"contactId": "c1", "contacto": "Rowan"},
                                   named_only=True) == ""


def test_two_undeclared_texts_name_nothing():
    assert card_target.payload_ref("contactos", "set_favorite", {"contacto": "Rowan", "persona": "Quinn"}) == ""


def test_non_string_values_are_ignored():
    assert card_target.payload_ref("contactos", "set_favorite", {"favorite": True, "rank": 3}) == ""
    assert card_target.payload_ref("contactos", "set_favorite",
                                   {"contacto": "Rowan", "favorite": True, "rank": 3}) == "Rowan"


def test_an_action_with_no_id_field_points_at_no_row():
    assert card_target.payload_ref("contactos", "add_contact", {"nombre": "Rowan"}) == ""


def _call(wid: str, action: str, item: str, payload: dict):
    """The call sequence of `tool_executor_widget_calls._handle_widget_data_tool`."""
    from widgets import refs
    ref = item or card_target.payload_ref(wid, action, payload, named_only=True)
    res = refs.resolve(wid, action, ref, payload)
    mis = card_target.absent_widget_misroute(wid, action, ref, resolved=res.ok or res.needs == "ambiguous",
                                             named_widget="", payload=payload)
    return res, mis


def test_a_name_under_an_undeclared_key_on_a_closed_card_resolves_to_that_contact(ct, closed):
    res, mis = _call("contactos", "set_favorite", "", {"contacto": "Rowan", "favorite": True})
    assert not mis, "the named contact was read as a loose pronoun on a closed card"
    assert res.ok and res.payload.get("contactId") == _rowan_id(ct), res


def test_a_real_loose_pronoun_on_a_closed_card_is_still_a_misroute(ct, closed):
    assert _call("contactos", "set_favorite", "lo", {"favorite": True})[1]
    assert _call("contactos", "set_favorite", "", {"favorite": True})[1]


def test_disarmed_the_fallback_the_named_contact_is_a_misroute_again(ct, closed, monkeypatch):
    """Disarm: the payload spec unreadable → the fallback answers "" and the behaviour test goes red."""
    def _boom(*a, **k):
        raise RuntimeError("disarmed")
    monkeypatch.setattr(payload_fill, "_payload_spec", _boom)
    with pytest.raises(AssertionError):
        test_a_name_under_an_undeclared_key_on_a_closed_card_resolves_to_that_contact(ct, None)
    with pytest.raises(AssertionError):
        test_one_undeclared_text_is_the_reference()
