"""V2-209 — «Aquí lo tienes» over a card with nothing in it, and the phrase is OURS.

Measured on `book-hotel-night-known__es` (2026-08-20 13:49):

    TESTER  Resérvame una noche en el Hotel Palacio de la Merced para el 30 de agosto.
    ZAELAR  Voy a mirarlo en su web y te lo dejo a punto.
    TESTER  Vale, avísame.
    ZAELAR  Aquí lo tienes.          ← la tarea seguía `working`, sin una habitación ni un precio

Judge: «alucinación de éxito … decir "Aquí lo tienes" cuando el navegador está bloqueado y no se ha obtenido
nada». The model never wrote that sentence — `show_ack` did, the canned ack for a turn whose only act was
opening a surface. Second time a canned phrase of ours is the thing that lied (V2-176 front 1 was «Hecho.»
for a task that had just STARTED).

`_surface_is_empty` has answered this question since 2026-08-17 and only STAMPED it on the observability row;
the ack kept asserting a delivery. What is new is the cost being measured, and the browser case the generic
check cannot answer: a browser card's saved state is NOT empty (it holds the task), so «is the state empty»
replies «there is something to show» about work in progress.
"""
import pytest

from voice.engine.core import langs


@pytest.fixture()
def lang():
    return langs.current_language()


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)


@pytest.fixture()
def navtasks():
    from widgets.navegador import tasks
    tasks._tasks.clear()
    yield tasks
    tasks._tasks.clear()


def test_both_languages_carry_the_phrase():
    """A missing string would silently fall back to the asserting one — the failure would look like the bug
    coming back rather than a missing translation."""
    seen = 0
    for code in ("es", "en"):
        spec = langs.spec(code)
        assert getattr(spec, "show_ack_empty", "").strip(), code
        assert spec.show_ack_empty != spec.show_ack, code
        seen += 1
    assert seen == 2          # y que el bucle CORRIÓ: un test que no mira nada pasa igual


def test_the_empty_ack_CLAIMS_NOTHING(lang):
    """REGRESIÓN MEDIDA, y mía (V2-209 addenda). La primera versión de esta frase acababa en «sigo con ello», y
    `cancel-subscription-before-charge__es` —el único 5/5 del tablero, que vivía justo de NO afirmar nada— cayó a
    2/5: «narró que seguía cancelando en la cuenta del usuario sin que el mecanismo lo respaldara».

    Cambiar una afirmación falsa por otra más pequeña no es arreglarla: es hacerla más fácil de colar. Este ack
    dice lo que PASÓ (se abrió, está vacío) y nada más — lo que esté o no en marcha lo dicen el estado y la línea
    de espera, que sí lo saben."""
    for spec in (langs.spec("es"), langs.spec("en")):
        low = spec.show_ack_empty.lower()
        for claim in ("sigo con ello", "sigo en ello", "still on it", "working on it", "en marcha"):
            assert claim not in low, spec.show_ack_empty
