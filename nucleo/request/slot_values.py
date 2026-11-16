"""nucleo/request/slot_values.py — whether a slot of an act HAS a value (split from `send_task` by its file ceiling)."""
from __future__ import annotations


def filled(v) -> bool:
    """A slot's value is THERE: a non-blank text, a list with at least one non-blank item (several people), or any
    other value. Measured: `members: ["Ana", "Luis"]` was read as an empty slot and the send asked «to whom?» — twice."""
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, (list, tuple)):
        return any(filled(x) for x in v)
    return v is not None


def _each(v) -> list:
    """The values of a slot, one per person (a list) or the one."""
    return [x for x in v if filled(x)] if isinstance(v, (list, tuple)) else [v]
