"""The messaging card's mail section is a MAIL CLIENT: folders, a folder page, one message, one draft over the card.

The operator, 2026-10-26, on the card's home showing an email draft above the messages addressed to him: the home
holds only what is addressed to him; the mail section is his mailbox — the Inbox with its default criteria, every
folder the account syncs, and a pending draft found by state, opened over the whole card on «abre el borrador»,
with recipient, subject, text and send / save / discard, and a way back to its folder.

Covered here end to end below the screen: the connector's folder list and folder page (read-only, header-only,
paged by UID), the bus round trip through the owner, the card's state (one folder, one open message, one draft),
and the actions voice and taps share. Generic by construction: Gmail-style special-use folders and a server with
none, an address and a directory contact, Spanish and English text.
"""
from __future__ import annotations

import asyncio

import pytest

from connectors.email import folders
from widgets import store as wstore
from widgets.mensajeria import data, mailbox


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(wstore, "_last_hash", {})
    from widgets.contactos import data as cd
    cd.apply_action("add_contact", {"name": "Rowan Pike", "phone": "+34600111222"})
    cd.apply_action("set_channel", {"contactId": "c1", "platform": "whatsapp", "handle": "+34600111222"})
    yield


# ── the connector: folders and a page, read-only ──────────────────────────────────────────────────────────

_GMAIL_LIST = [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasChildren \\Noselect) "/" "[Gmail]"',
               b'(\\HasNoChildren \\Sent) "/" "[Gmail]/Enviados"', b'(\\Drafts \\HasNoChildren) "/" "[Gmail]/Borradores"',
               b'(\\HasNoChildren \\Trash) "/" "[Gmail]/Papeler&AO0-a"', b'(\\HasNoChildren) "/" "Facturas"',
               b'(\\All \\HasNoChildren) "/" "[Gmail]/Todos"']


def _listed(lines):
    """A LIST response through the mailbox's own parser, the way `list_page` reads it."""
    from connectors.email.mailbox import Mailbox

    class _L:
        def list(self):
            return "OK", lines
    return folders.parse_list(Mailbox._folders(_L(), delimiter=True))


def test_folders_come_in_client_order_with_their_role_and_a_readable_name():
    got = _listed(_GMAIL_LIST)
    assert [f["role"] for f in got] == ["inbox", "drafts", "sent", "all", "trash", ""]
    assert "[Gmail]" not in [f["name"] for f in got], "a \\Noselect container holds folders, not mail"
    trash = next(f for f in got if f["role"] == "trash")
    assert trash["label"] == "Papelería" and trash["name"] == "[Gmail]/Papeler&AO0-a", "label decoded, name kept for SELECT"


def test_a_role_is_what_the_server_DECLARES_never_a_guess_from_the_folder_name():
    """A server that announces no special-use attribute gets its folders listed by their own names — reading «Sent»
    or «Enviados» out of a name is a word table, and the next language or provider would miss it."""
    got = _listed([b'() "." "INBOX"', b'() "." "INBOX.Sent"', b'() "." "INBOX.Drafts"', b'() "." "Trash"'])
    assert {f["label"]: f["role"] for f in got} == {"INBOX": "inbox", "Sent": "", "Drafts": "", "Trash": ""}


def test_a_folder_name_is_cut_only_at_the_servers_own_delimiter():
    """Gmail's delimiter is «/»: a label named after an address keeps its dots (it was read as «com»), and a server
    whose delimiter IS «.» still gets its leaf."""
    gm = _listed([b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren) "/" "ana@example.com"',
                  b'(\\HasNoChildren) "/" "Clientes/v2.0"'])
    assert {f["label"] for f in gm} == {"INBOX", "ana@example.com", "v2.0"}
    dot = _listed([b'() "." "INBOX"', b'() "." "INBOX.Facturas"', b'() NIL "Plano.txt"'])
    assert {f["label"] for f in dot} == {"INBOX", "Facturas", "Plano.txt"}


