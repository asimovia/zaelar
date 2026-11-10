"""Every CRITICAL event of the vocabulary has at least one door that emits it (V2-873, node 2.1663).

A critical errand class read unsure no longer asks at birth (node 2.884): what makes that safe is that money and
accounts are still asked where they really happen — at the exit doors that declare a critical event. A critical
event nobody emits is a guard nobody stands at; this holds the vocabulary to its doors. The errand classes are
emitted by the one worker door as `errand.<class>` (`acts/errand.asks_first`), the rest by name.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from nucleo.acts import errand
from nucleo.events import vocabulary

_ROOT = Path(__file__).resolve().parents[3]
_PRODUCT = ("nucleo", "widgets", "connectors", "voice", "server")


def _product_text() -> str:
    out = []
    for top in _PRODUCT:
        for f in (_ROOT / top).rglob("*.py"):
            if f.name != "vocabulary.py" and "/tests/" not in str(f):
                out.append(f.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(out)


_TEXT = _product_text()
_CRITICAL = [e.name for e in vocabulary.TYPES if e.level == "critical"]


def test_there_are_critical_events():
    assert {"payment.authorize", "errand.moves_money", "errand.account_change"} <= set(_CRITICAL)


@pytest.mark.parametrize("name", _CRITICAL)
def test_a_critical_event_has_a_door_that_emits_it(name):
    family, _, kind = name.partition(".")
    by_name = f'"{name}"' in _TEXT
    by_family = family == "errand" and kind in dict(errand._CLASSES) and 'f"errand.{cls}"' in _TEXT
    assert by_name or by_family, f"«{name}» is critical and no door emits it: the exit guard it promises does not exist"
