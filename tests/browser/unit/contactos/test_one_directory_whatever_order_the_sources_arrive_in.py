"""ONE directory whatever order the sources arrive in, and only HIS people in sight (2026-11-18).

Measured on a real store after a reset: the messaging sources were read first (an empty directory) and the address
book came later. 3 828 people: 1 046 of them somebody only ever seen as a member of one of his groups, 13 named by
a phone number; the account a chat app shows under the name she chose and his address book's row under the name he
saved were two rows — the one rule that joins them by that full name only ran when the chat arrived SECOND; and
«which … do I have» was answered with the record of the one he had last talked to.

  · `identity.by_name` in the look back — a full name exactly two rows of two sources carry joins them, after
    every import of either side and at the start: order changes nothing;
  · a group's member nobody else knows and an account named by a number are kept, mapped and OUT OF SIGHT
    (`identity.keep_back`), and come back by themselves when a source lists them as his or names them; a pass
    demotes the member-only rows an earlier pass made;
  · a number never names a row; his address book's name is the one shown once the rows are one;
  · a name under an ending («the Odiles») and a first name plus the word a chat app writes reach the people.

Every name here is invented.
"""
from __future__ import annotations

import time

import pytest

MOBILE, HOME = "+34 600 11 22 33", "+34 91 555 00 00"
JID = "34600112233@s.whatsapp.net"


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


def _google(name, i=1, **kw):
    return {"name": name, "kind": "person", "googleId": f"people/{i}",
            "phone": (kw.get("phones") or [""])[0], "email": (kw.get("emails") or [""])[0],
            "phones": [{"value": p, "label": ""} for p in kw.get("phones") or []],
            "emails": [{"value": e, "label": ""} for e in kw.get("emails") or []], "knownAs": []}


def _chat(name, jid=JID, phone="", **kw):
    return {"name": name, "kind": "person", "phone": phone, "externalIds": {"whatsapp": jid},
            "channels": [{"platform": "whatsapp", "handle": phone or jid, "chatId": jid, "name": name}], **kw}


def _tg(name, uid, phone=""):
    return {"name": name, "kind": "person", "externalIds": {"telegram": str(uid)},
            "channels": [{"platform": "telegram", "chatId": str(uid)}], **({"phone": phone} if phone else {})}


def _sight(db):
    return sorted(c["name"] for c in db["contacts"] if c.get("kind") == "person" and not c.get("hidden"))


def _both_orders(book, first, second):
    """Run the two imports in the order given on a fresh store; the people in sight and how each is reached."""
    from widgets import directory
    from widgets.contactos import gmerge, imports
    db = {"contacts": [], "next_id": 1}
    for what, payload in (first, second):
        if what == "google":
            gmerge.merge_imported(db, payload)
            from widgets.contactos import identity
            identity.unify(db)                       # what `gcontacts` does after every import
        else:
            imports.absorb(db, {"contacts": payload, "groups": []}, source=what)
    return [(c["name"], sorted({ch["platform"] for ch in directory.channels(c)}),
             sorted(r["name"] for r in c.get("knownAs") or []))
            for c in db["contacts"] if not c.get("hidden")]


# ── order changes nothing ─────────────────────────────────────────────────────────────────────────────────────

def test_a_phone_joins_the_two_rows_whichever_source_came_first(book):
    g = ("google", [_google("Odile Varga Lund", phones=[MOBILE], emails=["odile@example.org"])])
    w = ("whatsapp", [_chat("Odi Karó", phone="+34600112233")])
    want = [("Odile Varga Lund", ["email", "whatsapp"], ["Odi Karó"])]
    assert _both_orders(book, g, w) == want
    assert _both_orders(book, w, g) == want, "the chat first, the address book later: still one person, his name for her"


