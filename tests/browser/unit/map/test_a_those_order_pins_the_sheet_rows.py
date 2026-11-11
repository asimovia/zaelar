"""«Put those coffee shops on the map» pins the SHEET's rows, never places the model named itself (V2-879 O1).

Measured in the sandbox, es and en, with zero rows on the sheet and its search still running: the order reached the map
as `show` with eight coffee shops the model named from its own knowledge, as plain strings, and the turn said «Te las
pongo en el mapa». The class: the map's `show` took its places from anywhere. Now `show`/`add` take `rows` (numbers,
titles or "all") and resolve them from the sheet's own data; a free place over a sheet on screen or still filling is
kept only when it IS a row of it or he named it — anything else is refused, naming what the sheet holds, and nothing
is painted.
"""
from __future__ import annotations

import pytest

from nucleo import his_words
from widgets.map import data as mp, sheet as msheet
from widgets.results import data as results

_COORDS = {"lobo": (40.41, -3.70), "toma": (40.42, -3.71), "hola": (40.43, -3.69), "retiro": (40.415, -3.684),
           "griffith": (34.118, -118.300)}
CAFES = [{"title": "Café Lobo", "subtitle": "Calle Mayor 1, Madrid", "url": "https://example.org/lobo", "kind": "place"},
         {"title": "Toma Café", "subtitle": "Calle Palma 49, Madrid", "url": "https://example.org/toma", "kind": "place"},
         {"title": "Hola Coffee", "subtitle": "Calle Doctor Fourquet 33, Madrid", "url": "https://example.org/hola",
          "kind": "place"}]


@pytest.fixture
def world(monkeypatch, tmp_path):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(results.store, "DATA_DIR", str(tmp_path), raising=False)

    def geocode(q, deadline=None):
        for k, (lat, lon) in _COORDS.items():
            if k in q.lower():
                return {"lat": lat, "lon": lon, "found": "Madrid"}
        return None
    monkeypatch.setattr(mp, "_geocode", geocode)
    state = {"open": None, "live": set()}
    monkeypatch.setattr(msheet, "_open_sheets", lambda: state["open"])
    monkeypatch.setattr(msheet, "_live_sheets", lambda: set(state["live"]))
    his_words.reset()
    yield state
    his_words.reset()


def _seed(rows, sid="cafes"):
    res = results.apply_action("present", {"sheet": sid, "title": "Cafeterías en Madrid", "items": rows})
    assert res.get("ok") is not False, res
    assert [i["title"] for i in results.view_data(sid)["items"]] == [r["title"] for r in rows], "the seed did not land"


def _pins():
    return [p["name"] for p in mp.view_data()["places"]]


@pytest.mark.parametrize("ref", ["all", ["all"], [1, 2, 3], ["Café Lobo", "Toma Café", "Hola Coffee"]])
def test_rows_are_read_from_the_sheet_he_is_looking_at(world, ref):
    _seed(CAFES)
    world["open"] = {"cafes"}
    got = mp.apply_action("show", {"rows": ref})
    assert got["ok"] and got["from_sheet"] == "Cafeterías en Madrid", got
    assert _pins() == ["Café Lobo", "Toma Café", "Hola Coffee"]
    assert [p["url"] for p in mp.view_data()["places"]] == [r["url"] for r in CAFES], "the row's own link travels"


def test_one_row_by_number_and_a_row_that_is_not_there_is_said(world):
    _seed(CAFES)
    world["open"] = {"cafes"}
    got = mp.apply_action("show", {"rows": [2, 9]})
    assert got["ok"] and _pins() == ["Toma Café"] and got["unknown_rows"] == ["9"], got


def test_rows_over_an_empty_sheet_paint_nothing_and_say_so(world):
    """The O1 shape: the search is running and has delivered nothing. The map is not touched."""
    mp.apply_action("show", {"places": [{"name": "Griffith Observatory", "address": "Los Angeles"}]})
    _seed([], sid="cafes")
    world["open"], world["live"] = {"cafes"}, {"cafes"}
    before = mp.view_data()
    got = mp.apply_action("show", {"rows": "all"})
    assert got["ok"] is False and got["sheet_rows"] == 0 and "still going" in got["detail"], got
    assert mp.view_data() == before, "a refused show changed the map"


@pytest.mark.parametrize("lang_names", [
    ["Café de Oriente", "La Bicicleta", "Federal Café", "Toma Café"],        # es: eight of them, measured; four here
    ["Blue Bottle", "Stumptown", "Intelligentsia"],                          # en
])
def test_places_of_the_models_own_are_no_stand_in_for_rows_that_do_not_exist(world, lang_names):
    _seed([], sid="cafes")
    world["open"], world["live"] = {"cafes"}, {"cafes"}
    got = mp.apply_action("show", {"places": lang_names, "title": "Cafeterías"})
    assert got["ok"] is False and got["error"] == "not_a_sheet_row", got
    assert got["refused"] == lang_names and _pins() == []


def test_a_free_place_that_is_a_row_becomes_that_row(world):
    _seed(CAFES)
    world["open"] = {"cafes"}
    got = mp.apply_action("show", {"places": ["toma café", "Bar Inventado"]})
    assert got["ok"] and _pins() == ["Toma Café"] and got["refused"] == ["Bar Inventado"], got
    assert mp.view_data()["places"][0]["url"] == "https://example.org/toma"


def test_a_place_he_named_is_his_even_with_a_sheet_on_screen(world):
    _seed(CAFES)
    world["open"] = {"cafes"}
    his_words.note("y enséñame el Retiro en el mapa")
    got = mp.apply_action("show", {"places": [{"name": "Retiro", "address": "Madrid"}]})
    assert got["ok"] and _pins() == ["Retiro"], got


def test_with_no_sheet_on_screen_free_places_stay_as_they_were(world):
    """«show me Griffith on a map», or a plan the turn laid out itself: no sheet is the referent."""
    _seed(CAFES)                                   # a sheet on disk, neither open nor filling
    got = mp.apply_action("show", {"places": [{"name": "Griffith Observatory", "address": "Los Angeles"}]})
    assert got["ok"] and _pins() == ["Griffith Observatory"], got


@pytest.mark.parametrize("named", ["Cafeterías en Madrid", "cafes", "results::cafes"])
def test_a_sheet_named_by_its_title_or_id_is_that_sheet(world, named):
    """Measured (en): the model sent `sheet` with the sheet's TITLE; read as an id it named an empty sheet that does
    not exist, and four real rows were refused."""
    _seed(CAFES)
    world["open"] = {"cafes"}
    got = mp.apply_action("show", {"places": ["Toma Café"], "sheet": named})
    assert got["ok"] and _pins() == ["Toma Café"], got


def test_a_sheet_name_that_matches_no_sheet_invents_none(world):
    _seed(CAFES)
    world["open"] = {"cafes"}
    got = mp.apply_action("show", {"rows": [1], "sheet": "Some other search"})
    assert got["ok"] and _pins() == ["Café Lobo"], got
