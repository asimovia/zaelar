"""V2-227 scope A — WHERE the operator will look, decided when COMMISSIONED and not when delivered.

Operator, 2026-08-20: «if the worker takes a long time, the user gets bored and the experience is bad. They need to see IN REAL
TIME what is happening». A worker can take seven minutes, and today the surface where the response will land is only
chosen when the response ALREADY exists — which is exactly too late to open it beforehand and pour progress into it.
Without this field, the process tab is an empty tab.

Three rules, each one enforced because of its opposite failure:
  1. it is decided when COMMISSIONED (otherwise there is nothing to open while work is in progress);
  2. CLOSED vocabulary of five values (a free-form string leads to a taxonomy nobody maintains, and the
     frontend ends up guessing);
  3. it is decided ONCE (changing surfaces halfway through moves what the operator is ALREADY looking at).

And under the Brain Workers doctrine this is a RESOURCE: it cannot know about hotels, cars, or houses.
Nothing in this module knows a domain, and nothing can learn one.
"""

import pytest

from nucleo import surfaces


# ── the vocabulary, which is what prevents this from drifting ─────────────────────────────────────────────────
def test_there_are_exactly_seven_and_no_more():
    # V2-644 added `informe` (a written thing you READ, delivered into the documento sheet); the photo round
    # (2026-10-11) added `imagenes` (pictures, delivered into the photo viewer) — seven now, and this pin is what
    # makes the next addition a deliberate decision too.
    assert surfaces.SURFACES == ("lista", "item", "informe", "widget", "voz", "silenciosa", "imagenes")


@pytest.mark.parametrize("said,expected", [
    ("lista", "lista"), ("LISTA", "lista"), ("listado", "lista"), ("results", "lista"),
    ("item", "item"), ("ficha", "item"), ("detalle", "item"),
    ("informe", "informe"), ("report", "informe"), ("dossier", "informe"),
    ("widget", "widget"), ("app", "widget"),
    ("voz", "voz"), ("voice", "voz"),
    ("silenciosa", "silenciosa"), ("none", "silenciosa"),
])
def test_the_wording_maps_onto_the_same_six(said, expected):
    assert surfaces.normalize(said) == expected


def test_something_outside_the_vocabulary_is_NOT_invented_as_a_sixth():
    """Returns "" rather than the default value: the caller must be able to distinguish «said nothing» from «said something
    we do not understand», because only the latter warrants a warning."""
    assert surfaces.normalize("pantalla completa en 3D") == ""
    assert surfaces.normalize(None) == ""


# ── resolution, which is the fallback for entry points where nobody declared anything ─────────────────────────
def test_what_the_brain_declared_wins():
    assert surfaces.resolve("item", kind="web") == "item"


@pytest.mark.parametrize("kind,expected", [
    ("web", "lista"),          # browsing ends up in something you look at
    ("research", "lista"),
    ("code", "widget"),        # the widget generator: its outcome IS a widget
    ("generic", "voz"),
    ("", "voz"),
])
def test_and_if_nobody_said_anything_it_comes_from_the_KIND(kind, expected):
    """Auto-resume, confirm-gate, cluster peers, and the Whisper enter through the same door without declaring anything.
    A commission without a surface cannot be left without a screen."""
    assert surfaces.resolve(None, kind=kind) == expected


def test_an_UNKNOWN_word_falls_back_instead_of_breaking():
    assert surfaces.resolve("pantalla completa en 3D", kind="web") == "lista"


# ── rule 3, which protects the operator who is already looking ───────────────────────────────────────────────
class _Rec:
    def __init__(self, kind="generic", surface=""):
        self.kind, self.surface = kind, surface


def test_it_is_stamped_the_first_time():
    r = _Rec(kind="web")
    assert surfaces.set_once(r, "item") == "item" and r.surface == "item"


def test_and_NEVER_re_decided():
    """Changing surfaces halfway through is not a correction: it moves what the operator already has in front of them. If a later step
    disagrees, the commission decision is what needs fixing."""
    r = _Rec(kind="web", surface="lista")
    assert surfaces.set_once(r, "widget") == "lista" and r.surface == "lista"


def test_stamping_without_a_declaration_still_leaves_one():
    r = _Rec(kind="code")
    assert surfaces.set_once(r, None) == "widget"


def test_the_sheet_opens_only_for_the_two_that_show_things():
    assert [s for s in surfaces.SURFACES if surfaces.opens_sheet(s)] == ["lista", "item"]

