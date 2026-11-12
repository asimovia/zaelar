"""Group A step 7 — what observability keeps says WHEN things happened.

A phone is recognised by its own shape (its digit count, whatever the grouping), a date by its fields in range, and
a time by nothing at all: «2026-11-12 10:30» was stored as «[PHONE]:30», and a stored session could not tell whether
the day of a meeting was the fault. Real phones, emails and full names of (invented) people are still never kept.
"""
from __future__ import annotations

import pytest

from observability import pii

NAMES = {}
for _n in ("Odalys Brezmes Quintanar", "Thaddeus Wrenfield"):
    _k = pii.norm(_n)
    NAMES[_k] = "[PERSON]"
    NAMES.update({w: "[PERSON]" for w in _k.split() if len(w) >= 3})


@pytest.mark.parametrize("said", [
    "quedamos el 2026-11-12 a las 10:30",
    "pon la cita el 12/11 a las 17.30",
    "el 12.11.2026 a las 17h30",
    "meeting on 11/12/2026 at 09:45",
    "start 2026-11-12T10:30:00",
])
def test_a_date_or_a_time_is_never_a_phone(said: str) -> None:
    kept = pii.tag(said, NAMES)
    assert "[PHONE]" not in kept
    for clock in ("10:30", "17.30", "17h30", "09:45", "T10:30:00"):
        if clock in said:
            assert clock in kept                          # a time names no one: kept as said


def test_a_year_and_a_small_count_are_kept() -> None:
    assert pii.tag("en 2026 somos 4 y llevamos 1.5 kg", NAMES) == "en 2026 somos 4 y llevamos 1.5 kg"


@pytest.mark.parametrize("phone", ["+34 612 345 678", "612345678", "612-34-56-78", "91.123.45.67", "(555) 123-4567",
                                   "+44 20 7946 0958"])
def test_a_real_phone_is_still_tagged(phone: str) -> None:
    said = f"Odalys Brezmes Quintanar dice que llames a Thaddeus Wrenfield al {phone} o a odalys.bq@example.org " \
           f"el 2026-11-12 a las 10:30"
    kept = pii.tag(said, NAMES)
    assert "[PHONE]" in kept and "[EMAIL]" in kept and "10:30" in kept
    digits = "".join(c for c in phone if c.isdigit())
    for leak in ("Odalys", "Brezmes", "Quintanar", "Thaddeus", "Wrenfield", "odalys.bq", "example.org", phone):
        assert leak not in kept
    assert digits not in "".join(c for c in kept if c.isdigit())   # no run of the phone's digits survives anywhere
