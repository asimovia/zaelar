"""A leaving act is read by its DECLARATION, not by the shape of a send (V2-919).

Measured 2026-11-16: «create a group on WhatsApp with <person> called <name>» — the model's call was complete
(`members` a list of the person he named), the widget and the connector created the group when handed the call, and
the hand-off (`nucleo/request/send_task`) dropped it: a list read as an empty slot, so the row asked the send's
question about a recipient he had already given.

M1 — a value is read by the field's declared kind (`widgets.field_types.filled`, `types` in the manifest): a list
field is filled by at least one item, a boolean by a value that reads as one, any other field by non-blank text (or a
number the card reads); the wrong kind fills nothing. Parametrised over EVERY widget's leaving actions and their
declared slots, so a new widget or action is covered the day it is declared.

Disarmed (seen red): `send_task.sources` back to «a non-blank string» → the list slot reads `none`.
"""
from __future__ import annotations

import pytest


def _leaving_slots() -> list[tuple[str, str, str, str]]:
    from nucleo.workers import exit_slots
    from widgets import effects, runtime
    out = []
    for w in runtime.catalog():
        wid = str(w.get("id") or "")
        for act, spec in ((runtime.get(wid) or {}).get("actions") or {}).items():
            if isinstance(spec, dict) and effects.leaves(wid, act):
                for slot, d in exit_slots.declared(wid, act).items():
                    out.append((wid, act, slot, str(d.get("key") or slot)))
    return out


SLOTS = _leaving_slots()


def _values(kind: str) -> tuple[list, list]:
    """(values of the declared kind, values that are NOT — blank or the wrong kind)."""
    if kind == "list":
        return [["Ana"], ["Ana", "Luis"], [{"id": "c1", "name": "Ana"}]], [[], [""], ["  "], "Ana", None, 3]
    if kind == "bool":
        return [True, False, "true", "no"], [None, "maybe", ["x"]]
    return ["Ana", "whatsapp", 3], ["", "   ", None, [], ["Ana"], {"x": 1}, True]


def test_every_leaving_act_with_slots_is_covered():
    assert SLOTS, "no leaving action declares slots: the sweep would prove nothing"
    assert any(a == "create_group" for _w, a, _s, _k in SLOTS)


@pytest.mark.parametrize("wid,act,slot,key", SLOTS, ids=[f"{w}:{a}:{s}" for w, a, s, _k in SLOTS])
def test_a_slot_value_is_read_by_its_declared_kind(wid, act, slot, key):
    from nucleo.request import send_task
    from widgets import field_types
    kind = field_types.declared(wid, act).get(key, "")
    good, bad = _values(kind)
    for v in good:
        assert field_types.filled(wid, act, key, v), (wid, act, key, kind, v)
        got = send_task.sources(wid, act, {key: v}, "Ana Luis whatsapp")[slot]
        assert got["source"] != send_task.NONE, (wid, act, slot, v, got)
    for v in bad:
        assert not field_types.filled(wid, act, key, v), (wid, act, key, kind, v)
        got = send_task.sources(wid, act, {key: v}, "Ana Luis whatsapp")[slot]
        assert got["source"] == send_task.NONE, (wid, act, slot, v, got)


def test_several_people_are_his_only_when_every_one_is():
    from nucleo.request import send_task
    assert send_task.sources("mensajeria", "create_group", {"members": ["Ana", "Luis"]},
                             "crea un grupo con Ana y Luis")["recipient"]["source"] == send_task.HIS
    assert send_task.sources("mensajeria", "create_group", {"members": ["Ana", "Quinn"]},
                             "create a group with Ana")["recipient"]["source"] == send_task.AGENT


def test_the_card_rule_reads_a_blank_list_as_no_value():
    from nucleo.workers import exit_slots
    out = exit_slots.Reading({"n": [" "]})
    exit_slots._card({"wid": "mensajeria", "act": "reply", "row_call": False}, out, "recipient", "n")
    assert out.sources["recipient"] == "none"
    out = exit_slots.Reading({"n": 2})
    exit_slots._card({"wid": "mensajeria", "act": "reply", "row_call": False}, out, "recipient", "n")
    assert out.sources["recipient"] == "card"


def test_the_group_card_reads_his_answer_as_items(monkeypatch):
    """His answer to «with whom?» lands as ONE item of the list field; the card splits the names it carries."""
    from widgets.mensajeria import data as _md  # noqa: F401 — the card's own import order
    from widgets.mensajeria.actions import groups
    seen = []
    monkeypatch.setattr(groups, "_by_id", lambda members, payload: seen.append(list(members)) or [])
    groups._a_create_group("create_group", {"platform": "whatsapp", "name": "Viaje", "members": ["Ana y Luis"]})
    groups._a_create_group("create_group", {"platform": "whatsapp", "name": "Trip", "members": "Ana and Luis"})
    assert seen == [["Ana", "Luis"], ["Ana", "Luis"]]
