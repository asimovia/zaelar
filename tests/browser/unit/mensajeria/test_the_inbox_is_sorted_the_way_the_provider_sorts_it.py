"""The mail section lists the Inbox the way the PROVIDER sorts it, with the provider's own unread figures (V2-807 T-01).

The operator, 2026-10-26: «mi inbox de Gmail tiene 14… me incluyes promociones y social… solo la primaria». Over IMAP
a Gmail Inbox holds every category at once, so the card counted «1603 sin leer» against his 14 in Primary.

The class: the card mirrors the provider's own organisation and invents none of it. A server that advertises the
category extension (Gmail's `X-GM-EXT-1`) and answers a category's search has that category, listed under the Inbox
with its own unread count; the Inbox opens on the first one, as Gmail does. Any other server has folders only, and
every folder carries the server's own unread figure (`STATUS UNSEEN`).

Below the screen: a recorded Gmail-style IMAP transcript and a plain server, through the connector, the bus answer
and the card's state, and the voice/tap action they share. Generic: Spanish and English labels, a category named
alone or with its folder, a server that sorts nothing.
"""
from __future__ import annotations

import pytest

from connectors.email import categories, folders
from widgets import store as wstore
from widgets.mensajeria import data, mailbox


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(wstore, "_last_hash", {})
    yield


_LIST = [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasChildren \\Noselect) "/" "[Gmail]"',
         b'(\\HasNoChildren \\Sent) "/" "[Gmail]/Sent Mail"', b'(\\Drafts \\HasNoChildren) "/" "[Gmail]/Drafts"',
         b'(\\HasNoChildren \\Junk) "/" "[Gmail]/Spam"', b'(\\HasNoChildren) "/" "Invoices"']

#: What the server holds: Inbox UIDs by category, and which are unread.
_BY_CAT = {"primary": [101, 105, 109], "social": [102, 106], "promotions": [103, 104, 107, 108, 110],
           "updates": [111], "forums": []}
_UNSEEN = {101, 103, 104, 107, 110, 111}


class _Gmail:
    """A recorded Gmail session: capability, LIST, STATUS, SELECT, UID SEARCH X-GM-RAW, UID FETCH."""

    capabilities = ("IMAP4REV1", "UNSELECT", "IDLE", "X-GM-EXT-1", "MOVE")

    def __init__(self):
        self.cmds = []

    def list(self):
        return "OK", _LIST

    def status(self, name, what):
        self.cmds.append(("status", name, what))
        n = {"INBOX": 1603, "[Gmail]/Spam": 4, "Invoices": 2}.get(name.strip('"'), 0)
        return "OK", [f'"{name}" (UNSEEN {n})'.encode()]

    def select(self, name, readonly=False):
        self.cmds.append(("select", name, readonly))
        return "OK", [b"11"]

    def uid(self, cmd, *args):
        self.cmds.append(("uid", cmd) + args)
        if cmd.upper() == "SEARCH":
            assert args[0] == "X-GM-RAW", args
            q = args[1].strip('"')
            key = q.split("category:")[1].split()[0].rstrip("}")
            uids = set(_BY_CAT[key])
            if "from:amazon.com" in q and "-from:amazon.com" not in q:
                uids |= {104}                                     # his route brings Amazon's promotion here
            if "-from:amazon.com" in q:
                uids -= {104}
            if "is:unread" in q:
                uids &= _UNSEEN
            return "OK", [" ".join(str(u) for u in sorted(uids)).encode()]
        if cmd.upper() == "FETCH":
            out = []
            for i, u in enumerate(args[0].split(","), 1):
                head = (f"From: Shop {u} <shop{u}@{'amazon.com' if u == '104' else 'example.com'}>\r\n"
                        f"Subject: Mail {u}\r\nDate: Mon, 26 Oct 2026 10:00:00 +0000\r\n\r\n").encode()
                flags = "" if int(u) in _UNSEEN else "\\Seen"
                out.append((f"{i} (UID {u} FLAGS ({flags}) BODY[HEADER.FIELDS (FROM TO SUBJECT DATE)] {{1}}".encode(),
                            head))
            return "OK", out
        raise AssertionError(cmd)

    def fetch(self, seqset, what):
        raise AssertionError("a category page is fetched by UID, never by sequence number")

    def logout(self):
        pass


