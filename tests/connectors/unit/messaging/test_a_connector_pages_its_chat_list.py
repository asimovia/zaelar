"""Each messaging connector answers `msg.chats` with one page of its chat list.

Telegram walks the account's real dialogs; WhatsApp answers from the chat book its bridge has been told since
pairing. The cursor is the connector's: Telegram floats pinned dialogs to the head of the first page whatever
their age, so «the oldest row of the page» would jump the next page back to the day a pinned chat was last used.
The bridge is vendored JS with no harness of its own, so its seams are pinned in source, comment-stripped.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import pathlib
import re
from types import SimpleNamespace

import pytest

from connectors.messaging import ingest


@pytest.fixture
def published(monkeypatch):
    seen = []
    monkeypatch.setattr(ingest, "publish_chats", lambda platform, chats, **kw: seen.append((platform, chats, kw)))
    return seen


class _Inbox:
    def __init__(self, orders):
        self._orders = orders

    def drain(self):
        out, self._orders = self._orders, []
        return out


def _dialog(i, hours_ago, *, pinned=False, kind="person"):
    date = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours_ago)
    msg = SimpleNamespace(message=f"hola {i}", out=False, id=100 + i, media=None, photo=None, document=None)
    return SimpleNamespace(
        id=i, name=f"chat {i}", is_user=kind == "person", is_group=kind == "group",
        is_channel=kind in ("group", "channel"),
        unread_count=i % 3, date=date, message=msg, pinned=pinned, archived=False,
        dialog=SimpleNamespace(notify_settings=SimpleNamespace(mute_until=None)),
        entity=SimpleNamespace(forum=False))


def test_telegram_pages_its_dialogs_and_the_cursor_skips_pinned_ones(monkeypatch, published):
    from connectors.telegram import service as tg
    dialogs = [_dialog(1, 2000, pinned=True), _dialog(2, 1), _dialog(3, 5), _dialog(4, 9)]
    asked = {}

    class _Client:
        async def iter_dialogs(self, limit, offset_date=None):
            asked.update(limit=limit, offset_date=offset_date)
            for d in dialogs[:limit]:
                yield d

    monkeypatch.setattr(tg, "_client", _Client())
    monkeypatch.setattr(tg, "_chats_inbox", _Inbox([{"platform": "telegram", "before": None, "limit": 4}]))
    asyncio.run(tg._drain_chats())
    platform, rows, kw = published[-1]
    assert platform == "telegram" and [r["chatId"] for r in rows] == ["1", "2", "3", "4"]
    assert kw["next_before"] == pytest.approx(dialogs[3].date.timestamp()), \
        "the cursor is the oldest UNPINNED dialog, not the pinned one at the head"
    assert rows[0]["pinned"] and rows[1]["preview"] == "hola 2" and rows[1]["lastId"] == "102"
    assert not kw["complete"], "a full page may have more behind it"

    monkeypatch.setattr(tg, "_chats_inbox", _Inbox([{"platform": "telegram", "before": 1700000000, "limit": 20}]))
    asyncio.run(tg._drain_chats())
    assert asked["offset_date"] == dt.datetime.fromtimestamp(1700000000, dt.timezone.utc)
    assert published[-1][2]["complete"], "fewer than asked: nothing older exists"


def test_whatsapp_answers_from_the_bridge_book(monkeypatch, published):
    from connectors.whatsapp import client, service as wa

    async def get_chats(before=None, limit=20):
        assert before == 1700000000 and limit == 20
        return {"chats": [
            {"id": "34600@s.whatsapp.net", "name": "Ana", "isGroup": False, "unread": 2, "ts": 1699999000,
             "preview": "¿vienes?", "lastId": "X1"},
            {"id": "123@g.us", "name": "Viaje", "isGroup": True, "ts": 1699990000, "archived": True},
        ], "complete": True, "known": 2}

    monkeypatch.setattr(client, "get_chats", get_chats)
    monkeypatch.setattr(wa, "_chats_inbox", _Inbox([{"platform": "whatsapp", "before": 1700000000}]))
    asyncio.run(wa._drain_chats())
    platform, rows, kw = published[-1]
    assert [(r["chatId"], r["kind"]) for r in rows] == [("34600@s.whatsapp.net", "person"), ("123@g.us", "group")]
    assert rows[0]["unread"] == 2 and rows[0]["lastId"] == "X1" and rows[1]["archived"]
    assert kw == {"before": 1700000000, "next_before": 1699990000.0, "complete": True}


def test_a_connector_that_fails_says_so(monkeypatch, published):
    from connectors.whatsapp import client, service as wa

    async def broken(*a, **k):
        raise client.BridgeError("GET /chats → 503")

    monkeypatch.setattr(client, "get_chats", broken)
    monkeypatch.setattr(wa, "_chats_inbox", _Inbox([{"platform": "whatsapp", "before": None}]))
    asyncio.run(wa._drain_chats())
    assert "503" in published[-1][2]["error"]


# ── the bridge ───────────────────────────────────────────────────────────────────────────────────────────
_SRC = re.sub(r"//[^\n]*", "", pathlib.Path("connectors/whatsapp/bridge/bridge.js").read_text(encoding="utf-8"))


def test_the_bridge_keeps_a_chat_book_across_restarts():
    assert "CHAT_BOOK_FILE = path.join(SESSION_DIR" in _SRC
    assert "readFileSync(CHAT_BOOK_FILE" in _SRC and "writeFileSync(CHAT_BOOK_FILE" in _SRC
    assert "groupFetchAllParticipating" in _SRC, "groups are seeded on connect"


def test_the_history_sync_feeds_the_book_and_on_demand_history_reaches_the_conversation():
    handler = _SRC.split("sock.ev.on('messaging-history.set'", 1)[1].split("sock.ev.on(", 1)[0]
    assert "rememberChat(c.id" in handler
    assert "syncType !== 6" in handler, "only ON_DEMAND pages are scrollback"
    assert "history: true" in handler, "an asked-for page must never be triaged as news"


def test_a_page_never_ships_the_stored_last_message_and_the_anchor_is_served_on_request():
    route = _SRC.split("app.get('/chats'", 1)[1].split("app.", 1)[0]
    assert "const { last, ...row } = c;" in route
    hist = _SRC.split("app.post('/history'", 1)[1].split("app.", 1)[0]
    assert "includeAnchor && book?.last && book.lastId === oldestId" in hist
    assert "fromMe: !!oldestFromMe" in hist


def test_a_telegram_chat_opened_from_the_list_includes_its_last_message(monkeypatch):
    """The list knows the chat's last message id; asking for what came BEFORE it would leave a one-message
    chat empty. `includeAnchor` moves the offset past it."""
    from connectors.telegram import service as tg
    seen = {}

    class _Client:
        async def get_messages(self, chat, limit, offset_id):
            seen["offset_id"] = offset_id
            return []

    monkeypatch.setattr(tg, "_client", _Client())
    monkeypatch.setattr(ingest, "publish_history", lambda *a, **k: None)
    monkeypatch.setattr(tg, "_history_inbox", _Inbox([{"platform": "telegram", "chatId": "42", "beforeId": "77",
                                                       "includeAnchor": True}]))
    asyncio.run(tg._drain_history())
    assert seen["offset_id"] == 78
    monkeypatch.setattr(tg, "_history_inbox", _Inbox([{"platform": "telegram", "chatId": "42", "beforeId": "77"}]))
    asyncio.run(tg._drain_history())
    assert seen["offset_id"] == 77, "«load previous» still walks strictly backwards"
