"""What he archives, deletes or moves in his own mail client leaves the card (V2-807 T-04).

The operator, 2026-10-26: «ya he clasificado algunos de esos mensajes y los he quitado del medio… la quiero
sincronizada en tiempo real». The connector mirrored only \\Seen and \\Answered: a mail archived in Gmail leaves
INBOX, the flag fetch simply had no answer for its UID, and the row stayed on the card as if it were still waiting.

The class: the card mirrors the server's MEMBERSHIP. Of the messages on screen, the folder is asked which it still
holds; what it no longer holds leaves the card — from the folder list and from the home's pending items — and a
folder whose size changed has its first page read again, so a mail moved BACK appears again. «I could not ask» is
never read as «they are all gone».

Generic by construction: Inbox items and a non-Inbox folder list, Gmail-style and plain IMAP names, a failed login.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from connectors.email import membership, service
from widgets import store as wstore
from widgets.mensajeria import data, mailbox


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(wstore, "_last_hash", {})
    yield


# ── the connector: one login answers membership and flags ─────────────────────────────────────────────────────

class _Imap:
    """A folder holding UIDs 40, 42 and 45 (41, 43 and 44 were archived elsewhere). Records every command."""

    def __init__(self, held=("40", "42", "45"), exists=b"3", fail_login=False):
        self.held, self.exists, self.cmds = set(held), exists, []

    def select(self, name, readonly=False):
        self.cmds.append(("select", name, readonly))
        return "OK", [self.exists]

    def uid(self, cmd, *args):
        self.cmds.append(("uid", cmd) + args)
        asked = args[-1].split(",") if cmd.upper() == "SEARCH" else args[0].split(",")
        if cmd.upper() == "SEARCH":
            return "OK", [" ".join(u for u in asked if u in self.held).encode()]
        rows = [f"{i} (UID {u} FLAGS (\\Seen))".encode() if u == "42" else f"{i} (UID {u} FLAGS ())".encode()
                for i, u in enumerate(asked, 1)]
        return "OK", rows

    def logout(self):
        self.cmds.append(("logout",))


class _Mb:
    def __init__(self, im=None, fail=False):
        self.im, self.fail = im or _Imap(), fail

    def _imap(self):
        if self.fail:
            raise OSError("network down")
        return self.im


def test_one_login_says_which_messages_the_folder_still_holds_and_their_flags():
    mb = _Mb()
    ans = membership.check(mb, "INBOX", ["40", "41", "42", "43", "45"])
    assert ans["present"] == {"40", "42", "45"} and ans["exists"] == 3
    assert ans["flags"]["42"] == {"\\Seen"} and "41" not in ans["flags"]
    assert membership.gone(["40", "41", "42", "43", "45"], ans) == ["41", "43"]
    assert mb.im.cmds[0] == ("select", "INBOX", True), "asking never marks anything: read-only"
    assert mb.im.cmds[-1] == ("logout",)


def test_a_server_that_cannot_be_asked_removes_nothing():
    assert membership.check(_Mb(fail=True), "INBOX", ["40", "41"]) is None
    assert membership.gone(["40", "41"], None) == [], "«I could not ask» is not «they are all gone»"


# ── the tick: what is on screen is mirrored ──────────────────────────────────────────────────────────────────

def _store(viewed_folder="[Gmail]/Facturas", viewed_ago=10.0, exists=7):
    return {"items": [{"platform": "email", "messageId": "41", "chatId": "a@x.com"},
                      {"platform": "email", "messageId": "42", "chatId": "b@x.com"},
                      {"platform": "whatsapp", "messageId": "w1", "chatId": "c"}],
            "mailbox": {"lists": {
                viewed_folder: {"viewed_at": time.time() - viewed_ago, "exists": exists,
                                "rows": [{"uid": "9"}, {"uid": "8"}]},
                "Old": {"viewed_at": time.time() - 99999, "rows": [{"uid": "1"}]}}}}


def _run_tick(monkeypatch, db, answers):
    published, reads, rereads = [], [], []
    monkeypatch.setattr(service.ingest, "v2_enabled", lambda: True)
    monkeypatch.setattr(service.store, "load", lambda: db)
    monkeypatch.setattr(service.ingest, "publish_mailbox", lambda p, a: published.append(a))
    monkeypatch.setattr(service.ingest, "publish_read", lambda p, c, ids=None: reads.append((c, ids)))
    monkeypatch.setattr(membership, "check", lambda mb, folder, uids: answers.get(folder))
    from connectors.email import folders
    monkeypatch.setattr(folders, "list_page", lambda mb, f, b, n, **kw: rereads.append(f) or
                        {"rows": [{"uid": "10"}], "exists": 8, "complete": True})
    asyncio.run(service._poll_external_flags(object()))
    return published, reads, rereads


def test_the_tick_reports_what_left_each_folder_on_screen_and_what_he_read(monkeypatch):
    answers = {"INBOX": {"present": {"42"}, "flags": {"42": {"\\Seen"}}, "exists": 900},
               "[Gmail]/Facturas": {"present": {"9"}, "flags": {}, "exists": 7}}
    published, reads, rereads = _run_tick(monkeypatch, _store(), answers)
    assert {"folder": "INBOX", "gone": ["41"]} in published
    assert {"folder": "[Gmail]/Facturas", "gone": ["8"]} in published
    assert reads == [("b@x.com", ["42"])], "flags are still mirrored, from the same answer"
    assert rereads == [], "a folder whose size did not change is not read again"
    assert not any(a.get("folder") == "Old" for a in published), "a list he left alone is not asked about"


def test_a_folder_whose_size_changed_reads_its_first_page_again(monkeypatch):
    answers = {"INBOX": {"present": {"41", "42"}, "flags": {}, "exists": 900},
               "Facturas": {"present": {"9", "8"}, "flags": {}, "exists": 8}}
    published, _, rereads = _run_tick(monkeypatch, _store("Facturas"), answers)
    assert rereads == ["Facturas"]
    assert {"folder": "Facturas", "before": None, "rows": [{"uid": "10"}], "exists": 8, "complete": True} \
        in published, "the mail that arrived (or came back) is on the list again"


def test_no_answer_from_the_server_changes_nothing(monkeypatch):
    published, reads, rereads = _run_tick(monkeypatch, _store(), {})
    assert published == [] and reads == [] and rereads == []


# ── the card: what left the folder leaves the card ───────────────────────────────────────────────────────────

def _page(folder, uids, before=None):
    return {"platform": "email", "folder": folder, "before": before, "nextBefore": None, "complete": True,
            "exists": len(uids), "rows": [{"uid": str(u), "from": "a@x.com", "subject": f"s{u}"} for u in uids]}


def test_a_gone_message_leaves_the_folder_list_and_the_home_and_comes_back_with_the_folder():
    db = data.load_db()
    db["items"] = [{"n": 1, "platform": "email", "messageId": "44", "chatId": "a@x.com"},
                   {"n": 2, "platform": "whatsapp", "messageId": "44", "chatId": "w"},
                   {"n": 3, "platform": "email", "messageId": "45", "chatId": "b@x.com"}]
    mailbox.fold(db, _page("INBOX", [45, 44, 43]))
    mailbox.fold(db, {"platform": "email", "folder": "INBOX", "gone": ["44"]})
    assert [r["uid"] for r in mailbox.view(db)["rows"]] == ["45", "43"]
    assert [(it["platform"], it["messageId"], it["n"]) for it in db["items"]] == \
        [("whatsapp", "44", 1), ("email", "45", 2)], "only the email row of that UID, renumbered"
    mailbox.fold(db, _page("INBOX", [46, 45, 43]))
    assert [r["uid"] for r in mailbox.view(db)["rows"]] == ["46", "45", "43"], "moved back: it is listed again"


def test_a_gone_message_of_another_folder_never_touches_the_inbox():
    db = data.load_db()
    db["items"] = [{"n": 1, "platform": "email", "messageId": "9", "chatId": "a@x.com"}]
    mailbox.fold(db, _page("Facturas", [9, 8]))
    mailbox.fold(db, {"platform": "email", "folder": "Facturas", "gone": ["9"]})
    assert [r["uid"] for r in (db["mailbox"]["lists"]["Facturas"]["rows"])] == ["8"]
    assert [it["messageId"] for it in db["items"]] == ["9"], "UIDs are per folder: Facturas' 9 is not INBOX's 9"


def test_entering_a_folder_marks_it_looked_at_so_the_connector_keeps_it_in_step():
    db = data.load_db()
    mailbox.go(db, "inbox")
    assert time.time() - db["mailbox"]["lists"]["INBOX"]["viewed_at"] < 5
    mailbox.fold(db, _page("INBOX", [3, 2]))
    assert service.on_screen(db) == {"INBOX": ["3", "2"]}


def test_the_owner_folds_a_gone_answer_from_the_bus(monkeypatch):
    from widgets.mensajeria import owner
    db = data.load_db()
    db["items"] = [{"n": 1, "platform": "email", "messageId": "44", "chatId": "a@x.com"}]
    data.store.save(data.WIDGET_ID, db)

    class _Sub:
        def __init__(self, evs):
            import queue
            self.queue = queue.Queue()
            for e in evs:
                self.queue.put(e)
    monkeypatch.setattr(owner._OWNER, "_mailbox_sub",
                        _Sub([{"platform": "email", "folder": "INBOX", "gone": ["44"]}]))
    owner._OWNER._apply_mailbox()
    assert [it for it in data.load_db()["items"] if it.get("platform") == "email"] == []
