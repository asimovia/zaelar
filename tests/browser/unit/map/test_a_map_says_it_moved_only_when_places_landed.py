"""The map's end state is the map MOVING, never a map left on screen (operator's four principles, 2026-11-08).

`show`/`add` declare `updated changed`: `updated` is stamped only when places were pinned, and always moves, so a
second show in the same second still reads met while a show that found nothing reads UNMET over the old pins (the
old `places present` read met over them). A source he names («on Google Maps») adds that source's link per place to
the result, for that call only; the map itself stays OpenStreetMap.
"""
from __future__ import annotations

import pytest

from nucleo.circuit import spec, verify
from widgets.map import data as mp

_COORDS = {"griffith": (34.118, -118.300), "arena": (34.043, -118.267)}


@pytest.fixture
def fake(monkeypatch, tmp_path):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))

    def geocode(q, deadline=None):
        for k, (lat, lon) in _COORDS.items():
            if k in q.lower():
                return {"lat": lat, "lon": lon, "found": "Los Angeles"}
        return None
    monkeypatch.setattr(mp, "_geocode", geocode)
    monkeypatch.setattr(mp.time, "time", lambda: 1_790_000_000.25)     # every call inside ONE second


def _done(action, payload):
    dw = spec.render("map", action, payload)
    assert dw, f"map:{action} declares no renderable end state"
    return dw


def test_two_shows_in_one_second_both_read_met(fake):
    p1 = {"places": [{"name": "Griffith Observatory"}]}
    dw = _done("show", p1)
    assert mp.apply_action("show", p1)["ok"]
    assert verify.check(dw) is True
    p2 = {"places": [{"name": "Crypto.com Arena"}]}
    dw = _done("add", p2)
    assert mp.apply_action("add", p2)["ok"]
    assert verify.check(dw) is True, "a second write in the same second must still move `updated`"


def test_a_show_that_found_nothing_reads_unmet_over_the_old_pins(fake):
    assert mp.apply_action("show", {"places": [{"name": "Griffith Observatory"}]})["ok"]
    p = {"places": [{"name": "Nowhere Land"}]}
    dw = _done("show", p)
    assert not mp.apply_action("show", p)["ok"]
    assert verify.check(dw) is False, "the pins left on screen are not this request's outcome"


def test_a_named_source_adds_its_link_per_place_for_that_call_only(fake):
    got = mp.apply_action("show", {"places": [{"name": "Griffith Observatory"}], "source": "Google"})
    assert got["links"] == ["1. Griffith Observatory: https://www.google.com/maps/search/?api=1&query=34.118,-118.3"]
    assert "links" not in mp.apply_action("add", {"places": [{"name": "Crypto.com Arena"}]})
