"""A widget's name is the same name in the plural (App Review recording 2026-11-16: «open my activities» opened
nothing, «open activity» did — «activities» is not the alias «activity», and the voice tolerance put it at 0.78, under
its 0.84 cutoff). The resolver folds grammatical number on both sides, English and Castilian, on a SECOND pass: an
exact name always wins first, so a plural can never take a word another widget or surface owns exactly."""
import pytest

from widgets import runtime as rt


@pytest.mark.parametrize("said,card", [
    ("open my activities", "activity"), ("open activity", "activity"), ("abre mis actividades", "activity"),
    ("show my contacts", "contactos"), ("open the timers", "timer"), ("abre mis chats", "mensajeria"),
])
def test_singular_and_plural_name_the_same_widget(said, card):
    assert rt.identify(said).get("match") == card


def test_an_exact_name_beats_a_folded_one():
    # «chat» is the wall (a system surface) exactly; Messages owns «chats». Folding first would steal the wall.
    r = rt.identify("abre el chat")
    assert r.get("system") == "chat" and r.get("match") is None


@pytest.mark.parametrize("a,b", [("activity", "activities"), ("actividad", "actividades"), ("note", "notes"),
                                 ("reloj", "relojes"), ("contacto", "contactos"), ("message", "messages")])
def test_the_fold_is_the_same_for_both_numbers(a, b):
    assert rt._sing(a) == rt._sing(b)


def test_the_fold_never_widens_into_an_inner_word():
    # Word-aligned on both sides: «activityfeed» is not «activity».
    assert rt.identify("open activityfeed").get("match") is None