class _Imap:
    """A mailbox of 45 messages, uids 1..45. Records how it was opened and what was fetched."""

    def __init__(self):
        self.selected, self.fetched, self.logged_out = [], [], False

    def list(self):
        return "OK", _GMAIL_LIST

    def select(self, name, readonly=False):
        self.selected.append((name, readonly))
        return "OK", [b"45"]

    def uid(self, cmd, *args):
        raise AssertionError("a page is fetched by sequence number, never by searching the whole folder")

    def fetch(self, seqset, what):
        self.fetched.append((seqset, what))
        lo, hi = (int(x) for x in seqset.split(":"))
        out = []
        for u in range(lo, hi + 1):   # in this mailbox, sequence number == UID
            head = (f"From: Anna <anna{u}@example.com>\r\nTo: me@example.com\r\nSubject: =?utf-8?q?Reuni=C3=B3n_{u}?=\r\n"
                    f"Date: Mon, 26 Oct 2026 10:{int(u) % 60:02d}:00 +0000\r\n\r\n").encode()
            flags = "\\Seen" if int(u) % 2 else ""
            out.append((f"{u} (UID {u} FLAGS ({flags}) BODY[HEADER.FIELDS (FROM TO SUBJECT DATE)] {{1}}".encode(), head))
            out.append(b")")
        return "OK", out

    def logout(self):
        self.logged_out = True


class _Mb:
    def __init__(self):
        self.im = _Imap()

    def _imap(self):
        return self.im


def test_a_folder_page_is_headers_only_newest_first_and_never_marks_anything_read():
    mb = _Mb()
    page = folders.list_page(mb, "INBOX", None, 30)
    assert [r["uid"] for r in page["rows"]][:3] == ["45", "44", "43"] and len(page["rows"]) == 30
    assert page["nextBefore"] == "16" and page["complete"] is False
    assert mb.im.fetched[0][0] == "16:45", "one FETCH of exactly one page"
    assert page["rows"][0]["fromName"] == "Anna" and page["rows"][0]["subject"] == "Reunión 45"
    assert page["rows"][0]["seen"] is True and page["rows"][1]["seen"] is False
    assert mb.im.selected == [("INBOX", True)], "browsing selects read-only"
    assert all("BODY.PEEK[HEADER.FIELDS" in a[1] for a in mb.im.fetched), "headers only, PEEK"
    assert mb.im.logged_out
    older = folders.list_page(_Mb(), "INBOX", page["nextBefore"], 30)
    assert [r["uid"] for r in older["rows"]][0] == "15" and older["complete"] is True


# ── the card's state ──────────────────────────────────────────────────────────────────────────────────────

def _page(folder="INBOX", uids=(45, 44), before=None, nxt="44", complete=False):
    return {"platform": "email", "folder": folder, "before": before, "nextBefore": nxt, "complete": complete,
            "folders": _listed(_GMAIL_LIST),
            "rows": [{"uid": str(u), "from": "a@x.com", "fromName": "A", "subject": f"s{u}", "seen": False}
                     for u in uids]}


def test_entering_a_folder_asks_its_first_page_once_and_folds_the_answer():
    db = data.load_db()
    assert mailbox.go(db, "inbox") == "INBOX"
    assert db["pending_mail"] == [{"platform": "email", "folder": "INBOX", "before": None, "limit": mailbox.PAGE}]
    assert mailbox.ask(db, "INBOX") is False, "an ask in flight is not repeated"
    mailbox.fold(db, _page())
    v = mailbox.view(db)
    assert [r["uid"] for r in v["rows"]] == ["45", "44"] and v["more"] and not v["loading"]
    # A role he says resolves to the server's folder once the list is known.
    assert mailbox.folder_name(db, "sent") == "[Gmail]/Enviados" and mailbox.folder_name(db, "Papelería") \
        == "[Gmail]/Papeler&AO0-a"


def test_load_more_appends_older_rows_and_a_refresh_keeps_the_pages_walked():
    db = data.load_db()
    mailbox.fold(db, _page())
    mailbox.fold(db, _page(uids=(43, 42), before="44", nxt=None, complete=True))
    mailbox.fold(db, _page(uids=(46, 45, 44)))
    v = mailbox.view(db)
    assert [r["uid"] for r in v["rows"]] == ["46", "45", "44", "43", "42"] and not v["more"]


def test_an_inbox_row_that_is_waiting_on_the_home_is_marked_and_opens_without_asking_the_mailbox():
    db = data.load_db()
    db["items"] = [{"platform": "email", "messageId": "45", "chatId": "a@x.com", "from": "A"}]
    mailbox.fold(db, _page())
    assert [r["pending"] for r in mailbox.view(db)["rows"]] == [True, False]
    db.pop("pending_mail", None)
    mailbox.open_message(db, "45")
    assert not db.get("pending_mail"), "the card already holds this mail whole"
    mailbox.open_message(db, "44")
    assert db["pending_mail"] == [{"platform": "email", "folder": "INBOX", "open": "44"}]
    mailbox.fold(db, {"platform": "email", "folder": "INBOX", "open": {"uid": "44", "subject": "s44", "body": "hola"}})
    assert mailbox.view(db)["open"]["msg"]["body"] == "hola"


