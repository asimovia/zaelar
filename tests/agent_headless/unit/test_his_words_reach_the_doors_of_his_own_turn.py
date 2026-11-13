"""His words are his from the moment his turn is born — a door that runs INSIDE that turn reads them.

Measured on the demo sandbox (2026-11-13, step W1): «put griffith observatory, mount baldy and the getty on a map»
over a results sheet already on screen — the map refused all three («not_a_sheet_row»): over a sheet it keeps a free
place only when HE named it (`widgets/map/sheet.judge_free` → `nucleo/his_words`), and his words were recorded only when
the turn CLOSED, after every tool of the turn had run. The class: any door that asks «did he ask for this?» during the
turn that asked. His words are now noted when the turn's request is born (`nucleo/request/model.begin`).

Disarm: drop the `his_words.note` in `model.begin` → red.
"""
from __future__ import annotations

import time

from nucleo import his_words
from nucleo.request import model

SHEET = {"title": "27-inch 4K monitors", "live": False,
         "items": [{"title": "Dell S2722QC 27 4K"}, {"title": "LG 27UP850N-W"}]}


def test_his_words_are_readable_as_soon_as_his_turn_is_born():
    his_words.reset()
    t0 = time.time()
    model.begin("put griffith observatory, mount baldy and the getty on a map")
    assert his_words.since(t0) == ["put griffith observatory, mount baldy and the getty on a map"]


def test_the_map_keeps_the_places_he_named_this_turn_over_a_sheet_on_screen():
    from widgets.map import sheet
    his_words.reset()
    model.begin("put griffith observatory, mount baldy and the getty on a map")
    kept, refused = sheet.judge_free([{"name": "Griffith Observatory"}, {"name": "Mount Baldy"},
                                      {"name": "Santa Monica Pier"}], SHEET)
    assert [p.get("name") for p in kept] == ["Griffith Observatory", "Mount Baldy"]
    assert refused == ["Santa Monica Pier"]                 # a place of the model's own is still refused


def test_a_place_he_named_is_his_when_the_model_completes_its_name():
    """Demo sandbox 2026-11-13, W1 on b137: he said «the getty», the model wrote «The Getty Center, 1200 Getty Center
    Dr…», and over the monitors sheet the third pin was refused as the model's own — two pins, and «Done.».
    A name that BEGINS with a name he said where his phrase paused is his. Disarm: drop the prefix rule in
    `widgets/map/sheet._said_by_him` → red."""
    from widgets.map import sheet
    his_words.reset()
    model.begin("put griffith observatory, mount baldy and the getty on a map")
    kept, refused = sheet.judge_free([{"name": "The Getty Center, 1200 Getty Center Dr, Los Angeles, CA"},
                                      {"name": "Griffith Observatory, 2800 E Observatory Rd"},
                                      {"name": "Mount Baldy, San Gabriel Mountains, CA"},
                                      {"name": "Santa Monica Pier"}], SHEET)
    assert len(kept) == 3 and refused == ["Santa Monica Pier"], refused
    his_words.reset()
    model.begin("put griffith on the map")                  # a verb before the name does not hide it
    assert sheet.judge_free([{"name": "Griffith Observatory"}], SHEET)[1] == []


def test_a_word_inside_a_longer_phrase_names_no_place():
    """The V2-879 O1 shape stays shut with his sentence on record: «coffee» inside «those coffee shops» starts nothing,
    so the coffee shops the model names itself over a sheet are still refused."""
    from widgets.map import sheet
    his_words.reset()
    model.begin("put those coffee shops on the map")
    kept, refused = sheet.judge_free([{"name": "Blue Bottle Coffee"}, {"name": "Coffee Bean & Tea Leaf"},
                                      {"name": "Stumptown"}], SHEET)
    assert kept == [] and len(refused) == 3
    his_words.reset()
    model.begin("ponme esas cafeterías en el mapa")
    assert sheet.judge_free([{"name": "Café de Oriente"}, {"name": "Federal Café"}], SHEET)[0] == []
