"""One person is ONE row of the directory, whatever source each row came from (2026-11-18).

Measured on a real directory of 2 912 rows (one address book, one messaging import): 21 sets of rows shared a phone
and 12 an address, unmerged; the person he wrote to every day was two rows — the one of his address book and the one
of the chat, under the name SHE chose there — and «send her a message» found only the first.

  · `identity.keys` / `same` — a phone (any of them), an address or an account proves the person; a name never does;
  · every import folds what it proved (`imports.absorb`, `gmerge.merge_imported`), and the store's migration looks
    back at what was already there;
  · the name another source gives is kept beside the one shown, with its source, and finds the person;
  · a rename on the platform arrives (a `refresh` never adds a stranger);
  · when nothing proves it, he says it once (`merge_contacts`), and any fold can be taken apart (`split_contact`).
"""
from __future__ import annotations

import time

import pytest

MOBILE, HOME = "+34 600 11 22 33", "+34 91 555 00 00"


@pytest.fixture
def book(tmp_path, monkeypatch):
    """ISOLATED store — never the operator's directory."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from widgets import directory
    directory._WINDOW.clear()
    from widgets.contactos import data
    return data


def _google(name, **kw):
    return {"name": name, "kind": "person", "googleId": kw.pop("gid", f"people/{abs(hash(name)) % 10**6}"),
            "phone": (kw.get("phones") or [""])[0], "email": (kw.get("emails") or [""])[0],
            "phones": [{"value": p, "label": ""} for p in kw.get("phones") or []],
            "emails": [{"value": e, "label": ""} for e in kw.get("emails") or []], "knownAs": kw.get("knownAs") or []}


def _chat(name, jid, phone="", **kw):
    return {"name": name, "kind": "person", "phone": phone, "externalIds": {"whatsapp": jid},
            "channels": [{"platform": "whatsapp", "handle": phone or jid, "chatId": jid, "name": name}], **kw}


def _people(db):
    return [c for c in db["contacts"] if c.get("kind") == "person"]


# ── what proves a person ──────────────────────────────────────────────────────────────────────────────────────

def test_a_phone_an_address_and_an_account_are_keys_and_a_linked_identity_is_no_phone():
    from widgets.contactos import identity as I
    row = {"phones": [{"value": HOME}, {"value": "0034 600112233"}], "email": "Odile@Example.org",
           "channels": [{"platform": "whatsapp", "chatId": "77000000109@lid", "handle": "77000000109@lid"},
                        {"platform": "telegram", "chatId": "600000020", "handle": "@odile"}]}
    k = I.keys(row)
    assert ("phone", "600112233") in k and ("phone", "915550000") in k and ("email", "odile@example.org") in k
    assert ("acct", "whatsapp", "77000000109@lid") in k and ("acct", "telegram", "odile") in k
    assert not any(kind == "phone" and v in ("000000109", "600000020") for kind, v, *_ in k), \
        "a `@lid` and a Telegram account id carry digits that are no phone"
    assert ("phone", "600112233") in I.keys({"channels": [{"platform": "whatsapp", "chatId": "34600112233@s.whatsapp.net"}]})


def test_two_names_on_one_line_of_one_address_book_stay_two_people():
    from widgets.contactos import identity as I
    a = {"id": "c1", "kind": "person", "name": "Odile Varga", "source": "google", "phone": HOME}
    b = {"id": "c2", "kind": "person", "name": "Tomas Varga", "source": "google", "phone": HOME}
    assert I.same(a, b) == "", "a home landline is a line, not a person"
    assert I.same(a, {**b, "name": "Odile Varga Lund"}) == "phone"
    assert I.same(a, {**b, "name": "odile.vargalund"}) == "phone", "a handle standing where the name is missing"
    assert I.same(a, {**b, "source": "whatsapp", "name": "Odi"}) == "phone", "another source's account IS hers"
    assert I.same(a, {**b, "kind": "company"}) == "", "a person and a company are never one row"


# ── every import folds what it proved ─────────────────────────────────────────────────────────────────────────

def test_the_chat_of_a_person_joins_her_row_by_any_of_her_phones_and_its_name_is_kept(book):
    from widgets import directory
    from widgets.contactos import gmerge, imports
    db = book.load_db()
    gmerge.merge_imported(db, [_google("Odile Varga Lund", phones=[HOME, MOBILE], emails=["odile@example.org"])])
    res = imports.absorb(db, {"contacts": [_chat("Odi V", "34600112233@s.whatsapp.net", "+34600112233")]}, source="whatsapp")
    assert res["added"] == 0 and len(_people(db)) == 1, "her SECOND number is her too"
    c = _people(db)[0]
    assert c["name"] == "Odile Varga Lund", "the name of his address book is the one shown"
    assert {"name": "Odi V", "source": "whatsapp"} in c["knownAs"]
    assert any(ch["platform"] == "whatsapp" for ch in c["channels"])
    book.store.save(book.WIDGET_ID, db)
    assert [x["id"] for x in directory.resolve("Odi V")] == [c["id"]], "the name the chat shows finds her"


def test_his_address_book_arriving_second_names_the_row_the_chat_gave(book):
    from widgets.contactos import gmerge, imports
    db = book.load_db()
    imports.absorb(db, {"contacts": [_chat("Odi V", "34600112233@s.whatsapp.net", "+34600112233")]}, source="whatsapp")
    got = gmerge.merge_imported(db, [_google("Odile Varga Lund", phones=[MOBILE], knownAs=["My sunshine"])])
    assert got["added"] == 0 and len(_people(db)) == 1
    c = _people(db)[0]
    assert c["name"] == "Odile Varga Lund" and c["nameSource"] == "google"
    assert {r["name"] for r in c["knownAs"]} == {"Odi V", "My sunshine"}, "her own name and his nickname both find her"


def test_the_rows_already_stored_are_folded_and_the_folded_id_keeps_answering(book):
    from widgets.contactos import identity
    db = book.load_db()
    db["contacts"] += [
        {"id": "c1", "kind": "person", "name": "Odile Varga Lund", "source": "google", "googleId": "people/1",
         "email": "odile@example.org", "favorite": True},
        {"id": "c2", "kind": "person", "name": "odile.vargalund", "source": "google", "googleId": "people/2",
         "email": "odile@example.org"},
        {"id": "c3", "kind": "person", "name": "Odi V", "source": "whatsapp", "phone": MOBILE,
         "externalIds": {"whatsapp": "34600112233@s.whatsapp.net"},
         "channels": [{"platform": "whatsapp", "handle": MOBILE, "chatId": "34600112233@s.whatsapp.net", "volume": 9}]},
        {"id": "c4", "kind": "person", "name": "Odile V. (work)", "source": "telegram", "phone": MOBILE,
         "channels": [{"platform": "telegram", "handle": "@odile", "chatId": "777"}]},
        {"id": "c5", "kind": "person", "name": "Ines Brandt", "source": "google", "phone": HOME},
        {"id": "c6", "kind": "person", "name": "Tomas Brandt", "source": "google", "phone": HOME},
        {"id": "g1", "kind": "group", "name": "Trip", "members": ["c3", "c5"], "source": "whatsapp"}]
    for c in db["contacts"]:
        book.model.normalize(c)
    got = identity.unify(db)
    ids = {c["id"] for c in db["contacts"]}
    assert got["merged"] == 2 and ids == {"c1", "c4", "c5", "c6", "g1"}, ids      # mail twins; phone twins
    assert identity.unify(db)["merged"] == 0, "looking back twice changes nothing"
    both = book._find(db, "c3")
    assert both is not None and both["id"] == "c4" and {ch["platform"] for ch in both["channels"]} == {"whatsapp", "telegram"}
    assert book._find(db, "g1")["members"] == ["c4", "c5"], "the group that listed the folded row lists the person"
    assert book._find(db, "c2")["id"] == "c1" and db["merged"]["c2"]["row"]["name"] == "odile.vargalund"
    assert {c["id"] for c in db["contacts"] if c["id"] in ("c5", "c6")} == {"c5", "c6"}, "two people on a landline"


def test_a_store_of_the_previous_version_is_looked_back_at_when_it_loads(book):
    from widgets import store
    store.save(book.WIDGET_ID, {"_v": 4, "next_id": 9, "contacts": [
        {"id": "c1", "kind": "person", "name": "Odile Varga Lund", "source": "google", "phones": [{"value": MOBILE}], "phone": MOBILE},
        {"id": "c2", "kind": "person", "name": "Odi V", "source": "whatsapp", "phones": [{"value": "600 11 22 33"}],
         "phone": "600 11 22 33", "channels": [{"platform": "whatsapp", "handle": "x@lid", "chatId": "x@lid"}]}]})
    db = book.load_db()
    assert [c["id"] for c in _people(db)] == ["c1"] and "c2" in db["merged"]
    assert {"name": "Odi V", "source": "whatsapp"} in _people(db)[0]["knownAs"]


# ── a rename on the platform arrives; a stranger does not ─────────────────────────────────────────────────────

def test_a_pushed_rename_reaches_the_person_and_never_adds_a_stranger(book):
    from widgets import directory
    from widgets.contactos import imports
    db = book.load_db()
    imports.absorb(db, {"contacts": [_chat("Odi V", "1122@lid")]}, source="whatsapp")
    res = imports.absorb(db, {"contacts": [_chat("Odile Sunrise", "1122@lid", knownAs=["Odi V"]),
                                           _chat("Somebody In A Group", "9988@lid")]}, source="whatsapp", refresh=True)
    assert res["added"] == 0 and len(_people(db)) == 1, "the socket names every stranger of a group: none is a contact"
    c = _people(db)[0]
    assert c["name"] == "Odile Sunrise" and {"name": "Odi V", "source": "whatsapp"} in c["knownAs"]
    assert c["channels"][0]["name"] == "Odile Sunrise"
    book.store.save(book.WIDGET_ID, db)
    assert directory.resolve("Odile Sunrise") and directory.resolve("Odi V"), "the new name works and the old still does"


def test_a_name_he_gave_is_never_renamed_by_a_source(book):
    from widgets.contactos import imports
    db = book.load_db()
    imports.absorb(db, {"contacts": [_chat("Odi V", "1122@lid")]}, source="whatsapp")
    book.store.save(book.WIDGET_ID, db)
    cid = _people(db)[0]["id"]
    assert book.apply_action("update_contact", {"contactId": cid, "name": "Odile"})["ok"]
    db = book.load_db()
    imports.absorb(db, {"contacts": [_chat("Sunny", "1122@lid")]}, source="whatsapp", refresh=True)
    c = _people(db)[0]
    assert c["name"] == "Odile" and "Sunny" in {r["name"] for r in c["knownAs"]}


def test_a_number_learned_behind_an_account_joins_the_two_rows(book):
    """The chat's account hid its number (`@lid`); the bridge learns it from a message and pushes it."""
    from widgets.contactos import gmerge, imports
    db = book.load_db()
    gmerge.merge_imported(db, [_google("Odile Varga Lund", phones=[MOBILE])])
    imports.absorb(db, {"contacts": [_chat("Odi V", "1122@lid")]}, source="whatsapp")
    assert len(_people(db)) == 2, "nothing proves it yet"
    res = imports.absorb(db, {"contacts": [_chat("Odi V", "1122@lid", "+34600112233")]}, source="whatsapp", refresh=True)
    assert res["merged"] == 1 and len(_people(db)) == 1 and _people(db)[0]["name"] == "Odile Varga Lund"