# ── the actions voice and taps share ──────────────────────────────────────────────────────────────────────

def _held_email():
    return data.apply_action("draft", {"contact": "hospitality@example.com", "subject": "API access",
                                       "text": "Hola,\n\nQueremos integrarnos con vuestra API."})


def test_a_folder_order_moves_the_card_to_the_mail_section_and_asks_its_page():
    out = data.apply_action("mail_folder", {"folder": "sent"})
    assert out["ok"] and out["view"]["platform"] == "email"
    assert out["mailbox"]["folder"] == "sent" or out["mailbox"]["role"] in ("sent", "")
    assert data.load_db()["pending_mail"][-1]["folder"] in ("sent", "[Gmail]/Enviados")


def test_open_the_draft_finds_the_pending_one_by_state_and_puts_it_over_the_card():
    key = _held_email()["key"]
    db = data.load_db()
    db["drafts"][key]["at"] -= 3600                                                         # written an hour ago
    data.store.save(data.WIDGET_ID, db)
    data.apply_action("draft", {"contact": "Rowan Pike", "text": "See you at 4"})          # newer, another channel
    out = data.apply_action("open_draft", {"contact": "hospitality"})
    assert out["ok"] and out["result"]["subject"] == "API access"
    assert out["mailbox"]["draft"] == out["result"]["key"] and out["view"]["platform"] == "email"
    assert out["mailbox"]["role"] == "drafts", "a draft lives in the Drafts section, its way back"
    newest = data.apply_action("open_draft", {})
    assert newest["result"]["to"] == "Rowan Pike" and newest["view"]["platform"] == "whatsapp"
    assert data.apply_action("open_draft", {"contact": "nobody-at-all"})["ok"] is False


def test_save_keeps_his_edits_and_a_new_recipient_moves_the_draft_without_sending_anything():
    key = _held_email()["key"]
    out = data.apply_action("save_draft", {"key": key, "text": "Hello,\n\nWe would like API access.",
                                           "subject": "API access — Zaelar"})
    d = data.load_db()["drafts"][key]
    assert out["ok"] and d["text"].startswith("Hello") and d["target"]["subject"] == "API access — Zaelar"
    moved = data.apply_action("save_draft", {"key": key, "to": "partners@example.com", "text": d["text"]})
    drafts = data.load_db()["drafts"]
    assert key not in drafts and moved["result"]["key"] in drafts
    assert drafts[moved["result"]["key"]]["target"]["to"] == "partners@example.com"
    assert drafts[moved["result"]["key"]]["target"]["subject"] == "API access — Zaelar"
    assert not data.load_db().get("pending_send"), "saving never sends"


def test_send_from_the_draft_screen_sends_THAT_draft_even_when_another_is_newer():
    key = _held_email()["key"]
    data.apply_action("draft", {"contact": "Rowan Pike", "text": "See you at 4"})
    out = data.apply_action("send_draft", {"key": key})
    assert out["ok"], out
    assert [o["to"] for o in data.load_db()["pending_send"]] == ["hospitality@example.com"]


def test_discard_drops_the_draft_and_goes_back_to_its_folder():
    key = _held_email()["key"]
    data.apply_action("open_draft", {"key": key})
    out = data.apply_action("discard_draft", {"key": key})
    assert out["ok"] and key not in data.load_db()["drafts"] and out["mailbox"]["draft"] is None
    assert not data.load_db().get("pending_send")


def test_back_from_a_message_returns_to_its_folder_not_to_the_home():
    db = data.load_db()
    mailbox.fold(db, _page())
    data.store.save(data.WIDGET_ID, db)
    data.apply_action("mail_open", {"uid": "44"})
    out = data.apply_action("mail_back", {})
    assert out["mailbox"]["open"] is None and out["mailbox"]["folder"] == "INBOX"
    assert out["view"]["platform"] == "email"


