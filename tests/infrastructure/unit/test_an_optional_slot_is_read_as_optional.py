"""A payload slot a card declares optional is read as optional by the ONE reader of «may be left out».

Audit 2026-11-17: `agenda:add_list` gained `items` described «(opcional: solo si lo nombra)». `payload_fill._optional`
reads the literal mark «(opcional)» / «(optional)», so the slot read as REQUIRED: the action stopped having one
fillable key, and the order-unserved door asked him «I still need: name, items» for a list he had only named.

The mark is spelt the way the reader reads it. The spellings it does not read, already in the manifests, are counted:
they can only go down, and none may be added.
"""
from __future__ import annotations

import json
import pathlib
import re

from nucleo.acts import payload_fill
from nucleo.request import order_unserved

ENGINE = pathlib.Path(__file__).resolve().parents[3]
#: Declared optional in words the reader does not read («(opcional: …», «(optional — …»). Only goes down.
UNREAD_MAX = 29   # measured 2026-11-17
_UNREAD = re.compile(r"\((?:opcional|optional)\b(?!\))", re.I)


def unread(manifests) -> list[str]:
    out = []
    for f in manifests:
        acts = json.loads(pathlib.Path(f).read_text(encoding="utf-8")).get("actions") or {}
        for act, spec in acts.items():
            payload = spec.get("payload") if isinstance(spec, dict) else None
            for key, desc in (payload.items() if isinstance(payload, dict) else ()):
                if _UNREAD.search(str(desc)) and not payload_fill.declared_optional(desc):
                    out.append(f"{pathlib.Path(f).parent.name}:{act}.{key}")
    return out


def test_a_new_list_needs_only_its_name():
    assert order_unserved.needed("agenda", "add_list", {"name": "Hardware store"}) == []
    assert order_unserved.needed("agenda", "add_list") == ["name"]
    assert payload_fill.fillable_key("agenda", "add_list") == "name", "words can no longer name the list"


def test_no_slot_is_added_with_a_mark_the_reader_does_not_read():
    found = unread(sorted((ENGINE / "widgets").glob("*/manifest.json")))
    assert not [f for f in found if f.startswith("agenda:add_list.")], found
    assert len(found) <= UNREAD_MAX, (f"{len(found)} slots say optional in a spelling `payload_fill._optional` does not "
                                      f"read (ceiling {UNREAD_MAX}): write «(opcional)» / «(optional)» whole — {found}")


def test_the_count_sees_the_spelling_that_was_missed(tmp_path):
    """Disarm: the description as it was written on 2026-11-16 is counted, and read as required by the real reader."""
    was = "[string, …] — lo que va en la lista, tal como lo dijo (opcional: solo si lo nombra)"
    f = tmp_path / "card" / "manifest.json"
    f.parent.mkdir()
    f.write_text(json.dumps({"actions": {"add_list": {"payload": {"name": "cómo la llama", "items": was}}}}), encoding="utf-8")
    assert unread([f]) == ["card:add_list.items"] and not payload_fill._optional(was)
    now = json.loads((ENGINE / "widgets/agenda/manifest.json").read_text(encoding="utf-8"))["actions"]["add_list"]["payload"]["items"]
    assert payload_fill._optional(now)
