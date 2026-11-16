"""A widget's card on demand: its declared actions and fields, without its data (Brain Worker plan step 4).

Measured: the only way a worker learnt a widget's actions was `read_widget`, which also returns up to 12 KB of the
widget's data — paid every time it only needed which action takes which field. `act card` (and `cli.widget card`)
returns the declaration alone. Variants: two widgets, a name resolved through the registry, an unknown id.
"""
from __future__ import annotations

import asyncio
import pytest

from nucleo.workers import widget_card


@pytest.mark.parametrize("wid,act,field", [("contactos", "create_group", "name"), ("agenda", None, None)])
def test_the_card_carries_every_declared_action_and_its_fields(wid, act, field):
    got = widget_card.card(wid)
    assert got["ok"], got
    card = got["result"]
    from widgets import runtime
    declared = runtime.get(wid)["actions"]
    assert set(card["actions"]) == set(declared)
    if act:
        assert field in card["actions"][act]["fields"]


def test_the_card_carries_no_data():
    """The declaration only: no view, no items — the keys are the card's, nothing of the widget's store."""
    card = widget_card.card("contactos")["result"]
    assert set(card) <= {"id", "title", "for", "actions", "collections"}
    for coll in (card.get("collections") or {}).values():
        assert "rows" not in coll and "items" not in coll


def test_an_unknown_widget_is_said_not_found():
    got = widget_card.card("no_such_widget_xyz")
    assert got["ok"] is False and got["error"]


def test_the_bridge_answers_card_and_allows_it():
    from nucleo.cli import worker_api
    from nucleo.workers.session import SessionRecord
    assert worker_api.classify_act("card", {"id": "contactos"}) == worker_api.ALLOW
    got = asyncio.run(worker_api._one_act(SessionRecord(task_id="1", goal="x"), "card", {"id": "contactos"}))
    assert got["ok"] and "create_group" in got["result"]["actions"]


def test_disarmed_without_the_act_the_worker_is_denied(monkeypatch):
    """RED proof: with `card` out of the bridge's acts the worker is back to `read_widget` (data included)."""
    from nucleo.cli import worker_policy
    monkeypatch.setattr(worker_policy, "_KNOWN_ACTS", tuple(a for a in worker_policy._KNOWN_ACTS if a != "card"))
    assert "card" in worker_policy.deny_reason("card", {})
