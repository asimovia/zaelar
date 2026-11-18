"""ONE directory: every linked source feeds it by itself, and a said name is ranked with how sure the match is.

Measured 2026-11-18 on a real directory (2 705 rows, every one from the address book; two messaging accounts linked
and never read): nobody he wrote to was a row, so no row could gain a channel; two entries of one person in the
address book stayed two; and «send a message to <first name> <a word>» — the word was how she is called on the
platform — came back as six people of that first name, presented as the answer.

  · `sources._due` — a linked source is read on the first tick it is seen linked, again soon while its answer is
    partial, then daily; his «off» is remembered and stops it;
  · an arriving person a row already proves becomes a CHANNEL of that row, and the names its conversation carried
    in the message log travel with it (`sources._names_seen`) — a full name exactly one row has joins the two;
  · `identity.akin` — one address book's nickname row and full-name row on one phone are one person; a family
    sharing a surname on a landline is not;
  · `who.find` — word, sound, stem, a slip, any order, an address that sounds like it; a word nobody carries makes
    the answer `partial`, with the names to ask him among, never a match; `directory.resolve` agrees.

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


def _row(i, name, **kw):
    return {"id": f"c{i}", "kind": "person", "name": name, "source": "google", "googleId": f"people/{i}", **kw}


def _put(book, rows):
    db = book.load_db()
    db["contacts"] += rows
    for c in db["contacts"]:
        book.model.normalize(c)
    book.store.save(book.WIDGET_ID, db)
    return db


def _chat(name, jid=JID, phone="", **kw):
    return {"name": name, "kind": "person", "phone": phone, "externalIds": {"whatsapp": jid},
            "channels": [{"platform": "whatsapp", "handle": phone or jid, "chatId": jid, "name": name}], **kw}


# ── a linked source feeds the directory by itself ─────────────────────────────────────────────────────────────

def test_a_linked_source_never_read_is_due_and_his_off_stops_it(book, monkeypatch):
    from widgets.contactos import sources
    monkeypatch.setattr(sources, "connected", lambda s: s == "whatsapp")
    now = time.time()
    assert sources._due("whatsapp", {"on": False, "last": 0.0}, now)
    assert not sources._due("telegram", {"on": False, "last": 0.0}, now), "not linked: never read"
    assert not sources._due("whatsapp", {"on": False, "last": 0.0, "declined": True}, now), "his off is his"
    assert not sources._due("whatsapp", {"on": False, "last": 0.0, "tried": now - 60}, now), "a try waits its turn"
    assert sources._due("whatsapp", {"on": False, "last": now - 1000, "partial": True}, now), "a partial book is asked again soon"
    assert not sources._due("whatsapp", {"on": False, "last": now - 1000, "partial": False}, now)
    assert sources._due("whatsapp", {"on": False, "last": now - 90000}, now)


def test_the_tick_reads_a_linked_source_nobody_asked_for_and_her_chat_becomes_a_channel(book, monkeypatch):
    from widgets.contactos import sources
    _put(book, [_row(1, "Odile Varga Lund", phone=MOBILE, email="odile@example.org")])
    monkeypatch.setattr(sources, "connected", lambda s: s == "whatsapp")
    asked = []
    monkeypatch.setattr(sources, "_names_seen", lambda *a: 0)

    def answer(source, timeout=25.0):
        asked.append(source)
        return {"ok": True, "partial": True, "groups": [],
                "contacts": [_chat("Odi V", phone="+34600112233"), _chat("Marek Stone", "77000000109@lid")]}
    monkeypatch.setattr(sources, "_ask_connector", answer)
    sources.tick(None)
    assert asked == ["whatsapp"]
    people = [c for c in book.load_db()["contacts"] if c["kind"] == "person"]
    assert sorted(c["name"] for c in people) == ["Marek Stone", "Odile Varga Lund"], "matched → a channel; unmatched → a row"
    her = next(c for c in people if c["name"] == "Odile Varga Lund")
    assert [ch["platform"] for ch in her["channels"]] == ["whatsapp"] and her["email"] == "odile@example.org"
    st = book.load_db()["sources"]["whatsapp"]
    assert st["last"] > 0 and st["partial"] is True and st["on"] is False
    sources.tick(None)
    assert asked == ["whatsapp"], "the next tick does not ask again at once"


def test_switching_a_source_off_is_remembered(book, monkeypatch):
    from widgets.contactos import sources
    assert sources.set_auto("whatsapp", False)["on"] is False
    assert book.load_db()["sources"]["whatsapp"]["declined"] is True


def test_the_name_her_conversation_carried_joins_the_account_to_the_row_of_that_name(book, monkeypatch):
    """The platform shows the name SHE chose; the message log saw the same number under the name he keeps her by."""
    from connectors.messaging import archive
    from widgets import directory
    from widgets.contactos import sources
    _put(book, [_row(1, "Odile Varga Lund", email="odile@example.org"), _row(2, "Odile Brandt", phone=HOME)])
    monkeypatch.setattr(archive, "chats", lambda platform, limit=600: [
        {"chatId": JID, "name": "Odile Varga Lund", "kind": "person"},
        {"chatId": "77000000109@lid", "name": "Hugo Self", "kind": "person"},
        {"chatId": "77000000272@lid", "name": "Hugo Self", "kind": "person"},      # his own name, under every chat
        {"chatId": "1203630@g.us", "name": "Trip", "kind": "group"}])
    rows = [_chat("Odi Karó", "77000000473@lid", "+34600112233"), _chat("Marek Stone", "77000000109@lid")]
    assert sources._names_seen("whatsapp", rows) == 1
    assert rows[0]["knownAs"] == ["Odile Varga Lund"] and "knownAs" not in rows[1], "a name of several accounts is nobody's"
    res = sources._absorb("whatsapp", {"ok": True, "contacts": rows, "groups": []})
    assert res["contacts"]["added"] == 1, "only the stranger is a new row"
    her = directory.resolve("Odi Caro")
    assert [c["name"] for c in her] == ["Odile Varga Lund"], "found by the platform's name, by sound"
    assert {ch["platform"] for ch in directory.channels(her[0])} == {"whatsapp", "email"}


def test_a_single_word_the_source_also_has_never_joins_two_rows(book):
    from widgets.contactos import imports
    db = _put(book, [_row(1, "Odile", email="odile@example.org")])
    res = imports.absorb(db, {"contacts": [_chat("Marek Stone", knownAs=["Odile"])]}, source="whatsapp")
    assert res["contacts"]["added"] == 1, "a nickname names, it never identifies"


# ── one address book, two entries of one person ───────────────────────────────────────────────────────────────

def test_a_nickname_row_and_a_full_name_row_on_one_phone_are_one_person_and_a_family_is_not():
    from widgets.contactos import identity as I
    a = _row(1, "Odile Varga Lund", phone=MOBILE)
    assert I.same(a, _row(2, "Odile Work", phone=MOBILE)) == "phone", "the same given name"
    assert I.same(a, _row(2, "Odyle Sister", phone=MOBILE)) == "phone", "…by sound"
    assert I.same(a, _row(2, "Varg", phone=MOBILE)) == "phone", "a one-word stem of her name"
    assert I.same(a, _row(2, "Tomas Varga Lund", phone=MOBILE)) == "", "a family on one line: two surnames shared"
    assert I.same(a, _row(2, "Marek Stone", phone=MOBILE)) == ""
    assert I.same(_row(1, "Al Stone", phone=MOBILE), _row(2, "Al Brandt", phone=MOBILE)) == "", "two letters are no given name"


def test_the_look_back_folds_them_and_the_fold_can_be_undone(book):
    from widgets.contactos import fusion, identity
    db = _put(book, [_row(1, "Odile Varga Lund", phone=MOBILE, favorite=True), _row(2, "Odile Work", phone=MOBILE),
                     _row(3, "Ines Brandt", phone=HOME), _row(4, "Tomas Brandt", phone=HOME)])
    assert identity.unify(db)["merged"] == 1
    assert {c["id"] for c in db["contacts"]} == {"c1", "c3", "c4"} and "c2" in db["merged"]
    assert {"name": "Odile Work", "source": "google"} in book._find(db, "c1")["knownAs"]
    assert fusion.split(db, "c2") and identity.unify(db)["merged"] == 0, "taken apart stays apart"
    assert {c["id"] for c in db["contacts"]} == {"c1", "c2", "c3", "c4"}


# ── a said name, ranked ───────────────────────────────────────────────────────────────────────────────────────

PEOPLE = [("Odile Varga Lund", {"email": "ovl@example.org"}), ("Odile Brandt", {"phone": HOME}),
          ("Odile Stone", {"phone": "+34 600 00 00 01"}), ("Marek Stone", {"email": "quietharbor@example.org"}),
          ("Jimena Villalobos", {"phone": "+34 600 00 00 02"}), ("Carolina Ruiz", {"phone": "+34 600 00 00 03"})]


@pytest.fixture
def people(book):
    _put(book, [_row(i, n, **kw) for i, (n, kw) in enumerate(PEOPLE, 1)])
    return book


@pytest.mark.parametrize("said, name, confidence", [
    ("Odile Varga", "Odile Varga Lund", "sure"),
    ("lund odile", "Odile Varga Lund", "sure"),                # any order
    ("Odil Barga", "Odile Varga Lund", "likely"),              # a slip, and b for v
    ("Gimena Biyalovos", "Jimena Villalobos", "sure"),         # soft g/j, b/v, ll/y
    ("Jimena Villa", "Jimena Villalobos", "likely"),           # a stem of the surname
    ("Marek Sotne", "Marek Stone", "likely"),                  # two letters swapped
    ("Quiet Harbor", "Marek Stone", "likely"),                 # what his address sounds like
])
def test_a_said_name_finds_its_person_and_says_how_sure(people, said, name, confidence):
    from widgets import directory
    from widgets.contactos import who
    got = who.find(said)
    assert got["confidence"] == "one", got
    assert (got["people"][0]["contact"]["name"], got["people"][0]["confidence"]) == (name, confidence)
    assert [c["name"] for c in directory.resolve(said)] == [name], "the doors and the worker agree"


def test_a_first_name_several_share_is_a_question_among_all_of_them(people):
    from widgets.contactos import who
    got = who.find("Odile")
    assert got["confidence"] == "several" and len(got["people"]) == 3
    assert {r["confidence"] for r in got["people"]} == {"sure"}


def test_a_surname_nobody_carries_is_partial_with_names_and_never_a_match(people):
    from widgets import directory
    from widgets.contactos import who
    got = who.find("Odile Kowalski")
    assert got["confidence"] == "partial" and got["unmatched"] == ["kowalski"]
    assert [r["contact"]["name"].split()[0] for r in got["people"]] == ["Odile"] * 3
    assert all(r["confidence"] == "partial" and r["missing"] == ["kowalski"] for r in got["people"])
    assert directory.resolve("Odile Kowalski") == [], "no door sends on part of a name"
    assert directory.resolve("Odile Sante") == [], "most of the letters of «Odile Stone» is not her surname"
    assert who.find("Odile Sante")["confidence"] == "partial"
    assert [c["name"] for c in directory.resolve("with Marek Stone")] == ["Marek Stone"], "her whole name, inside more words"
    assert directory.resolve("Odile Stome")[0]["name"] == "Odile Stone", "a slip of the surname is still her"
    assert who.find("Kowalski")["confidence"] == "none"


def test_the_worker_is_told_it_is_part_of_a_name_and_whom_to_ask_about(people, monkeypatch):
    from nucleo.request import send_contact as send_errand
    monkeypatch.setattr(send_errand, "_in_front", lambda q: {})
    monkeypatch.setattr(send_errand, "_front_shares", lambda q: {})
    out = send_errand.find_contact("Odile Kowalski")["result"]
    assert out["match"] == "partial" and out["unmatched"] == ["kowalski"] and "never pick one" in out["note"]
    assert len(out["people"]) == 3 and all(p["confidence"] == "partial" for p in out["people"])
    assert "example.org" not in str(out) and "600" not in str(out), "who and by which platform, never an address or a number"
    one = send_errand.find_contact("Gimena Biyalovos")["result"]
    assert one["match"] == "one" and [p["name"] for p in one["people"]] == ["Jimena Villalobos"]


def test_the_open_conversation_that_shares_part_of_the_name_is_asked_about_first(people, monkeypatch):
    from nucleo.request import send_contact as send_errand
    from widgets.mensajeria import data as md
    from widgets.mensajeria.outbound import in_front
    monkeypatch.setattr(send_errand, "_in_front", lambda q: {})
    monkeypatch.setattr(md, "load_db", lambda: {})
    monkeypatch.setattr(in_front, "conversation", lambda db: {"platform": "whatsapp", "chatId": JID, "name": "Odile Stone"})
    out = send_errand.find_contact("Odile Kowalski")["result"]
    assert out["in_front"] == {"name": "Odile Stone", "platform": "whatsapp", "shares": True}
    assert out["note"].startswith("`in_front` is the conversation he has open; it carries part of the name")
    monkeypatch.setattr(in_front, "conversation", lambda db: {"platform": "whatsapp", "chatId": JID, "name": "Marek Stone"})
    assert "in_front" not in send_errand.find_contact("Odile Kowalski")["result"], "an open chat of somebody else is nothing"


def test_a_lookup_of_thousands_stays_cheap(book):
    from widgets.contactos import who
    _put(book, [_row(i, f"Person{i} Family{i % 97}", phone=f"+34 600 {i:06d}") for i in range(3000)])
    who.find("Person7 Family7")
    t0 = time.perf_counter()
    got = who.find("Persn1500 Famly45")
    assert time.perf_counter() - t0 < 1.0 and got["people"]
