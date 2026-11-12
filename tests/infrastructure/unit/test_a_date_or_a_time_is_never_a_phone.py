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


def test_a_small_count_and_a_decimal_are_kept_and_a_lone_year_is_a_number() -> None:
    """A year standing alone cannot be told from a PIN by its shape (birth years are the commonest PINs): it is tagged."""
    assert pii.tag("somos 4 y llevamos 1.5 kg a las 17.30 del 12", NAMES) == "somos 4 y llevamos 1.5 kg a las 17.30 del 12"
    assert pii.tag("en 2026 somos 4", NAMES) == "en [NUMBER] somos 4"
    for said, secret in (("PIN 2010", "2010"), ("el pin es 1987 y la clave 4821", "1987"), ("code 1999", "1999")):
        assert secret not in pii.tag(said, NAMES), said


@pytest.mark.parametrize("said", ["mi teléfono es 12 34 56 78", "llama al 91 12 34 56", "call 12 34 56 78 now",
                                  "el código es 12 34 56", "son el 1234 5678", "ring 22-33-44-55",
                                  "612 34 56 78 699 11 22 33", "apunta 91 123 45 67 y 93 765 43 21, y el 600 11 22 33",
                                  "card 4111 1111 1111 1111 22 33", "+34 612 34 56 78 +44 20 7946 0958"])
def test_a_number_said_in_groups_is_never_kept(said: str) -> None:
    """Measured 2026-11-12: phones said in pairs (eight digits, as in several countries) and codes said in groups were
    stored as said; two phones in one breath made one run past fifteen digits, the shape refused it and the pairs of
    each were kept. Disarm: the floor back at nine digits → the pairs go red; a ceiling of fifteen → the long runs."""
    kept = pii.tag(said, NAMES)
    assert "[PHONE]" in kept or "[NUMBER]" in kept, kept
    assert sum(c.isdigit() for c in kept) == 0, kept          # not one digit of it survives


def test_no_digit_of_a_grouped_number_survives_whatever_surrounds_it() -> None:
    """The class, swept: every grouping (pairs, threes, two phones in one breath, eighteen digits by pairs), every
    separator, glued to what comes before («nº», «tel:», «(», «+») and after («:», «)», «.», «/3»). Seeded, so it is
    the same sweep every run. Disarms seen red: a ceiling of fifteen digits; the tail refusing a bare «:»; the head
    refusing to start after a letter («nº612…»)."""
    import random
    rnd, leaks = random.Random(7), []
    for sizes in ((3, 2, 2, 2), (2, 2, 2, 2), (3, 3, 3), (4, 4), (3, 3, 4), (9,), (1, 3, 3, 4),
                  (3, 2, 2, 2, 3, 2, 2, 2), (2,) * 9):
        for sep in (" ", "-", ".", "  ", " - "):
            for pre in ("", "al ", "(", "tel:", "tel: ", "+", "+34 ", "nº", "n.º ", "tlf"):
                for suf in ("", ".", ",", ":", ";", ")", " y luego", "?", " h", "/3", "-", ": apunta"):
                    digits = iter("".join(rnd.choice("123456789") for _ in range(sum(sizes))))
                    said = pre + sep.join("".join(next(digits) for _ in range(n)) for n in sizes) + suf
                    kept = pii.tag(f"llama {said} hoy", NAMES)
                    if sum(c.isdigit() for c in kept) > sum(c.isdigit() for c in pre + suf):
                        leaks.append((said, kept))
    assert not leaks, leaks[:5]


def test_the_genome_drops_what_these_shapes_name() -> None:
    """`genome/privacy` shares the shapes and DROPS: a gene carrying a grouped number or a four-digit code never leaves."""
    from genome import privacy
    for value in ("12 34 56 78", "PIN 2010", "91 12 34 56"):
        assert privacy.reason({"key": "alias", "value": value}, set()), value
    assert privacy.reason({"key": "alias", "value": "the kitchen light"}, set()) == ""


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
