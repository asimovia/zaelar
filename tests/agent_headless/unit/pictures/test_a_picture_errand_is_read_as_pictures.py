"""An errand whose deliverable is pictures is read as `imagenes`, never a results sheet (2.500).

show-real-photo-of-a-new-car__us (sandbox 20261011-115914-en): eight Amalfi photos on screen, «are they really the
Amalfi? … I'd rather be sure it's not the Roma» escalated as `lista` — a results table opened beside the viewer.
The surface vocabulary has a value for pictures, the brief's question offers it, and when his words were unsure
the screen decides: a correction of what we just did while the viewer holds pictures is about those pictures.
"""
from __future__ import annotations

from nucleo import surfaces as S

from ._brief import brief, viewer_on_screen


def test_pictures_are_a_surface_of_their_own():
    assert S.normalize("images") == S.IMAGES == S.normalize("fotos")
    assert S.IMAGES in S.question()["criteria"]
    assert not S.opens_sheet(S.IMAGES) and S.not_a_sheet(S.IMAGES) and S.delivers_pictures(S.IMAGES)
    assert S.pick("lista", S.IMAGES) == S.IMAGES, "the brief's pictures reading beats a declared sheet"