class _Plain(_Gmail):
    """A server that sorts nothing: no category extension."""

    capabilities = ("IMAP4REV1", "IDLE")

    def uid(self, cmd, *args):
        raise AssertionError("a server with no category extension is never searched for categories")

    def fetch(self, seqset, what):
        lo, hi = (int(x) for x in seqset.split(":"))
        return "OK", [(f"{u} (UID {u} FLAGS (\\Seen) BODY[HEADER.FIELDS (FROM)] {{1}}".encode(),
                       f"From: a{u}@x.com\r\nSubject: s{u}\r\n\r\n".encode()) for u in range(lo, hi + 1)]


class _Mb:
    def __init__(self, im):
        self.im = im

    def _imap(self):
        return self.im


# ── the connector ─────────────────────────────────────────────────────────────────────────────────────────────

def test_a_gmail_inbox_answers_its_categories_with_their_own_unread_and_a_page_of_one():
    mb = _Mb(_Gmail())
    page = folders.list_page(mb, "INBOX", None, 2, category="primary")
    assert page["categories"] == [{"key": "primary", "unread": 1}, {"key": "social", "unread": 0},
                                  {"key": "promotions", "unread": 4}, {"key": "updates", "unread": 1},
                                  {"key": "forums", "unread": 0}]
    assert page["counts"]["INBOX"] == 1603, "the folder's own figure is still there — it is just not Primary's"
    assert page["counts"]["[Gmail]/Spam"] == 4
    assert page["category"] == "primary" and [r["uid"] for r in page["rows"]] == ["109", "105"]
    assert page["nextBefore"] == "105" and page["complete"] is False
    older = folders.list_page(_Mb(_Gmail()), "INBOX", page["nextBefore"], 2, category="primary")
    assert [r["uid"] for r in older["rows"]] == ["101"] and older["complete"] is True
    assert "categories" not in older and "counts" not in older, "the figures ride with the first page only"
    assert ("select", "INBOX", True) in mb.im.cmds, "read-only"


def test_his_route_is_composed_into_the_providers_own_query():
    ext = categories.supported(_Gmail())
    routes = [{"from": "amazon.com", "to": "primary"}]
    assert categories.query(ext, "primary", routes) == "{category:primary from:amazon.com}"
    assert categories.query(ext, "promotions", routes) == "category:promotions -from:amazon.com"
    page = folders.list_page(_Mb(_Gmail()), "INBOX", None, 30, category="primary", routes=routes)
    assert "104" in [r["uid"] for r in page["rows"]]
    assert {c["key"]: c["unread"] for c in page["categories"]}["primary"] == 2, "the counts follow his rule too"
    # a route token can never carry search syntax
    assert categories.clean_routes([{"from": 'x" OR in:anywhere', "to": "primary"}, {"from": "", "to": "x"}]) == []


def test_a_server_that_sorts_nothing_has_folders_only_and_a_category_asked_of_it_is_ignored():
    page = folders.list_page(_Mb(_Plain()), "INBOX", None, 3, category="primary")
    assert "categories" not in page and "category" not in page
    assert [r["uid"] for r in page["rows"]] == ["11", "10", "9"]
    assert page["counts"]["INBOX"] == 1603


# ── the card's state ──────────────────────────────────────────────────────────────────────────────────────────

def _listed():
    from connectors.email.mailbox import Mailbox
    return folders.parse_list(Mailbox._folders(_Gmail()))


def _answer(db, **ev):
    mailbox.fold(db, {"platform": "email", "folder": "INBOX", "before": None, "nextBefore": None, "complete": True,
                      "folders": _listed(), **ev})


_CATS = [{"key": "primary", "unread": 14}, {"key": "social", "unread": 40}, {"key": "promotions", "unread": 1549}]


def test_the_inbox_opens_on_the_providers_first_category_once_it_is_known():
    db = data.load_db()
    mailbox.go(db, "inbox")
    assert db["pending_mail"][-1] == {"platform": "email", "folder": "INBOX", "before": None, "limit": mailbox.PAGE}
    _answer(db, rows=[{"uid": "9"}], categories=_CATS, counts={"INBOX": 1603})
    assert db["pending_mail"][-1]["category"] == "primary", "the provider has spoken: the Inbox moves to Primary"
    v = mailbox.view(db)
    assert v["category"] == "primary" and v["unread"] == 14, "Primary's 14, never the Inbox's 1603"
    assert [c["key"] for c in v["categories"]] == ["primary", "social", "promotions"]