# ── his word, and the undo ────────────────────────────────────────────────────────────────────────────────────

def test_he_says_two_rows_are_one_person_and_can_take_them_apart_again(book):
    from widgets.contactos import identity
    db = book.load_db()
    db["contacts"] += [
        {"id": "c1", "kind": "person", "name": "Odile Varga Lund", "source": "google", "email": "odile@example.org"},
        {"id": "c2", "kind": "person", "name": "Odi V", "source": "whatsapp",
         "channels": [{"platform": "whatsapp", "handle": "1122@lid", "chatId": "1122@lid", "volume": 5}]}]
    db["next_id"] = 3
    book.store.save(book.WIDGET_ID, db)
    r = book.apply_action("merge_contacts", {"contactId": "c1", "with": "Odi V"})
    assert r["ok"] and r["result"]["folded"] == "Odi V", r
    one = _people(book.load_db())
    assert len(one) == 1 and one[0]["id"] == "c1" and {ch["platform"] for ch in one[0]["channels"]} == {"whatsapp"}
    assert not book.apply_action("merge_contacts", {"contactId": "c1", "with": "c1"})["ok"]
    back = book.apply_action("split_contact", {"contactId": "c1"})
    assert back["ok"] and back["result"]["contact"]["name"] == "Odi V", back
    db = book.load_db()
    assert {c["id"] for c in _people(db)} == {"c1", "c2"} and not book._find(db, "c1").get("channels")
    c1, c2 = book._find(db, "c1"), book._find(db, "c2")
    c1["phone"] = c2["phone"] = MOBILE
    for c in (c1, c2):
        book.model.normalize(c)
    assert identity.unify(db)["merged"] == 0, "what he took apart is never joined again"


