"""A sheet row that does not carry what he asked about is not news to him yet (search-buy-vinyl EN, 2026-10-14).

«Find me an original pressing of 'The Dark Side of the Moon' in good condition for under $70.» Then «are any of them
actually original pressings? and what condition are they in». Rows carrying a title and a price and nothing about
pressing or condition were offered to him three times as candidates.

What he asked about is read from his own words, never from a word list: the stems (six letters or more) of what he
said AFTER the commission that are stems of the commission itself — his requirements, said again. A row carries one
when its title names it or a fact of the row VERIFIES it (`hard_checks.status` yes/no: a «?» or a source stamp is not
an answer). Until a row carries at least half of them it is not owed to him. With nothing asked, nothing changes.
"""
from __future__ import annotations

import re

from search.asked import norm as _norm

#: Shorter words are function words in both product languages ("under", "about"): no requirement of his.
_MIN_LETTERS = 6
_STEM = 6


def _stems(text) -> set[str]:
    return {w[:_STEM] for w in re.findall(r"[a-z]{%d,}" % _MIN_LETTERS, _norm(text))}


def asked(commission: str, said) -> set[str]:
    """The requirements of `commission` that his LATER sentences asked about again. `said` is his sentences in
    order; the first one that names a requirement is the commission being made, so it asks nothing new — and neither
    does the commission's own text."""
    want = _stems(commission)
    out: set[str] = set()
    if not want:
        return out
    first = True
    for s in said or []:
        got = _stems(s) & want
        if not got:
            continue
        if first or _norm(s) == _norm(commission):
            first = False
            continue
        out |= got
    return out


def carries(item: dict, want: set[str]) -> bool:
    """Does this sheet row answer at least half of what he asked about?"""
    if not want:
        return True
    from widgets.results import hard_checks as H
    have = _stems((item or {}).get("title"))
    for f in (item or {}).get("facts") or []:
        if isinstance(f, dict) and H.status(f.get("value"))[0] in (H.YES, H.NO):
            have |= _stems(f.get("label")) | _stems(f.get("value"))
    return 2 * len(want & have) >= len(want)


def items_owed(goal: str, items: list[dict], said) -> list[dict]:
    """The sheet rows (dicts) that carry what he asked about since `goal` was commissioned."""
    want = asked(goal, said)
    return [i for i in items or [] if carries(i, want)]
