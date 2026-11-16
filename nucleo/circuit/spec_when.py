"""nucleo/circuit/spec_when.py — a CONDITIONAL clause of a declared end state (split from `spec` by its file ceiling).

A clause of a template's list with `"when": "{key}"` is kept only when that field of the call came filled: a group
asked WITH people must hold them (replay over 65c0f7e63: an empty group was judged `met`), a group asked alone need not.
"""
from __future__ import annotations


def kept(clause: dict, payload: dict, placeholder) -> dict | None:
    """The clause without its `when`, or None when the field it names came empty."""
    m = placeholder.match(str(clause.get("when") or ""))
    val = (payload or {}).get(m.group(1)) if m else None
    if not (str(val).strip() if isinstance(val, str) else bool(val)):
        return None
    return {k: v for k, v in clause.items() if k != "when"}


def kept_all(items: list, payload: dict, placeholder) -> list:
    """A template's list with its conditional clauses resolved: kept (without `when`) or left out."""
    out = []
    for v in items:
        if isinstance(v, dict) and "when" in v:
            v = kept(v, payload, placeholder)
            if v is None:
                continue
        out.append(v)
    return out
