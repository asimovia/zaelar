"""V2-849 step 3 · a name is looked for closest first: his circle, then the people he talks to, then the background.

A real directory: 2,706 contacts imported from an address book, fifteen of them match «unai» and most are years old
(«Psm Unai Buso», «Unai Elastic», «Carmen Mamá de Unai»). The resolver answered in store order, so a «which
Unai?» named four arbitrary rows — and the person he writes to every week was not among them.

The rules (`widgets/directory.py`):
  · a level per contact, computed: CIRCLE (his word: favorite, alias, relation), RECENT and ACTIVE (traffic either
    way within the two `contacts.windows_days`, 7 and 40 by default), BACKGROUND (the rest; also a contact marked closed); hidden and blocked are never
    candidates;
  · the match ladder is unchanged (alias → exact → all words → address/number → spelling), and each rung answers
    closest first;
  · ONE person of his circle is the answer; anything else is a question naming at most `CANDIDATES_MAX`, closest
    first, each with what tells them apart — a single active «Unai» beside fourteen background ones is still a
    question (medium certainty is asked, never assumed).
"""
from __future__ import annotations

import json
import time

import pytest


@pytest.fixture
def world(tmp_path, monkeypatch):
    """ISOLATED store and workspace — never the operator's real directory."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from widgets.contactos import data as d
    from widgets import directory
    directory._WINDOW.clear()
    yield d, directory
    directory._WINDOW.clear()


def _put(d, *rows):
    db = d.load_db()
    for i, r in enumerate(rows):
        # Every row carries a number, as an imported row does: one with no way to reach (V2-854's «unclassified»)
        # ranks last and is never a send's candidate, which is not what these cases are about.
        db["contacts"].append({"id": f"c{i}-{r['name']}", "kind": "person", "channels": [],
                               "phone": f"+34 600 000 {i:03d}", **r})
    d.store.save(d.WIDGET_ID, db)


def _talked(days_ago: float, platform: str = "whatsapp") -> list[dict]:
    return [{"platform": platform, "chatId": f"x{days_ago}", "handle": "", "volume": 3,
             "last_seen": time.time() - days_ago * 86400}]


def _names(rows) -> list[str]:
    return [r["name"] for r in rows]


# ── the levels ───────────────────────────────────────────────────────────────────────────────────────────────

def test_each_contact_has_a_level_computed_from_what_he_did(world):
    _d, dr = world
    assert dr.level({"name": "A", "favorite": True}) == dr.CIRCLE
    assert dr.level({"name": "A", "aliases": ["mi tontita"]}) == dr.CIRCLE
    assert dr.level({"name": "A", "relation": "mother"}) == dr.CIRCLE
    assert dr.level({"name": "A", "channels": _talked(3)}) == dr.RECENT
    assert dr.level({"name": "A", "channels": _talked(20)}) == dr.ACTIVE
    assert dr.level({"name": "A", "channels": _talked(400)}) == dr.BACKGROUND
    assert dr.level({"name": "A"}) == dr.BACKGROUND
    assert dr.level({"name": "A", "favorite": True, "flags": ["closed"]}) == dr.BACKGROUND
    assert dr.level({"name": "A", "channels": _talked(1), "flags": ["blocked"]}) == 0
    assert dr.level({"name": "A", "favorite": True, "hidden": True}) == 0


def test_the_window_is_his_setting(world, tmp_path):
    _d, dr = world
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "contacts.json").write_text(json.dumps({"windows_days": [2, 7]}))
    dr._WINDOW.clear()                                   # the windows are read at most every few seconds
    assert dr.level({"name": "A", "channels": _talked(5)}) == dr.ACTIVE
    assert dr.level({"name": "A", "channels": _talked(30)}) == dr.BACKGROUND


# ── closest first ────────────────────────────────────────────────────────────────────────────────────────────

def test_a_first_name_is_asked_with_the_one_he_talks_to_first(world):
    """V2-854 (the operator, decision 1): a recent conversation is the FIRST level, so one active Unai beside three
    he never talks to is the answer when the margin says so (`clear_margin`); two active ones are still a question,
    the most recent first."""
    d, dr = world
    _put(d, {"name": "Psm Unai Buso"}, {"name": "Unai Elastic"}, {"name": "Unai Hernandez"},
         {"name": "Unai Sabater", "channels": _talked(2)})
    assert _names(dr.resolve("Unai")) == ["Unai Sabater"], "the one he talks to leads by the margin"
    db = d.load_db()
    next(c for c in db["contacts"] if c["name"] == "Unai Elastic")["channels"] = _talked(6)
    d.store.save(d.WIDGET_ID, db)
    hits = dr.resolve("Unai")
    assert _names(hits) == ["Unai Sabater", "Unai Elastic"], "two he wrote to this week: a question among them only"
    from widgets.mensajeria.outbound import targets
    t = targets.resolve_target({"contact": "Unai", "text": "¿has probado Zaelar?"})
    assert t["ok"] is False and t["candidates"] == ["Unai Sabater", "Unai Elastic"]
    assert "WhatsApp, hace 2 días" in t["error"]


def test_one_person_of_his_circle_is_the_answer(world):
    d, dr = world
    _put(d, {"name": "Leire Lozoya"}, {"name": "Leire Ares", "channels": _talked(5)},
         {"name": "Leire Salinas Ortega", "aliases": ["Leire", "mi tontita"]})
    assert _names(dr.resolve("Leire")) == ["Leire Salinas Ortega"]
    assert _names(dr.resolve("mi tontita")) == ["Leire Salinas Ortega"]


def test_a_full_name_reaches_the_background(world):
    d, dr = world
    _put(d, {"name": "Unai Sabater", "channels": _talked(2)}, {"name": "Unai Hernandez"})
    assert _names(dr.resolve("Unai Hernandez")) == ["Unai Hernandez"]


def test_hidden_and_blocked_people_are_never_candidates(world):
    d, dr = world
    _put(d, {"name": "Ana Ruiz", "hidden": True}, {"name": "Ana Gil", "flags": ["blocked"], "channels": _talked(1)},
         {"name": "Ana Mora"})
    assert _names(dr.resolve("Ana")) == ["Ana Mora"]


def test_the_same_in_english_on_another_channel(world):
    d, dr = world
    _put(d, {"name": "Rowan Ferrer", "channels": _talked(4, "telegram")},
         {"name": "Rowan Lee", "channels": _talked(1, "telegram")})
    from widgets.mensajeria.outbound import targets
    t = targets.resolve_target({"contact": "Rowan", "text": "running late"})
    assert t["candidates"] == ["Rowan Lee", "Rowan Ferrer"] and "Telegram, ayer" in t["error"]
    db = d.load_db()
    db["contacts"][0]["channels"] = _talked(400, "telegram")     # V2-854: only one he talks to lately → the answer
    d.store.save(d.WIDGET_ID, db)
    assert targets.resolve_target({"contact": "Rowan", "text": "running late"})["name"] == "Rowan Lee"


def test_a_favorite_among_namesakes_is_the_answer_without_an_alias(world):
    """The circle rule itself, not the alias rung: his ★ on one Leire makes her the Leire — among namesakes he has
    not talked to lately (V2-854: a recent conversation is the first level, above the ★)."""
    d, dr = world
    _put(d, {"name": "Leire Lozoya", "channels": _talked(300)}, {"name": "Leire Ares"},
         {"name": "Leire Salinas Ortega", "favorite": True})
    assert _names(dr.resolve("Leire")) == ["Leire Salinas Ortega"]
