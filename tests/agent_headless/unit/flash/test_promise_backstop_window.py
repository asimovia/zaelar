"""V2-132 — a promise whose request was made a turn or two earlier.

`find-theatre-tickets__es` described the task across TWO turns: «get me two tickets for the musical The Lion
King» and then, after zaelar correctly asked for the missing detail, «this Saturday, the afternoon show». The
promise («give me a moment while I look into it») landed on the second one, whose text on its own describes no
task — so the promise backstop, which only ever looked at THIS turn, could not fire. Eight turns of narrating a
search that had never started, with `signals: empty` in the mechanism report. (A7 retired the window lookback that
answered it — an errand opens by the model's call or a sure verdict; what stays is the catalogue's reading.)

Two independent gaps, both measured on the transcript before touching anything:
  · `_PROMISE_RE` did not know «me pongo A», «estoy con ello», «sigo con ello» — the plainest ways to say it.
  · buying tickets had no category in the site catalog, so the task classified as `generic`: a worker with NO
    browser, which is why the `widget` signal could not possibly fire.
"""
import pytest

from nucleo.flash import site_catalog as sc


@pytest.mark.parametrize("text", [
    "de primero pedimos entradas para compartir",   # a starter on a menu
    "guárdame el ticket de la compra",              # a receipt
])
def test_the_other_meanings_of_entrada_and_ticket_stay_out(text):
    assert sc.category_of(text) is None
