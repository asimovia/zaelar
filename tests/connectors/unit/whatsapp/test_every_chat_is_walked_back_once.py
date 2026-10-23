"""Every WhatsApp chat is walked back to its beginning ONCE, into the communications archive (backfill.py).

WhatsApp keeps history on the phone: a search about something said two years ago can only be answered if the
walk already happened. These pin the walk's contract: one request in flight, the anchor is the oldest message
held, pages land in the archive and never in the widget's conversations, a chat the phone has nothing older for
is finished — and a phone that is simply not answering pauses the walk instead of writing every chat off.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from connectors.messaging import archive, ingest


@pytest.fixture
def walk(tmp_path, monkeypatch):
    from widgets import store as wstore
    from connectors.whatsapp import backfill, client
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    archive.reset()
    clock = [1_000_000.0]
    monkeypatch.setattr(backfill, "time", SimpleNamespace(time=lambda: clock[0]))
    book = [{"id": "a@s.whatsapp.net", "ts": 999_000, "lastId": "LA", "fromMe": False},
            {"id": "b@s.whatsapp.net", "ts": 998_000, "lastId": "LB", "fromMe": True},
            {"id": "c@s.whatsapp.net", "ts": 997_000, "lastId": "LC", "fromMe": False}]
    asks = []

    async def get_chats(before=None, limit=20):
        return {"chats": book, "complete": True}

    async def fetch_history(chat, oldest_id, oldest_ts, limit=30, oldest_from_me=False, include_anchor=False):
        asks.append({"chat": chat, "id": oldest_id, "ts": oldest_ts, "fromMe": oldest_from_me,
                     "include": include_anchor})
        return {"available": True, "requested": limit}

    monkeypatch.setattr(client, "get_chats", get_chats)
    monkeypatch.setattr(client, "fetch_history", fetch_history)
    w = backfill.Walker()

    def step(seconds=0):
        clock[0] += seconds
        asyncio.run(w.tick())

    yield SimpleNamespace(w=w, asks=asks, step=step, clock=clock, backfill=backfill)
    archive.reset()


def _page(chat, *ts):
    return [{"messageId": f"{chat}-{t}", "dir": "in", "from": "x", "body": f"m{t}", "ts": t} for t in ts]


def test_the_walk_goes_back_page_by_page_from_the_oldest_message_held(walk):
    walk.step()
    assert walk.asks == [{"chat": "a@s.whatsapp.net", "id": "LA", "ts": 999_000, "fromMe": False,
                          "include": True}], "nothing held yet: the chat's last message is the anchor"
    walk.step(5)
    assert len(walk.asks) == 1, "one request in flight at a time"
    walk.w.landed("a@s.whatsapp.net", _page("a@s.whatsapp.net", 900_000, 950_000))
    walk.step(5)
    assert walk.asks[-1] == {"chat": "a@s.whatsapp.net", "id": "a@s.whatsapp.net-900000", "ts": 900_000.0,
                             "fromMe": False, "include": False}, "the next page starts from the oldest held"
    assert archive.backfill_state("whatsapp", "a@s.whatsapp.net")["pages"] == 1


def test_a_chat_with_nothing_older_is_finished_and_the_walk_moves_on(walk):
    walk.step()
    walk.w.landed("a@s.whatsapp.net", _page("a@s.whatsapp.net", 900_000))
    walk.step(5)                                         # page two asked …
    walk.step(walk.backfill.WAIT_S + 1)                  # … and never answered: the beginning was reached
    assert archive.backfill_state("whatsapp", "a@s.whatsapp.net")["done"] == 1
    assert walk.asks[-1]["chat"] == "b@s.whatsapp.net" and walk.asks[-1]["fromMe"] is True
    walk.step(walk.backfill.WAIT_S + 1)                  # b: nothing at all, but the phone IS answering
    assert archive.backfill_state("whatsapp", "b@s.whatsapp.net")["done"] == 1


def test_a_phone_that_does_not_answer_pauses_the_walk_and_writes_nothing_off(walk):
    for _ in range(walk.backfill.SILENT_BEFORE_PAUSE):
        walk.step(walk.backfill.WAIT_S + 1)
    walk.step(walk.backfill.WAIT_S + 1)
    assert all(archive.backfill_state("whatsapp", c)["done"] == 0
               for c in ("a@s.whatsapp.net", "b@s.whatsapp.net", "c@s.whatsapp.net"))
    n = len(walk.asks)
    walk.step(60)
    assert len(walk.asks) == n, "paused: no request until the pause is over"
    walk.step(walk.backfill.PAUSE_S)
    assert len(walk.asks) == n + 1


def test_walk_pages_go_to_the_archive_and_not_to_the_conversation(walk, monkeypatch):
    from connectors.whatsapp import client, service
    walk.step()
    published = []
    monkeypatch.setattr(service._backfill, "walker", walk.w)
    monkeypatch.setattr(ingest, "v2_enabled", lambda: True)
    monkeypatch.setattr(ingest, "publish_history", lambda *a, **k: published.append(a[1]))

    async def get_messages():
        return [{"messageId": "old1", "chatId": "a@s.whatsapp.net", "senderName": "Ana", "body": "hace un año",
                 "timestamp": 900_000, "direction": "in", "history": True}]
    monkeypatch.setattr(client, "get_messages", get_messages)
    asyncio.run(service._ingest_new())
    assert published == [], "a walk page is not news and not scrollback on screen"
    assert archive.count("whatsapp", "a@s.whatsapp.net") == 1

    import time
    service._widget_asked["a@s.whatsapp.net"] = time.time() + 100
    try:
        asyncio.run(service._ingest_new())
        assert published == ["a@s.whatsapp.net"], "a page the operator asked for still reaches the screen"
    finally:
        service._widget_asked.pop("a@s.whatsapp.net", None)


def test_a_page_message_without_its_own_time_is_not_filed_as_now(walk):
    """History-sync timestamps are protobuf Longs; one that did not survive the wire used to fall back to «now»
    and file a two-year-old line as today's. The bridge converts them, and the walk drops what still has none."""
    import pathlib
    import re
    src = re.sub(r"//[^\n]*", "", pathlib.Path("connectors/whatsapp/bridge/bridge.js").read_text(encoding="utf-8"))
    assert "function tsNum(v)" in src and "'low' in v" in src
    assert "timestamp: tsNum(m.messageTimestamp)" in src and "timestamp: tsNum(msg.messageTimestamp)" in src
    walk.step()
    walk.w.landed("a@s.whatsapp.net", [{"messageId": "nots", "dir": "in", "from": "x", "body": "sin hora"}])
    assert archive.count("whatsapp", "a@s.whatsapp.net") == 0


def test_a_chat_written_off_before_the_phone_proved_it_answers_comes_back(walk):
    walk.step()
    walk.step(walk.backfill.WAIT_S + 1)                  # a: unanswered, nothing known about the phone yet
    assert archive.backfill_state("whatsapp", "a@s.whatsapp.net")["done"] == 1
    assert walk.asks[-1]["chat"] == "b@s.whatsapp.net"
    walk.w.landed("b@s.whatsapp.net", _page("b@s.whatsapp.net", 900_000))   # the phone answers for b
    assert archive.backfill_state("whatsapp", "a@s.whatsapp.net")["done"] == 0