def test_a_full_name_the_source_also_has_joins_them_whichever_came_first(book):
    """No key in common: his address book has only her address; the chat app shows the name she chose and knows
    the one he saved."""
    g = ("google", [_google("Odile Varga Lund", emails=["odile@example.org"])])
    w = ("whatsapp", [_chat("Odi Karó", "77000000109@lid", knownAs=["Odile Varga Lund"])])
    want = [("Odile Varga Lund", ["email", "whatsapp"], ["Odi Karó"])]
    assert _both_orders(book, g, w) == want
    assert _both_orders(book, w, g) == want, "this direction made two rows"


def test_a_name_alone_joins_only_one_pair_of_two_sources_and_never_what_he_took_apart(book):
    from widgets.contactos import fusion, identity

    def db_of(*rows):
        db = {"contacts": [dict(r) for r in rows], "next_id": 9}
        for c in db["contacts"]:
            book.model.normalize(c)
        return db
    a = {"id": "c1", "kind": "person", "name": "Odile Varga Lund", "source": "google", "googleId": "people/1"}
    b = {"id": "c2", "kind": "person", "name": "Odi", "source": "whatsapp", "knownAs": [{"name": "Odile Varga Lund", "source": "whatsapp"}]}
    assert identity.unify(db_of(a, b))["merged"] == 1
    assert identity.unify(db_of(a, {**b, "source": "google"}))["merged"] == 0, "one source's two rows: it keeps them apart"
    assert identity.unify(db_of(a, {**b, "knownAs": [{"name": "Odile", "source": "whatsapp"}]}))["merged"] == 0, "one word is no full name"
    one = {**a, "name": "Odile"}
    assert identity.unify(db_of(one, {**b, "name": "Odi", "knownAs": [{"name": "Odile", "source": "whatsapp"}]}))["merged"] == 0, \
        "…even when it is all either row is called"
    c = {"id": "c3", "kind": "person", "name": "Odile Varga Lund", "source": "telegram"}
    assert identity.unify(db_of(a, b, c))["merged"] == 0, "three rows carry it: nobody is guessed"
    assert identity.unify(db_of(a, {**b, "hidden": True}))["merged"] == 0, "a row out of sight is joined to nobody by a name"
    db = db_of(a, b)
    identity.unify(db)
    assert db["merged"]["c2"]["by"] == "name" and fusion.split(db, "c2")
    assert identity.unify(db)["merged"] == 0, "taken apart stays apart"
    kept = {"id": "c4", "kind": "person", "name": "Odile Varga", "source": "telegram", "phone": MOBILE, "hidden": True, "keptBy": "member"}
    seen = {"id": "c5", "kind": "person", "name": "Odi", "source": "whatsapp", "phone": MOBILE}
    db = db_of(kept, seen)
    assert identity.unify(db)["merged"] == 1
    assert db["contacts"][0]["hidden"] is False and "keptBy" not in db["contacts"][0], "one of the two was in sight: the person is"


def test_the_start_step_folds_what_is_already_there(book):
    from widgets import store
    db = book.load_db()
    db["contacts"] += [
        {"id": "c1", "kind": "person", "name": "Odi Karó", "source": "whatsapp", "phone": MOBILE,
         "knownAs": [{"name": "Odile Varga Lund", "source": "whatsapp"}],
         "channels": [{"platform": "whatsapp", "chatId": JID, "handle": MOBILE}]},
        {"id": "c2", "kind": "person", "name": "Odile Varga Lund", "source": "google", "googleId": "people/1",
         "email": "odile@example.org"},
        {"id": "c3", "kind": "person", "name": "+34 600 00 00 01", "source": "telegram", "phone": "+34 600 00 00 01"}]
    for c in db["contacts"]:
        book.model.normalize(c)
    store.save(book.WIDGET_ID, db)
    got = book.on_start()
    assert got["folded_now"] == 1 and got["people"] == 1 and got["numbers_kept_back_now"] == 1
    assert _sight(book.load_db()) == ["Odile Varga Lund"]
    again = book.on_start()
    assert again["folded_now"] == 0 and again["numbers_kept_back_now"] == 0, "a start that repeats it changes nothing"


# ── only his people are in sight ──────────────────────────────────────────────────────────────────────────────