def test_every_new_action_is_declared_in_the_manifest():
    import json
    import pathlib
    man = json.loads((pathlib.Path(data.__file__).parent / "manifest.json").read_text())
    for a in ("mail_folder", "mail_more", "mail_open", "mail_back", "open_draft", "save_draft", "discard_draft"):
        assert a in man["actions"] and a in data.ACTIONS, a


# ── the round trip over the bus ───────────────────────────────────────────────────────────────────────────

def test_the_owner_publishes_the_ask_and_folds_the_connectors_answer(monkeypatch):
    from connectors.messaging import ingest
    from widgets.mensajeria import owner
    sent = []
    monkeypatch.setattr(ingest, "publish_mailbox_ask", sent.append)
    db = data.load_db()
    mailbox.go(db, "inbox")
    data.store.save(data.WIDGET_ID, db)
    owner._OWNER._flush_queues()
    assert sent == [{"platform": "email", "folder": "INBOX", "before": None, "limit": mailbox.PAGE}]
    assert not data.load_db().get("pending_mail"), "an ask leaves once"

    class _Sub:
        def __init__(self, evs):
            import queue
            self.queue = queue.Queue()
            for e in evs:
                self.queue.put(e)
    monkeypatch.setattr(owner._OWNER, "_mailbox_sub", _Sub([_page()]))
    owner._OWNER._apply_mailbox()
    assert [r["uid"] for r in data.view_data()["mailbox"]["rows"]] == ["45", "44"]


def test_the_email_connector_serves_a_page_and_a_message_on_demand(monkeypatch):
    from connectors.email import service
    from connectors.messaging import ingest
    answers = []
    monkeypatch.setattr(ingest, "publish_mailbox", lambda p, a: answers.append((p, a)))
    monkeypatch.setattr(folders, "list_page", lambda mb, f, b, n: {"rows": [{"uid": "9"}], "folders": [],
                                                                    "nextBefore": None, "complete": True,
                                                                    "error": ""})
    monkeypatch.setattr(folders, "read_one", lambda mb, f, u, m=None: {"uid": u, "folder": f, "body": "x"})

    class _Inbox:
        def drain(self):
            return [{"platform": "email", "folder": "INBOX", "before": None, "limit": 30},
                    {"platform": "email", "folder": "[Gmail]/Enviados", "open": "7"}]
    monkeypatch.setattr(service, "_mailbox_inbox", _Inbox())
    asyncio.run(service._drain_mailbox(object()))
    assert answers[0] == ("email", {"folder": "INBOX", "before": None, "rows": [{"uid": "9"}], "folders": [],
                                    "nextBefore": None, "complete": True, "error": ""})
    assert answers[1] == ("email", {"folder": "[Gmail]/Enviados", "open": {"uid": "7", "folder": "[Gmail]/Enviados",
                                                                         "body": "x"}})


# ── the draft screen's one-order buttons; the outcome is state ────────────────────────────────────────────

def test_compose_saves_a_new_mail_as_a_draft_on_screen_and_says_so():
    out = data.apply_action("compose", {"to": "partners@example.com", "subject": "Hola", "text": "Texto"})
    mb = out["mailbox"]
    assert mb["draft"] and data.load_db()["drafts"][mb["draft"]]["target"]["to"] == "partners@example.com"
    assert mb["note"]["key"] == "saved" and not data.load_db().get("pending_send")


def test_compose_with_send_writes_and_sends_in_one_order_and_goes_back_to_the_folder():
    out = data.apply_action("compose", {"to": "partners@example.com", "subject": "Hola", "text": "Texto",
                                        "send": True})
    assert out["ok"] and [o["to"] for o in data.load_db()["pending_send"]] == ["partners@example.com"]
    assert out["mailbox"]["draft"] is None and out["mailbox"]["note"]["key"] == "sent"


def test_send_from_an_open_draft_sends_what_is_on_screen():
    key = _held_email()["key"]
    data.apply_action("compose", {"key": key, "text": "Edited on screen", "send": True})
    assert [o.get("text") for o in data.load_db()["pending_send"]] == ["Edited on screen"]


def test_a_recipient_nobody_knows_keeps_the_screen_and_says_why():
    out = data.apply_action("compose", {"to": "Somebody Unknown", "text": "Texto", "send": True})
    assert out["ok"] is False and out["mailbox"]["note"]["key"] == "not_saved" and out["mailbox"]["note"]["text"]
    assert not data.load_db().get("pending_send")
