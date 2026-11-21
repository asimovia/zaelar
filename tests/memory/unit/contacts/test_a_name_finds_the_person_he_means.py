"""A said name finds the person he means, and asks only on a real tie (2026-11-21).

Measured on his engine: «send a message to Tony <surname> <surname>» found nobody — the row is «Antonio <surname>
<surname>», the send door read «Tony» as a word nobody carries, the card's search matched the phrase as a substring
(zero rows) and the model went on searching word by word. And «which of the 23?» was asked when he talks to one.

The rules, one piece each:
  · a name is read word by word, in any order, without accents or capitals, by sound, by stem, by a short form
    inside the name («Toni» of «Antonio»), and by his alias (`contactos/who.score`) — the send door, the resolver
    and the card's search read it the SAME way;
  · the closest LEVEL any match is on decides (`directory.nearest`): his favorite, else who he exchanged a message
    with in the last 7 days, else the last 40, else the rest; one person there is the answer, several there is the
    question — and only among them;
  · when he last exchanged a message is read from the messaging archive, the one log every message reaches
    (`directory.last_contact`).

Invented people only.
"""
from __future__ import annotations

import time

import pytest

DAY = 86400.0


@pytest.fixture
def book(tmp_path, monkeypatch):
    """ISOLATED contacts, messaging archive and workspace — never the operator's real directory."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from connectors.messaging import archive
    from widgets import directory
    from widgets.contactos import data as cd
    archive.reset()
    for cache in (directory._WINDOW, directory._MARGIN, directory._TRAFFIC, directory._ASKED):
        cache.clear()
    yield cd, directory, archive
    archive.reset()
    for cache in (directory._WINDOW, directory._MARGIN, directory._TRAFFIC, directory._ASKED):
        cache.clear()


def _put(cd, *rows):
    db = cd.load_db()
    for i, r in enumerate(rows):
        db["contacts"].append({"id": f"p{i}", "kind": "person", "channels": [], "phone": f"+34 600 000 00{i}", **r})
    cd.store.save(cd.WIDGET_ID, db)


def _tg(chat: str) -> list[dict]:
    return [{"platform": "telegram", "handle": "", "chatId": chat, "volume": 0, "last_seen": 0.0}]


def _wrote(archive, directory, chat: str, days_ago: float, platform: str = "telegram", direction: str = "out"):
    """A message in the archive — the one log every channel reaches — `days_ago` days ago."""
    archive.record(platform, chat, [{"id": f"{chat}-{days_ago}", "body": "hola", "ts": time.time() - days_ago * DAY}],
                   direction=direction)
    directory._TRAFFIC.clear()


def _names(rows) -> list[str]:
    return [r["name"] for r in rows]


def _send(name: str) -> dict:
    from nucleo.send import people
    return people.resolve(name)


NAMESAKES = [{"name": f"Iker {s}", "channels": _tg(f"9{i}")} for i, s in enumerate(["Lasa", "Mendi", "Ortu", "Zabal"])]


# ── how a name is read ─────────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("said", ["Antonio Garbí Montalvo", "antonio garbi montalvo", "Toni Garbí Montalvo",
                                  "tony garbi montalvo", "Garbí Montalvo", "montalvo antonio"])
def test_a_full_name_is_found_however_it_is_said(book, said):
    cd, d, _a = book
    _put(cd, {"name": "Antonio Garbí Montalvo"}, {"name": "Toni Ferrer"}, {"name": "Tonia Rius"})
    got = _send(said)
    assert got.get("one", {}).get("name") == "Antonio Garbí Montalvo", got
    assert _names(d.resolve(said)) == ["Antonio Garbí Montalvo"]


@pytest.mark.parametrize("said", ["Antonio Garbí Montalvo", "antonio garbi"])
def test_the_long_form_finds_a_row_saved_with_the_short_one(book, said):
    cd, d, _a = book
    _put(cd, {"name": "Toni Garbí Montalvo"}, {"name": "Antonio Rius"})
    assert _send(said)["one"]["name"] == "Toni Garbí Montalvo"


def test_the_cards_search_finds_the_name_as_said_and_shows_those_rows(book):
    cd, _d, _a = book
    _put(cd, {"name": "Antonio Garbí Montalvo"}, {"name": "Toni Ferrer"})
    got = cd.apply_action("show_view", {"query": "Tony Garbí Montalvo"})
    assert [m["name"] for m in got["result"]["matches"]] == ["Antonio Garbí Montalvo"]
    assert cd.load_db()["view"]["sel"]["ids"] == ["p0"], "the card shows the rows the answer found"
    got = cd.apply_action("show_view", {"query": "garbi"})
    assert [m["name"] for m in got["result"]["matches"]] == ["Antonio Garbí Montalvo"], "a part of the name, as before"


def test_his_alias_names_the_person(book):
    cd, d, _a = book
    _put(cd, {"name": "Leire Ostolaza", "aliases": ["la jefa"]}, {"name": "Leire Arana"})
    assert _send("la jefa")["one"]["name"] == "Leire Ostolaza"
    assert _names(d.resolve("La Jefa")) == ["Leire Ostolaza"]


def test_a_short_form_never_outranks_the_name_itself(book):
    cd, _d, _a = book
    _put(cd, {"name": "Elia Prat"}, {"name": "Cornelia Bas", "favorite": True})
    assert _send("Elia")["one"]["name"] == "Elia Prat"


def test_a_name_nobody_carries_is_nobody(book):
    cd, d, _a = book
    _put(cd, *NAMESAKES)
    assert _send("Gorka Etxebe").get("one") is None and d.resolve("Gorka Etxebe") == []


# ── which of the people who carry it ──────────────────────────────────────────────────────────────────────────

def test_the_only_one_he_wrote_to_this_week_is_the_answer(book):
    cd, d, a = book
    _put(cd, *NAMESAKES)
    _wrote(a, d, "92", 3)
    assert _send("Iker")["one"]["name"] == "Iker Ortu"
    assert _names(d.resolve("Iker")) == ["Iker Ortu"]


def test_a_message_that_came_IN_counts_the_same(book):
    cd, d, a = book
    _put(cd, *NAMESAKES)
    _wrote(a, d, "91", 2, direction="in")
    assert _send("iker")["one"]["name"] == "Iker Mendi"


def test_an_address_and_a_whatsapp_number_are_conversations_of_the_row(book):
    cd, d, a = book
    _put(cd, {"name": "Iker Lasa", "emails": [{"value": "ilasa@example.org", "label": ""}]},
         {"name": "Iker Mendi", "phone": "+34 611 000 111"}, {"name": "Iker Ortu"})
    _wrote(a, d, "ilasa@example.org", 1, platform="email", direction="in")
    assert _send("Iker")["one"]["name"] == "Iker Lasa"
    _wrote(a, d, "34611000111@s.whatsapp.net", 0.5, platform="whatsapp")
    assert d.level(next(c for c in cd.load_db()["contacts"] if c["name"] == "Iker Mendi")) == d.RECENT


def test_this_month_beats_the_rest_and_this_week_beats_this_month(book):
    cd, d, a = book
    _put(cd, *NAMESAKES)
    _wrote(a, d, "90", 20)
    _wrote(a, d, "93", 200)
    assert _send("Iker")["one"]["name"] == "Iker Lasa", "20 days ago, against 200 and never"
    _wrote(a, d, "91", 5)
    assert _send("Iker")["one"]["name"] == "Iker Mendi", "5 days ago, against 20"


def test_his_favorite_comes_first(book):
    cd, d, a = book
    _put(cd, *NAMESAKES[:3], {**NAMESAKES[3], "favorite": True})
    _wrote(a, d, "90", 1)
    assert _send("Iker")["one"]["name"] == "Iker Zabal"


def test_a_real_tie_on_the_winning_level_asks_among_it_only(book):
    cd, d, a = book
    _put(cd, *NAMESAKES)
    _wrote(a, d, "90", 1)
    _wrote(a, d, "93", 4)
    got = _send("Iker")
    assert [c["name"] for c in got["several"]] == ["Iker Lasa", "Iker Zabal"], got
    assert _names(d.resolve("Iker")) == ["Iker Lasa", "Iker Zabal"]


def test_nobody_written_to_is_a_question_among_everyone(book):
    cd, _d, _a = book
    _put(cd, *NAMESAKES)
    assert len(_send("Iker")["several"]) == 4


def test_which_of_them_do_i_have_still_lists_every_one(book):
    """«Which Ikers do I have?» is a list, not a pick: the level never trims it."""
    cd, d, a = book
    _put(cd, *NAMESAKES)
    _wrote(a, d, "92", 3)
    from widgets.contactos import who
    assert len(who.find("Iker", pick=False)["people"]) == 4