def _group(name, gid, members):
    return {"name": name, "platform": "telegram", "subtype": "group", "externalIds": {"telegram": str(gid)},
            "channels": [{"platform": "telegram", "chatId": str(gid)}], "members": members}


def test_a_member_nobody_else_knows_is_kept_out_of_sight_and_the_group_still_counts_him(book):
    from widgets import directory
    from widgets.contactos import imports
    db = book.load_db()
    res = imports.absorb(db, {"contacts": [_tg("Odile Varga", 1, "+34600112233")],
                              "groups": [_group("Trip", -100, [_tg("Odile Varga", 1), _tg("Marek Stone", 2)])]},
                         source="telegram")
    assert _sight(db) == ["Odile Varga"] and res["contacts"]["added"] == 1
    marek = next(c for c in db["contacts"] if c["name"] == "Marek Stone")
    assert marek["hidden"] and marek["keptBy"] == "member" and directory.level(marek) == 0, "mapped, never a candidate"
    assert len(next(c for c in db["contacts"] if c["kind"] == "group")["members"]) == 2
    book.store.save(book.WIDGET_ID, db)
    assert directory.resolve("Marek Stone") == [] and book.view_data()["hidden_count"] == 0, "not one of HIS hides either"


def test_the_day_a_source_lists_him_as_his_he_is_back(book):
    from widgets.contactos import gmerge, imports
    db = book.load_db()
    grp = [_group("Trip", -100, [_tg("Marek Stone", 2), _tg("Ines Brandt", 3)])]
    imports.absorb(db, {"contacts": [], "groups": grp}, source="telegram")
    assert _sight(db) == []
    imports.absorb(db, {"contacts": [_tg("Marek Stone", 2)], "groups": grp}, source="telegram")     # a conversation with him
    assert _sight(db) == ["Marek Stone"]
    db2 = book.load_db()
    imports.absorb(db2, {"contacts": [], "groups": [_group("Trip", -100, [_tg("Ines Brandt", 3, "+34915550000")])]}, source="telegram")
    gmerge.merge_imported(db2, [_google("Ines Brandt", phones=[HOME])])                               # his address book
    assert [c["name"] for c in db2["contacts"] if c["kind"] == "person" and not c.get("hidden")] == ["Ines Brandt"]


def test_a_pass_demotes_the_member_only_rows_an_earlier_pass_made_and_nobody_he_touched(book):
    from widgets.contactos import imports
    db = book.load_db()
    old = lambda i, name, **kw: {"id": f"c{i}", "kind": "person", "name": name, "source": "telegram", "hidden": False,
                                 "externalIds": {"telegram": str(i)}, "channels": [{"platform": "telegram", "chatId": str(i)}], **kw}
    db["contacts"] += [old(1, "Marek Stone"), old(2, "Ines Brandt", favorite=True), old(3, "Tomas Brandt", phone=HOME),
                       old(4, "Odile Varga"), old(5, "Hugo Lund", channels=[{"platform": "telegram", "chatId": "5", "volume": 3}])]
    db["next_id"] = 9
    for c in db["contacts"]:
        book.model.normalize(c)
    members = [_tg(n, i) for i, n in ((1, "Marek Stone"), (2, "Ines Brandt"), (3, "Tomas Brandt"), (4, "Odile Varga"), (5, "Hugo Lund"))]
    imports.absorb(db, {"contacts": [_tg("Odile Varga", 4)], "groups": [_group("Trip", -100, members)]}, source="telegram")
    assert _sight(db) == ["Hugo Lund", "Ines Brandt", "Odile Varga", "Tomas Brandt"], \
        "his favorite, the one with a number, the one he has a conversation with and the one he talked to stay"
    assert next(c for c in db["contacts"] if c["id"] == "c1")["keptBy"] == "member"


def test_the_start_owes_every_source_with_groups_one_read(book):
    from widgets.contactos import sources
    db = book.load_db()
    db["contacts"].append({"id": "c1", "kind": "group", "name": "Trip", "platform": "telegram", "members": ["c2"]})
    sources.state(db)["telegram"].update({"last": time.time() - 60, "partial": False})
    sources.state(db)["whatsapp"].update({"last": time.time() - 60, "partial": False})
    assert sources.owe_members(db) == ["telegram"] and db["sources"]["telegram"]["partial"] is True
    assert sources.owe_members(db) == [], "once per store"


