"""The figures a tool's output carries, as numbers (V2-941, v3.1 §1.10 bis): what a TEXT evidence holds, so a claim
against an unstructured read can be checked by value. It reads a tool's output, never what the person said; it walks
characters — no regular expression, no word table.

A run of digits with its separators is read both ways a language writes numbers — a point or a comma as the decimal
mark, the other one (or a space, an apostrophe) grouping thousands — and every reading that is well formed counts:
`1.234` is 1.234 and 1234, `22,5` is 22.5, `1,234.5` is 1234.5. A source in another language than his is read too.
A figure written in words is not a figure here.
"""
from __future__ import annotations

GROUP = "\u0020\u00a0\u202f'\u2019"   # characters that only group thousands: a space, two no-break spaces, two quotes
MARKS = ".,"
MINUS = ("-", "−")


def _runs(text: str) -> list[tuple[str, bool]]:
    out, i, n = [], 0, len(text)
    while i < n:
        if not text[i].isdigit():
            i += 1
            continue
        neg = i > 0 and text[i - 1] in MINUS and (i < 2 or not text[i - 2].isdigit())
        j = i
        while j < n and (text[j].isdigit() or (text[j] in MARKS + GROUP and j + 1 < n and text[j + 1].isdigit())):
            j += 1
        out.append((text[i:j], neg))
        i = j
    return out


def _read(run: str, decimal: str) -> float | None:
    """`run` with `decimal` as the decimal mark; None when it is not well formed that way."""
    group = "," if decimal == "." else "."
    head, _, tail = run.rpartition(decimal) if decimal in run else (run, "", "")
    if decimal in run:
        if run.count(decimal) > 1 or any(c in MARKS + GROUP for c in tail):
            return None
    else:
        head, tail = run, ""
    parts = head
    for g in (group, *GROUP):
        parts = parts.replace(g, "|")
    chunks = parts.split("|")
    if len(chunks) > 1 and (not 1 <= len(chunks[0]) <= 3 or any(len(c) != 3 for c in chunks[1:])):
        return None
    digits = "".join(chunks)
    if not digits.isdigit() or (tail and not tail.isdigit()):
        return None
    return float(digits + ("." + tail if tail else ""))


def _readings(run: str) -> set[float]:
    got = {x for x in (_read(run, "."), _read(run, ",")) if x is not None}
    if got or not any(g in run for g in GROUP):
        return got
    pieces = run                                     # «5 10» is two figures, not a malformed thousand
    for g in GROUP:
        pieces = pieces.replace(g, "|")
    return {x for p in pieces.split("|") if p for x in _readings(p)}


def figures(text: str) -> tuple[float, ...]:
    out: list[float] = []
    for run, neg in _runs(str(text or "")):
        for v in sorted(_readings(run)):
            v = -v if neg else v
            if v not in out:
                out.append(v)
    for v in durations(text):                        # a duration is also the same time in its other units
        if v not in out:
            out.append(v)
    return tuple(out)


#: a duration's units in seconds, in the order of the packs' `duration_units`: hours, minutes, seconds
SECONDS = (3600.0, 60.0, 1.0)
#: what may stand between one part of a duration and the next («1 h 20 min», «1 hora y 20 minutos», «1h, 20m»)
JOIN_MAX = 5
_units_cache: list = []


def _units() -> tuple:
    """The unit names of every pack, by unit: a source is read whatever its language (`LangSpec.duration_units`)."""
    if not _units_cache:
        from i18n import langs
        names: tuple = (set(), set(), set())
        for spec in langs.supported():
            for i, group in enumerate(tuple(getattr(spec, "duration_units", ()) or ())[:3]):
                names[i].update(str(w).casefold() for w in group)
        _units_cache.append(tuple(frozenset(n) for n in names))
    return _units_cache[0]


def _word_after(text: str, j: int) -> tuple[str, int]:
    """The word right after position `j` (spaces and a dot skipped): its letters, and where it ends."""
    n = len(text)
    while j < n and (text[j] in GROUP or text[j] == " "):
        j += 1
    k = j
    while k < n and text[k].isalpha():
        k += 1
    return text[j:k].casefold(), k


def durations(text: str) -> tuple[float, ...]:
    """Every duration the text writes with its units — «1 h 20 min», «80 minutos», «1,5 horas» — as the same time in
    hours, minutes and seconds. Characters only: a figure, then a word the packs name as a unit."""
    text, units = str(text or ""), _units()
    out: list[float] = []
    total, last_unit, end = 0.0, -1, -1
    i = 0
    for run, _neg in _runs(text):
        at = text.find(run, i)
        i = at + len(run)
        word, k = _word_after(text, i)
        unit = next((u for u, names in enumerate(units) if word and word in names), None)
        values = sorted(_readings(run))
        if unit is None or not values:
            continue
        if end >= 0 and unit > last_unit and at - end <= JOIN_MAX:
            total += values[0] * SECONDS[unit]      # the next part of the same duration
        else:
            if end >= 0:
                out.extend(_as_units(total))
            total = values[0] * SECONDS[unit]
        last_unit, end = unit, k
    if end >= 0:
        out.extend(_as_units(total))
    return tuple(dict.fromkeys(out))


def _as_units(seconds: float) -> tuple[float, ...]:
    return tuple(round(seconds / s, 6) for s in SECONDS)


def percents(text: str) -> tuple[float, ...]:
    """The figures the text wrote as a percent: a `%` right after the figure (a space between them allowed)."""
    text = str(text or "")
    out: list[float] = []
    i, n = 0, len(text)
    for run, neg in _runs(text):
        at = text.find(run, i)
        j = at + len(run)
        i = j
        while j < n and text[j] in GROUP:
            j += 1
        if j < n and text[j] == "%":
            for v in sorted(_readings(run)):
                v = -v if neg else v
                if v not in out:
                    out.append(v)
    return tuple(out)