# ── once a day, and only a source he has imported from ────────────────────────────────────────────────────────

def test_a_linked_source_is_looked_at_once_a_day_only_after_he_imported_from_it(book, monkeypatch):
    from widgets.contactos import sources
    monkeypatch.setattr(sources, "connected", lambda s: True)
    now = time.time()
    assert not sources._due("whatsapp", {"on": False, "last": 0.0}, now), "an import nobody asked for never starts"
    assert not sources._due("whatsapp", {"on": False, "last": now - 3600}, now)
    assert sources._due("whatsapp", {"on": False, "last": now - 90000}, now)
    assert sources._due("whatsapp", {"on": True, "last": now - 1000}, now)
    monkeypatch.setattr(sources, "connected", lambda s: False)
    assert not sources._due("whatsapp", {"on": False, "last": now - 90000}, now), "a source that is not linked"


def test_a_rule_he_set_about_the_folded_row_is_a_rule_about_the_person(book):
    """His exception for ONE person hangs from her row's id (`subject:<id>`): folded away, it would stop guarding."""
    import rules
    from widgets.contactos import identity
    rules.add("subject:c2/messaging/whatsapp/send_new", "gate", "consent", "ask", text="never to her without asking")
    rules.add("subject:c7", "gate", "consent", "ask", text="somebody else")
    db = book.load_db()
    db["contacts"] += [
        {"id": "c1", "kind": "person", "name": "Odile Varga Lund", "source": "google", "phone": MOBILE, "favorite": True},
        {"id": "c2", "kind": "person", "name": "Odi V", "source": "whatsapp", "phone": MOBILE}]
    for c in db["contacts"]:
        book.model.normalize(c)
    assert identity.unify(db)["merged"] == 1 and [c["id"] for c in _people(db)] == ["c1"]
    scopes = sorted(r["scope"] for r in rules.all_rows(include_defaults=False))
    assert scopes == ["subject:c1/messaging/whatsapp/send_new", "subject:c7"], scopes
