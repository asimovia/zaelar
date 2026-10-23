"""Email is the ON-DEMAND platform (connectors/messaging/history.py): the mailbox is never copied, a search asks it.

The search used to look only at the INBOX's senders and subjects, so mail the operator had archived, or a word
written inside a message, answered «nothing». It now asks the INBOX and the server's archive folder (Gmail's
«All Mail»), by sender, recipient, subject or text — read-only — and a hit outside the INBOX is keyed by its
Message-ID, because UIDs are per folder and the INBOX's are what mark-seen acts on.
"""
from __future__ import annotations

from connectors.email import search
from connectors.messaging import history


def _raw(mid, sender, subject, body):
    return (f"From: {sender} <{sender}>\r\nTo: me@example.test\r\nSubject: {subject}\r\nMessage-ID: <{mid}>\r\n"
            f"Date: Mon, 01 Sep 2025 10:00:00 +0000\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n{body}\r\n"
            ).encode()


class _IMAP:
    def __init__(self):
        self.selected, self.readonly, self.criteria = None, [], []
        self.folders = {
            "INBOX": {7: _raw("a@x", "ana@example.test", "Barco", "el precio del barco es 12.000")},
            "[Gmail]/All Mail": {3: _raw("a@x", "ana@example.test", "Barco", "el precio del barco es 12.000"),
                                 2: _raw("b@x", "luis@example.test", "Viejo", "lo del barco que archivé")},
        }

    def list(self):
        return "OK", [b'(\\HasNoChildren) "/" "INBOX"', b'(\\All \\HasNoChildren) "/" "[Gmail]/All Mail"']

    def select(self, name, readonly=False):
        self.selected = name.strip('"')
        self.readonly.append(readonly)
        return "OK", [b"1"]

    def uid(self, cmd, *args):
        if cmd == "search":
            self.criteria.append(args[1:])
            return "OK", [" ".join(str(u) for u in self.folders[self.selected]).encode()]
        uid = int(args[0])
        assert args[1] == "(BODY.PEEK[])", "looking for a mail must never mark it read"
        return "OK", [(b"x", self.folders[self.selected][uid])]

    def logout(self):
        pass


class _MB:
    def __init__(self, im):
        self.im = im

    def _imap(self):
        return self.im


def test_the_inbox_and_the_archive_folder_are_asked_by_any_field_and_read_only():
    im = _IMAP()
    hits = search.search_text(_MB(im), ["barco"], limit=10, media_dir="/nowhere")
    assert [h["messageId"] for h in hits] == ["7", "mid:<b@x>"], \
        "INBOX hit by UID; the archived one by Message-ID; the copy in both folders only once"
    assert all(im.readonly) and len(im.readonly) == 2
    assert all("TEXT" in c and "TO" in c and "FROM" in c and "SUBJECT" in c for c in im.criteria)
    assert hits[1]["folder"] == "[Gmail]/All Mail"


def test_email_is_never_walked_and_the_chat_platforms_are():
    assert history.mode("email") == "on_demand" and not history.walk_enabled("email")
    assert history.mode("whatsapp") == history.mode("telegram") == "walk"


def test_a_search_answer_says_how_far_each_platforms_past_reaches(tmp_path, monkeypatch):
    from connectors.messaging import archive
    from widgets import store as wstore
    from widgets.mensajeria import views
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    archive.reset()
    monkeypatch.setattr(views, "mailbox_fill", lambda terms: 0)
    archive.backfill_mark("whatsapp", "a@s.whatsapp.net", done=True)
    archive.backfill_mark("whatsapp", "b@s.whatsapp.net", page=True)
    res = views._search_archive_answer({"q": "barco"})["result"]
    assert res["history"]["email"]["mode"] == "on_demand"
    assert res["history"]["whatsapp"] == {"mode": "walk", "done": 1, "started": 2, "messages": 0}
    assert "whatsapp: 1 de 2 chats" in res["detail"], "«nothing found» must say the walk is still going"
    archive.reset()