def test_a_category_named_alone_or_with_its_folder_lands_on_that_entry():
    db = data.load_db()
    _answer(db, rows=[], categories=_CATS, counts={"INBOX": 1603, "[Gmail]/Spam": 4})
    data.store.save(data.WIDGET_ID, db)
    out = data.apply_action("mail_folder", {"folder": "promotions"})
    assert out["mailbox"]["folder"] == "INBOX" and out["mailbox"]["category"] == "promotions"
    assert out["result"]["unread"] == 1549 and out["result"]["category"] == "promotions"
    assert out["result"]["categories"] == ["primary", "social", "promotions"]
    out = data.apply_action("mail_folder", {"folder": "inbox", "category": "social"})
    assert out["mailbox"]["category"] == "social"
    asked = data.load_db()["pending_mail"][-1]
    assert asked["category"] == "social" and asked["routes"] == []
    out = data.apply_action("mail_folder", {"folder": "spam"})
    assert out["mailbox"]["role"] == "junk" and out["mailbox"]["category"] is None and out["result"]["unread"] == 4
    out = data.apply_action("mail_folder", {"folder": "inbox"})
    assert out["mailbox"]["category"] == "primary", "the Inbox with no category named opens on Primary"


def test_a_category_the_provider_never_returned_is_not_invented():
    db = data.load_db()
    _answer(db, rows=[{"uid": "3"}], counts={"INBOX": 7})               # a server that sorts nothing
    data.store.save(data.WIDGET_ID, db)
    out = data.apply_action("mail_folder", {"folder": "inbox", "category": "promotions"})
    assert out["mailbox"]["category"] is None and out["mailbox"]["categories"] == []
    assert out["result"]["unread"] == 7
    _answer(db, rows=[], categories=_CATS)
    mailbox.go(db, "inbox", "forums")                                      # Gmail's, but not returned here
    assert mailbox.view(db)["category"] == "primary"


def test_each_category_keeps_its_own_list_and_the_mail_section_entry_keeps_where_he_was():
    db = data.load_db()
    _answer(db, rows=[], categories=_CATS)
    mailbox.go(db, "inbox", "promotions")
    mailbox.fold(db, {"platform": "email", "folder": "INBOX", "category": "promotions", "before": None,
                      "rows": [{"uid": "50"}, {"uid": "49"}], "nextBefore": "49", "complete": False})
    mailbox.go(db, "inbox", "primary")
    mailbox.fold(db, {"platform": "email", "folder": "INBOX", "category": "primary", "before": None,
                      "rows": [{"uid": "60"}], "complete": True})
    assert [r["uid"] for r in mailbox.view(db)["rows"]] == ["60"]
    mailbox.go(db, "inbox", "promotions")
    v = mailbox.view(db)
    assert [r["uid"] for r in v["rows"]] == ["50", "49"] and v["more"]
    data.store.save(data.WIDGET_ID, db)
    data.apply_action("mail_more", {})
    assert data.load_db()["pending_mail"][-1]["category"] == "promotions", "«load more» stays in the category"
    out = data.apply_action("show_view", {"platform": "email"})
    assert out["mailbox"]["category"] == "promotions", "entering the section again lands where he was"


def test_the_bus_answer_carries_the_category_through_the_connector(monkeypatch):
    import asyncio

    from connectors.email import service
    from connectors.messaging import ingest
    answers, calls = [], []
    monkeypatch.setattr(ingest, "publish_mailbox", lambda p, a: answers.append(a))
    monkeypatch.setattr(folders, "list_page", lambda mb, f, b, n, **kw: calls.append(kw) or
                        {"rows": [], "category": kw.get("category"), "complete": True})

    class _Inbox:
        def drain(self):
            return [{"platform": "email", "folder": "INBOX", "before": None, "limit": 30, "category": "social",
                     "routes": [{"from": "x.com", "to": "social"}]}]
    monkeypatch.setattr(service, "_mailbox_inbox", _Inbox())
    asyncio.run(service._drain_mailbox(object()))
    assert calls == [{"category": "social", "routes": [{"from": "x.com", "to": "social"}]}]
    assert answers[0]["category"] == "social"