def test_a_number_is_never_a_name(book):
    from widgets.contactos import imports
    db = book.load_db()
    imports.absorb(db, {"contacts": [_chat("+34600112233", phone="+34600112233", nameKind="number")]}, source="whatsapp")
    assert _sight(db) == [] and db["contacts"][0]["keptBy"] == "no_name", "kept for its mapping, never shown"
    imports.absorb(db, {"contacts": [_chat("Odi Karó", phone="+34600112233")]}, source="whatsapp")
    assert _sight(db) == ["Odi Karó"], "the day the platform names the account, the row is that person"
    db = book.load_db()
    db["contacts"].clear()
    imports.absorb(db, {"contacts": [_chat("Odi Karó", phone="+34600112233")]}, source="whatsapp")
    imports.absorb(db, {"contacts": [_chat("+34 600 11 22 33", phone="+34600112233")]}, source="whatsapp")
    c = db["contacts"][0]
    assert c["name"] == "Odi Karó" and not c.get("knownAs"), "a number neither renames her nor is a name she is known by"


# ── what the brain reads ──────────────────────────────────────────────────────────────────────────────────────

PEOPLE = ["Odile Varga Lund", "Odile Brandt", "Odile Stone", "Odile Ruiz", "Odile Karó", "Odile Marsh", "Marek Stone"]


@pytest.fixture
def people(book):
    db = book.load_db()
    db["contacts"] += [{"id": f"c{i}", "kind": "person", "name": n, "source": "google", "googleId": f"people/{i}",
                        "phone": "+34" + str(600000000 + i)} for i, n in enumerate(PEOPLE, 1)]
    db["contacts"][4]["channels"] = [{"platform": "whatsapp", "chatId": JID, "volume": 3, "last_seen": time.time()}]
    for c in db["contacts"]:
        book.model.normalize(c)
    book.store.save(book.WIDGET_ID, db)
    return book


def test_which_of_them_do_i_have_names_every_one_and_not_the_record_of_the_leader(people):
    from widgets import directory
    assert [c["name"] for c in directory.resolve("Odile")] == ["Odile Karó"], "the ranking's leader: who a send goes to"
    for question in ("which Odile do I have?", "dime qué Odiles tengo"):
        out = people.read_query(question)
        assert out.startswith("6 personas") and all(n in out for n in PEOPLE[:6]), out
        assert "Marek" not in out and "Ficha COMPLETA" not in out


def test_a_first_name_and_the_word_a_chat_app_writes_reach_the_turn(people):
    db = people.load_db()
    db["contacts"][4]["channels"], db["contacts"][2]["channels"] = [], [{"platform": "whatsapp", "chatId": JID, "volume": 3, "last_seen": time.time()}]
    people.store.save(people.WIDGET_ID, db)                          # the one he talks to is ANOTHER Odile
    assert people.people_named("pregunta a odile si viene")[0]["name"] == "Odile Stone"
    rows = people.people_named("mándale un mensaje a odile caro que llego tarde")
    assert [r["name"] for r in rows] == ["Odile Karó"], "by sound — never the other five of that first name"
    assert people.people_named("dile a marek que si") and people.people_named("escribe a odile kowalski")[0]["name"].startswith("Odile")


def test_a_name_with_no_latin_letter_matches_no_latin_word():
    from widgets.contactos import who
    assert who.word("odilesxx", "𝘔𝘪𝘤𝘩𝘢𝘦𝙡") == 0 and who.word("𝘔𝘪𝘤𝘩", "odile") == 0, "no sound is not every sound"
    assert who.word("odiles", "odile") == who.STEM and who.word("odile's".replace("'", ""), "odile") == who.STEM
    assert who.word("odilesque", "odile") == 0 and who.word("anas", "ana") == 0, "an ending, on a name long enough to carry one"
