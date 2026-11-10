"""genome/privacy.py — no gene names anyone (V2-859 T564).

Deterministic, at export, BEFORE anything leaves: a gene is dropped if any text it carries (its key and its value —
never its evidence, which is not exported) contains something this agent knows as PARTICULAR:

  · a name it knows: every name of every contact (and each word of it, three letters or more), and the names of
    the memory's concept hubs;
  · a SHAPE that only a particular thing has: an email, a phone, a URL or a path in one, a number of three digits
    or more, a numeric date.

The shapes are shapes, not words: nothing here is a vocabulary of any language. Dropping too much costs one gene
that another agent will learn on its own; letting one name through cannot be taken back — so every doubt drops.
"""
from __future__ import annotations

from loguru import logger

from observability.pii import SHAPES as _SHAPES, norm as _norm   # one set of shapes for every privacy filter


def known() -> set[str]:
    """What this agent knows as particular, normalised. Read to DROP, never to export. Never raises."""
    out: set[str] = set()
    try:
        from widgets import directory
        for c in directory._contacts():
            for name in directory.names(c):
                n = _norm(name)
                if n:
                    out.add(n)
                    out.update(w for w in n.split() if len(w) >= 3)
    except Exception as e:  # noqa: BLE001 — no address book: the shapes still guard
        logger.debug(f"genome: contacts unreadable for the privacy filter ({e!r})")
    try:
        from memory import api as memory
        out.update(n for n in (_norm(x) for x in memory.concept_names(200)) if n)
    except Exception as e:  # noqa: BLE001 — no memory: the shapes and the contacts still guard
        logger.debug(f"genome: concept names unreadable for the privacy filter ({e!r})")
    return out


def _texts(obj) -> list[str]:
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [t for k, v in obj.items() for t in (_texts(k) + _texts(v))]
    if isinstance(obj, (list, tuple)):
        return [t for v in obj for t in _texts(v)]
    return []


def reason(gene: dict, particulars: set[str]) -> str:
    """'' when the gene names nothing particular, else what it named (the KIND, never the value)."""
    for text in _texts([gene.get("key"), gene.get("value")]):
        for kind, pat in _SHAPES:
            if pat.search(text):
                return kind
        padded = f" {_norm(text)} "
        if any(f" {p} " in padded for p in particulars):
            return "known name"
    return ""


def keep(genes: list[dict], particulars: set[str] | None = None) -> tuple[list[dict], dict[str, int]]:
    """The genes that may leave, and how many were dropped by kind."""
    particulars = known() if particulars is None else particulars
    kept, dropped = [], {}
    for g in genes:
        why = reason(g, particulars)
        if why:
            dropped[why] = dropped.get(why, 0) + 1
        else:
            kept.append(g)
    return kept, dropped
