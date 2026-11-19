"""INI-042 #34 — the owner's beat does not parse the whole messaging store to find an empty queue.

The beat drains a dozen queues every tick on the engine's loop thread, and each `take_*` parsed the WHOLE store: 2.4 s
of a frozen loop on a hosted account. Now a drain whose queue was empty in a file that has not changed since the last
read answers «nothing» without reading it; any write (an atomic replace) is seen by the very next drain.
"""
from __future__ import annotations

import pytest

from connectors.messaging import store as msgstore
from widgets import store as wstore


@pytest.fixture
def reads(monkeypatch, tmp_path):
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(wstore, "_last_hash", {})
    monkeypatch.setitem(msgstore._SEEN, "sig", None)
    count = {"n": 0}
    real = wstore.load

    def counting(widget_id, default=None, **kw):
        if widget_id == msgstore.WIDGET_ID:
            count["n"] += 1
        return real(widget_id, default, **kw)

    counting.__module__ = wstore.__name__          # the real reader, counted — not a test double of the file
    monkeypatch.setattr(wstore, "load", counting)
    msgstore.save(msgstore._empty())
    return count


_DRAINS = (msgstore.take_pending_read, msgstore.take_pending_unread, msgstore.take_pending_reply,
           msgstore.take_pending_send, msgstore.take_pending_history, msgstore.take_pending_fetch,
           msgstore.take_pending_group, msgstore.take_pending_group_leave, msgstore.take_pending_chats,
           msgstore.take_control, lambda: msgstore.take_pending_disposal("archive"),
           lambda: msgstore.take_pending_disposal("trash"))


def test_a_beat_over_empty_queues_reads_the_store_once(reads):
    msgstore.load()
    reads["n"] = 0
    for _ in range(3):                              # three beats
        assert all(drain() == [] for drain in _DRAINS)
    assert reads["n"] == 0


def test_a_write_is_seen_by_the_next_drain(reads):
    msgstore.load()
    assert msgstore.take_pending_send() == []
    db = msgstore.load()
    db["pending_send"] = [{"ref": "r1", "platform": "telegram", "to": "@x", "text": "hola"}]
    msgstore.save(db)
    assert [o["ref"] for o in msgstore.take_pending_send()] == ["r1"]
    assert msgstore.take_pending_send() == []
    db = msgstore.load()
    db["pending_read"] = [{"platform": "telegram", "chatId": "1", "messageId": "m"}]
    msgstore.save(db)
    assert len(msgstore.take_pending_read()) == 1


def test_a_patched_store_is_always_read(reads, monkeypatch):
    msgstore.load()
    fake = msgstore._empty()
    fake["pending_send"] = [{"ref": "r2"}]
    monkeypatch.setattr(msgstore, "load", lambda: fake)
    monkeypatch.setattr(msgstore, "save", lambda db: db)
    assert [o["ref"] for o in msgstore.take_pending_send()] == ["r2"]


def test_the_owners_whole_flush_over_empty_queues_never_reads_the_store(reads, monkeypatch):
    """The flush's last drain (the email section's page orders) read the whole store every beat on its own."""
    from connectors.messaging import ingest
    from widgets.mensajeria.owner.handle import _Handle
    asked = []
    monkeypatch.setattr(ingest, "publish_mailbox_ask", asked.append)
    msgstore.load()
    reads["n"] = 0
    for _ in range(3):
        _Handle()._flush_queues()
    assert reads["n"] == 0 and asked == []
    db = msgstore.load()
    db["pending_mail"] = [{"platform": "email", "folder": "INBOX"}]
    msgstore.save(db)
    _Handle()._flush_queues()
    assert [o["folder"] for o in asked] == ["INBOX"], "an order written since is published by the next flush"
    assert msgstore.load().get("pending_mail") == [], "and taken off the queue"
