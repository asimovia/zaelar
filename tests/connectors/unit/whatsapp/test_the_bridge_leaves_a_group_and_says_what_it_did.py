"""The WhatsApp bridge leaves a group and says what it did.

`leave_group` (the messaging card) reaches the connector as `msg.group_leave`: the client posts each chat to the
bridge's `/group/leave`, which leaves it (`groupLeave`) and, best effort, deletes the chat (`chatModify` delete);
the drain answers with the chats that are gone (`connector.chats_gone`) and ONE `msg.send_failed` naming the ones that
stayed. The bridge is vendored JS with no harness of its own, so its seams are pinned in source, comment-stripped.
"""
from __future__ import annotations

import asyncio
import pathlib
import re
import shutil
import subprocess

import pytest

from connectors.messaging import group_leave, ingest
from connectors.whatsapp import client

BRIDGE = pathlib.Path("connectors/whatsapp/bridge/bridge.js")
BOOK = "120363600112233@g.us"
SHOPPING = "120363915550000@g.us"


class _Inbox:
    def __init__(self, orders):
        self._orders = orders

    def drain(self):
        out, self._orders = self._orders, []
        return out


@pytest.fixture
def heard(monkeypatch):
    out = {"gone": [], "failed": [], "notes": []}
    monkeypatch.setattr(group_leave, "publish_chats_gone", lambda p, ids, ref="": out["gone"].append((p, list(ids), ref)))
    monkeypatch.setattr(ingest, "publish_send_failed", lambda order, reason: out["failed"].append((order["ref"], reason)))
    from connectors.whatsapp import service as wa
    monkeypatch.setattr(wa, "_note", lambda text: out["notes"].append(text))
    return out


def _order(*chats):
    return {"platform": "whatsapp", "ref": "r1", "chats": [{"chatId": c, "name": n} for c, n in chats]}


def test_the_client_posts_the_chat_to_the_leave_endpoint(monkeypatch):
    seen = []

    async def fake(method, path, *, body=None, timeout=15.0):
        seen.append((method, path, body))
        return {"left": True, "deleted": True}

    monkeypatch.setattr(client, "_request", fake)
    got = asyncio.run(client.leave_group(BOOK))
    assert seen == [("POST", "/group/leave", {"chatId": BOOK})] and got == {"left": True, "deleted": True}


def test_every_chat_that_left_is_one_gone_echo_and_a_failure_names_the_one_that_stayed(monkeypatch, heard):
    from connectors.whatsapp import service as wa

    async def leave(chat_id):
        if chat_id == SHOPPING:
            raise client.BridgeError("POST /group/leave → 500", status=500, error="not-authorized")
        return {"left": True, "deleted": False, "why": "no anchor message for this chat"}

    monkeypatch.setattr(client, "leave_group", leave)
    monkeypatch.setattr(wa, "_group_leave_inbox", _Inbox([_order((BOOK, "Book club"), (SHOPPING, "Shopping list"))]))
    asyncio.run(wa._drain_group_leaves())
    assert heard["gone"] == [("whatsapp", [BOOK], "r1")], "left even when the phone kept the chat: he is out of it"
    assert len(heard["failed"]) == 1 and "Shopping list" in heard["failed"][0][1] and "Book club" not in heard["failed"][0][1]
    assert len(heard["notes"]) == 1 and "Shopping list" in heard["notes"][0]


def test_an_answer_that_does_not_say_it_left_is_a_failure(monkeypatch, heard):
    from connectors.whatsapp import service as wa

    async def leave(chat_id):
        return {}

    monkeypatch.setattr(client, "leave_group", leave)
    monkeypatch.setattr(wa, "_group_leave_inbox", _Inbox([_order((BOOK, "Book club"))]))
    asyncio.run(wa._drain_group_leaves())
    assert heard["gone"] == [] and heard["failed"] and "Book club" in heard["failed"][0][1]


def test_disarmed_without_the_left_check_a_silent_bridge_reads_as_gone(monkeypatch, heard):
    from connectors.whatsapp import service as wa
    from connectors.whatsapp.service import leave as wa_leave

    async def leave(chat_id):
        return {}

    async def unguarded(chat_id):
        await client.leave_group(chat_id)

    monkeypatch.setattr(client, "leave_group", leave)
    monkeypatch.setattr(wa_leave, "_leave_one", unguarded)
    monkeypatch.setattr(wa, "_group_leave_inbox", _Inbox([_order((BOOK, "Book club"))]))
    asyncio.run(wa._drain_group_leaves())
    assert heard["gone"] == [("whatsapp", [BOOK], "r1")]


def test_the_loop_drains_group_leaves_and_owns_its_inbox():
    src = pathlib.Path("connectors/whatsapp/service/__init__.py").read_text(encoding="utf-8")
    assert '("group leaves", _drain_group_leaves)' in src and "GroupLeaveInbox(PLATFORM)" in src


# --- bridge.js: the wiring exists, and the file parses ------------------------------------------------------

def test_the_bridge_leaves_the_group_deletes_the_chat_and_forgets_it():
    raw = BRIDGE.read_text(encoding="utf-8")
    assert "// ZAELAR-PATCH (leave group): LEAVE a group" in raw
    src = re.sub(r"//[^\n]*", "", raw)
    for needle in ("app.post('/group/leave'", "sock.groupLeave(jid)", "sock.chatModify({ delete: true, lastMessages:",
                   "chatBook.delete(jid)", "leftChats.add(jid)", "leftChats.has(id)", "left: true, deleted",
                   "participant: msg.key.participant"):
        assert needle in src, needle
    assert "POST /group/leave" in pathlib.Path("connectors/whatsapp/bridge/VENDORED_FROM.md").read_text(encoding="utf-8")


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not on PATH")
def test_the_bridge_parses():
    r = subprocess.run(["node", "--check", str(BRIDGE)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
