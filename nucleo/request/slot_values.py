"""nucleo/request/slot_values.py — whether a slot of an act HAS a value, by the slot's KIND (split from `send_task`).

A slot's value is TEXT — a non-blank string — except a slot the card DECLARES as taking several (`"many": true`, a
group's members) or a field the action declares as a list (its manifest value is one), which also takes a list with
at least one non-blank name. A one-person recipient (`send_to`'s `contact`) given a list is asked, as before. Anything else — a list where text is expected, a dict, a number, a boolean, an empty list — is NO
value: the slot is asked, never sent (measured: `text: ["hola"]` reached the card as the text «['hola']»).
"""
from __future__ import annotations


def _text(v) -> bool:
    return isinstance(v, str) and bool(v.strip())


def filled(v, *, many: bool = False) -> bool:
    """`v` is a value of its slot: non-blank text, or — when the slot takes several (`many`) — a list of names with at
    least one non-blank. Measured both ways: `members: ["Ana", "Luis"]` read as empty (asked «to whom?» twice), and a
    list in a text slot sent literally."""
    if _text(v):
        return True
    return many and isinstance(v, (list, tuple)) and any(_text(x) for x in v) and all(
        isinstance(x, str) or x is None for x in v)


def takes_many(wid: str, action: str, key: str, decl: dict | None = None) -> bool:
    """Does this slot take several values: the card declares it (`"many": true` on the slot) or the field is a list."""
    if (decl or {}).get("many") is True:
        return True
    from nucleo.flash import payload_fill   # `_payload_spec` never raises: {} for an unread declaration
    return isinstance(payload_fill._payload_spec(wid, action).get(key), list)


def end_names(wid: str, action: str, key: str) -> bool:
    """The act's declared end state (`done_when`) names this field (`{key}`, not `{key?}`): without it the act cannot
    be judged, so an optional field it names is still asked (`send_draft`'s `{contact}`)."""
    import json

    from nucleo.circuit import spec as _spec
    return "{" + key + "}" in json.dumps(_spec.template_of(wid, action) or {}, ensure_ascii=False)


def _each(v) -> list:
    """The values of a slot, one per person (a list) or the one."""
    return [x for x in v if _text(x)] if isinstance(v, (list, tuple)) else [v]
