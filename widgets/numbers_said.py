"""widgets/numbers_said.py — the numbers a text NAMES, for a matcher that must treat a number as identity.

«Paso 2» is not «Paso 1», «step 12» is not «step 120»: a matcher that scores words drops a digit as noise and lands on
the nearest passage. This reads every number a text names — a digit («2», «2º», «3rd», «1.250» as 1 and 250) or a
spoken number from the one table every reader of spoken numbers shares (`refs.number_words`: «segundo», «third»).
"""
from __future__ import annotations

import re

#: A digit may carry its ordinal mark: «3º»/«1ª» reach us as «3o»/«1a» (NFKD), typed «2nd»/«3ro» count the same.
#: The ONE pattern every reader of a written number uses (`refs` reads positions with it).
DIGIT_ORD = re.compile(r"(\d+)(?:o|a|er|ro|do|to|mo|vo|no|st|nd|rd|th)?")


def numbers_in(text) -> frozenset:
    """Every number `text` names, as ints (1-based for the spoken ones, as every manifest counts)."""
    from widgets.refs import _norm, number_words      # lazily: `refs` itself reads DIGIT_ORD from here
    words, out = number_words(), set()
    for t in _norm(text).split():
        m = DIGIT_ORD.fullmatch(t)
        if m or t in words:
            out.add(int(m.group(1)) if m else words[t])
    return frozenset(out)
