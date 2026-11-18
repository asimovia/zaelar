"""The conversation he has OPEN is the first reading of a name it carries (2026-11-18).

Measured: with her chat open on the screen he said «send her a message» by her first name. The name was resolved
against the directory alone — which held another row of the same person, the one of his address book, with only a
mail address — and the reply offered to write there. What he was looking at was never a candidate.

  · the name he says is read against the open conversation first: its own name and its contact's, by word or by
    SOUND; when it names that conversation the message goes there;
  · a word HE gave to somebody else outranks the screen only as a question, the one in front first;
  · with no conversation open, or another channel named, the directory decides as before.
"""
from __future__ import annotations

import pytest

CHAT = "77000000272@lid"


@pytest.fixture
def world(tmp_path, monkeypatch):
    """ISOLATED stores: her address-book row (a mail address only) and her chat, under the name SHE spells."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from widgets import directory
    directory._WINDOW.clear(); directory._ASKED.clear()
    from widgets.contactos import data as people
    db = people.load_db()
    db["contacts"].append({"id": "c1", "kind": "person", "name": "Vanessa Holt Rios", "source": "google",
                           "email": "vanessa@example.org", "emails": [{"value": "vanessa@example.org", "label": ""}],
                           "aliases": [], "channels": []})
    people.store.save(people.WIDGET_ID, db)
    from widgets.mensajeria import data as msgs, thread
    mdb = msgs.load_db()
    thread._thread(mdb, "whatsapp", CHAT)["name"] = "Banesa Olt"
    mdb["active_chat"] = {"platform": "whatsapp", "chatId": CHAT}
    mdb["platforms"] = {p: {"status": "connected", "reported": True} for p in ("whatsapp", "telegram", "email")}
    msgs.store.save(msgs.WIDGET_ID, mdb)
    yield people, msgs
    directory._WINDOW.clear(); directory._ASKED.clear()


def _target(payload):
    from widgets.mensajeria.outbound import targets
    return targets.resolve_target(payload)


def test_a_name_that_sounds_like_the_open_chat_is_that_chat(world):
    t = _target({"contact": "Vanessa", "text": "on my way"})
    assert t.get("ok") and (t["platform"], t["chatId"]) == ("whatsapp", CHAT) and t.get("in_front"), t
    assert t["name"] == "Banesa Olt", "named as the chat shows her, so the one question he hears says who"


def test_a_name_the_open_chat_does_not_carry_goes_to_the_directory(world):
    people, _msgs = world
    db = people.load_db()
    db["contacts"].append({"id": "c2", "kind": "person", "name": "Tomas Brandt", "email": "tomas@example.org",
                           "emails": [{"value": "tomas@example.org", "label": ""}], "channels": []})
    people.store.save(people.WIDGET_ID, db)
    t = _target({"contact": "Tomas", "text": "hello"})
    assert t.get("ok") and t["platform"] == "email" and t["contactId"] == "c2", t


def test_a_word_he_gave_someone_else_is_asked_with_the_one_in_front_first(world):
    people, _msgs = world
    db = people.load_db()
    db["contacts"][0]["aliases"] = ["Vanessa"]                 # HIS word for the row of his address book
    people.store.save(people.WIDGET_ID, db)
    t = _target({"contact": "Vanessa", "text": "on my way"})
    assert not t.get("ok") and t.get("slot") == "contact", t
    assert t["candidates"] == ["Banesa Olt", "Vanessa Holt Rios"], t


def test_with_nothing_open_or_another_channel_named_the_directory_decides(world):
    _people, msgs = world
    mail = _target({"contact": "Vanessa", "text": "hello", "channel": "email"})
    assert mail.get("ok") and mail["platform"] == "email" and mail["contactId"] == "c1", mail
    mdb = msgs.load_db()
    mdb["active_chat"] = None
    msgs.store.save(msgs.WIDGET_ID, mdb)
    t = _target({"contact": "Vanessa", "text": "hello"})
    assert t.get("ok") and t["platform"] == "email" and not t.get("in_front"), t


def test_once_the_two_rows_are_one_person_the_open_chat_is_hers_by_any_name(world):
    people, _msgs = world
    db = people.load_db()
    db["contacts"].append({"id": "c9", "kind": "person", "name": "Banesa Olt", "source": "whatsapp",
                           "channels": [{"platform": "whatsapp", "handle": CHAT, "chatId": CHAT, "volume": 3}]})
    people.store.save(people.WIDGET_ID, db)
    assert people.apply_action("merge_contacts", {"contactId": "c1", "with": "c9"})["ok"]
    t = _target({"contact": "Vanessa Holt", "text": "on my way"})
    assert t.get("ok") and t["contactId"] == "c1" and (t["platform"], t["chatId"]) == ("whatsapp", CHAT), t


def test_the_worker_looking_a_name_up_is_told_what_he_is_looking_at(world):
    """A send is one worker task: its lookup must hand back the open conversation, or the name that reaches the
    door is the directory's and the screen is never read."""
    from nucleo.request import send_errand
    got = send_errand.find_contact("Vanessa")["result"]
    assert got["in_front"] == {"name": "Banesa Olt", "platform": "whatsapp"} and "write THERE" in got["note"], got
    people, _msgs = world
    db = people.load_db()
    db["contacts"][0]["aliases"] = ["Vanessa"]
    people.store.save(people.WIDGET_ID, db)
    asked = send_errand.find_contact("Vanessa")["result"]
    assert asked["in_front"] == {"name": "Banesa Olt", "ask": ["Vanessa Holt Rios"]} and "ask him which" in asked["note"]
    assert "in_front" not in send_errand.find_contact("Tomas")["result"]
