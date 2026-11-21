"""A countdown his turn sets comes on screen; the timer's controls do not drag it back (V2-879, open row O6).

Measured in the lab sandbox (es+en, before and after V2-879's first cut): «pon un temporizador de 10 minutos» set the
timer — running, 600 s — and the card never appeared: `set` was classed a plain write (no effect declared), and a
write is deliberately not presented («it may run behind the screen on purpose», V2-773). A countdown's output cannot
happen off screen, so `set` and `start` DECLARE `present.mount` — the manifest's own field for an effect that cannot be
derived — and the turn's one door (`canvas_visibility.present`, `reason=producer-mount`, the arbiter's mount rule) brings
the card for them alone. `pause` and `reset` stay controls: no mount, and a show on them is still a drag.

Why not «every ok act on a closed card shows it»: measured on the catalogue, 165 offered acts are writes (agenda's
`add_meeting`, messaging's `archive`, contacts…); a default flip would open a card on every one of them.
"""
from __future__ import annotations


from nucleo.acts import visibility as cv
from widgets import effects as fx



def test_the_countdown_declares_that_it_lives_on_screen():
    assert fx.PRESENT_MOUNT in fx.of("timer", "set") and fx.PRESENT_MOUNT in fx.of("timer", "start")
    assert fx.PRESENT_MOUNT not in fx.of("timer", "pause") and fx.PRESENT_MOUNT not in fx.of("timer", "reset")


def test_the_one_door_brings_the_card_for_the_set_and_only_once():
    got = []
    emit = lambda k, label, extra: got.append((k, label, extra))   # noqa: E731
    assert cv.present("timer", reason="producer-mount", action="set", src="turn:e_1", known=[], emit=emit) is True
    assert got[-1][:2] == ("widget", "show") and got[-1][2]["action"] == "set"
    assert cv.present("timer", reason="producer-mount", action="set", src="turn:e_1", known=["timer"], emit=emit) is False
    assert cv.present("timer", reason="producer-mount", action="pause", src="turn:e_1", known=[], emit=emit) is False, \
        "a mount claimed over a control the app does not declare as one"
