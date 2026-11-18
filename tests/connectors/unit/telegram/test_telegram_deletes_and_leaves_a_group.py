"""Telegram leaves a group the way its app's «Delete and leave» does: Telethon's `delete_dialog` leaves the group or
channel and removes the dialog. The drain answers the order like WhatsApp's: the chats gone, and one failure naming
the ones that stayed.
"""
from __future__ import annotations

import asyncio

import pytest

from connectors.messaging import group_leave, ingest


class _Inbox:
    def __init__(self, orders):
        self._orders = orders

    def drain(self):
        out, self._orders = self._orders, []
        return out


class _Client:
    def __init__(self, broken=()):
        self.deleted, self._broken = [], set(broken)

    async def get_input_entity(self, ref):
        return ("peer", ref)

    async def delete_dialog(self, entity):
        if entity[1] in self._broken:
            raise RuntimeError("CHAT_ADMIN_REQUIRED")
        self.deleted.append(entity[1])


@pytest.fixture
def heard(monkeypatch):
    out = {"gone": [], "failed": [], "notes": []}
    monkeypatch.setattr(group_leave, "publish_chats_gone", lambda p, ids, ref="": out["gone"].append((p, list(ids), ref)))
    monkeypatch.setattr(ingest, "publish_send_failed", lambda order, reason: out["failed"].append(reason))
    from connectors.telegram import service as tg
    monkeypatch.setattr(tg, "_note", lambda text: out["notes"].append(text))
    return out


def _run(monkeypatch, cli):
    from connectors.telegram import service as tg
    monkeypatch.setattr(tg, "_client", cli)
    monkeypatch.setattr(tg, "_group_leave_inbox", _Inbox([{"platform": "telegram", "ref": "r9", "chats": [
        {"chatId": "-100600000311", "name": "Shopping list"}, {"chatId": "-100600000020", "name": "Book club"}]}]))
    asyncio.run(tg._drain_group_leaves())


def test_each_group_is_deleted_and_left_and_answered_as_gone(monkeypatch, heard):
    cli = _Client()
    _run(monkeypatch, cli)
    assert cli.deleted == [-100600000311, -100600000020], "a numeric id is resolved as the peer id it is"
    assert heard["gone"] == [("telegram", ["-100600000311", "-100600000020"], "r9")] and not heard["failed"]


def test_a_group_that_would_not_let_him_go_is_named_in_the_one_failure(monkeypatch, heard):
    _run(monkeypatch, _Client(broken={-100600000020}))
    assert heard["gone"] == [("telegram", ["-100600000311"], "r9")]
    assert len(heard["failed"]) == 1 and "Book club" in heard["failed"][0] and "Shopping list" not in heard["failed"][0]
    assert len(heard["notes"]) == 1


def test_disarmed_without_the_failure_answer_a_partial_leave_reads_as_complete(monkeypatch, heard):
    real = group_leave.leave_each

    async def no_failure_answer(platform, order, leave_one):
        monkeypatch.setattr(ingest, "publish_send_failed", lambda order, reason: None)
        return await real(platform, order, leave_one)

    monkeypatch.setattr(group_leave, "leave_each", no_failure_answer)
    _run(monkeypatch, _Client(broken={-100600000020}))
    assert heard["gone"] == [("telegram", ["-100600000311"], "r9")] and heard["failed"] == []
