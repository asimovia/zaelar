"""A messaging platform opens on its CHAT LIST, the first screen of the real app (widgets/mensajeria/chatlist.py).

Entering WhatsApp or Telegram showed only what triage kept, so an account with a hundred conversations and
nothing unread opened on an empty card. The list is now its own thing: the connector hands pages of chats over
`msg.chats`, the widget keeps them in `chat_index`, shows what moved in the recent window and walks back a page
at a time, and a chat opened from it fetches its own messages.
"""
from __future__ import annotations

import time

import pytest

from connectors.messaging import store as msgstore
from widgets import store as wstore
from widgets.mensajeria import chatlist, data


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    from nucleo import consent
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path / "ws"))
    consent._reset_for_tests()
    db = data.load_db()
    db.setdefault("platforms", {})["telegram"] = {"status": "connected"}
    db["platforms"]["whatsapp"] = {"status": "connected"}
    wstore.save("mensajeria", db)
    yield
    consent._reset_for_tests()


def _page(platform, rows, *, before=None, next_before=None, complete=False):
    msgstore.add_chats(platform, {"chats": rows, "before": before, "nextBefore": next_before,
                                  "complete": complete})


def _chat(cid, hours_ago, **kw):
    return {"chatId": cid, "name": kw.pop("name", cid), "kind": kw.pop("kind", "person"),
            "ts": time.time() - hours_ago * 3600, "unread": kw.pop("unread", 0), **kw}


def _asks():
    return data.load_db().get("pending_chats") or []


def test_entering_a_platform_asks_its_first_page_once():
    data.apply_action("show_view", {"platform": "telegram"})
    assert _asks() == [{"platform": "telegram", "before": None, "limit": chatlist.PAGE}]
    data.apply_action("show_view", {"platform": "telegram"})
    assert len(_asks()) == 1, "an ask still in flight must not be queued twice"
    data.apply_action("show_view", {"platform": "email"})
    assert len(_asks()) == 1, "email has no chat list"


def test_the_list_shows_the_recent_window_newest_first_and_never_an_empty_screen():
    rows = [_chat(f"c{i}", hours_ago=i * 10) for i in range(30)]          # c0..c7 inside 72 h
    _page("telegram", rows, next_before=rows[-1]["ts"])
    v = data.view_data()["chat_list"]["telegram"]
    ids = [r["chatId"] for r in v["rows"]]
    assert ids == [f"c{i}" for i in range(chatlist.MIN_SHOWN)], "8 recent ones, topped up to MIN_SHOWN"
    assert v["more"] and not v["complete"]

    _page("whatsapp", [_chat("old", hours_ago=500)], complete=True)
    w = data.view_data()["chat_list"]["whatsapp"]
    assert [r["chatId"] for r in w["rows"]] == ["old"], "a quiet week still shows the latest chats"
    assert not w["more"]


def test_load_more_walks_back_and_asks_the_connector_when_the_index_runs_short():
    rows = [_chat(f"c{i}", hours_ago=100 + i) for i in range(25)]
    _page("telegram", rows, next_before=rows[-1]["ts"])
    data.apply_action("show_view", {"platform": "telegram"})          # answered just now: no refresh ask
    assert _asks() == []
    r = data.apply_action("chats_more", {"platform": "telegram"})
    assert r["ok"] and len(data.view_data()["chat_list"]["telegram"]["rows"]) == 25
    assert _asks() == [{"platform": "telegram", "before": rows[-1]["ts"], "limit": chatlist.PAGE}], \
        "fewer than a page left in the index: the next page is asked with the connector's cursor"


def test_refreshing_the_first_page_keeps_the_deeper_cursor():
    first = [_chat(f"a{i}", hours_ago=i) for i in range(20)]
    _page("telegram", first, next_before=first[-1]["ts"])
    second = [_chat(f"b{i}", hours_ago=100 + i) for i in range(20)]
    _page("telegram", second, before=first[-1]["ts"], next_before=second[-1]["ts"])
    _page("telegram", first[:5], next_before=first[4]["ts"])            # entering again refreshed page one
    idx = data.load_db()["chat_index"]["telegram"]
    assert idx["cursor"] == second[-1]["ts"]
    _page("telegram", [], before=second[-1]["ts"], complete=True)
    assert data.load_db()["chat_index"]["telegram"]["complete"]
    assert data.apply_action("chats_more", {"platform": "telegram"})["result"]["asked"] is False


def test_live_conversations_and_the_inbox_move_the_rows():
    _page("whatsapp", [_chat("111", hours_ago=50, name="Ana", preview="viejo")])
    db = data.load_db()
    now = time.time()
    db["threads"] = {"whatsapp|111": {"name": "Ana", "msgs": [
        {"id": "m1", "dir": "in", "who": "Ana", "body": "¿quedamos?", "ts": now - 60, "read": False}]}}
    db["items"] = [{"platform": "whatsapp", "chatId": "111", "messageId": "m1", "from": "Ana",
                    "body": "¿quedamos?", "dirigido_a_mi": True}]
    wstore.save("mensajeria", db)
    row = data.view_data()["chat_list"]["whatsapp"]["rows"][0]
    assert row["preview"] == "¿quedamos?" and row["ts"] >= now - 61
    assert row["pending"] == 1 and row["forMe"]


def test_a_chat_opened_from_the_list_fetches_its_messages_and_stays_open_meanwhile():
    _page("whatsapp", [_chat("555@s.whatsapp.net", hours_ago=2, name="Luis", lastId="ABC", fromMe=False)])
    r = data.apply_action("open", {"platform": "whatsapp", "chatId": "555@s.whatsapp.net"})
    assert r["active_chat"] == {"platform": "whatsapp", "chatId": "555@s.whatsapp.net"}
    db = data.load_db()
    assert db["threads"]["whatsapp|555@s.whatsapp.net"]["name"] == "Luis"
    ask = db["pending_history"][-1]
    assert ask["beforeId"] == "ABC" and ask["includeAnchor"] and ask["beforeFromMe"] is False
    again = data.view_data()
    assert again["active_chat"], "an empty thread waiting for its messages must not auto-close"
    assert again["opening"]

    db = data.load_db()
    db["opening"]["at"] = time.time() - 3600
    wstore.save("mensajeria", db)
    assert data.view_data()["active_chat"] is None, "once the wait is over, an empty thread closes as before"


def test_a_read_on_the_phone_zeroes_the_counter():
    _page("whatsapp", [_chat("777", hours_ago=1, unread=4)])
    msgstore.apply_external_read("whatsapp", "777")
    assert data.view_data()["chat_list"]["whatsapp"]["rows"][0]["unread"] == 0


def test_the_archive_fills_in_what_the_connector_can_no_longer_list():
    """WhatsApp tells a linked device its chats once, at pairing; every chat the archive already holds is a
    conversation the list can still show, with its last message — and a row the app sent wins over it."""
    from connectors.messaging import archive
    archive.reset()
    now = time.time()
    archive.record("whatsapp", "999@s.whatsapp.net", [
        {"messageId": "o1", "body": "lo de siempre", "ts": now - 900 * 3600},
        {"messageId": "o2", "body": "¿y el barco?", "ts": now - 800 * 3600}], direction="in", chat_name="Pepe")
    archive.record("whatsapp", "555@s.whatsapp.net", [
        {"messageId": "p1", "body": "archivo", "ts": now - 5 * 3600}], direction="in", chat_name="Luis viejo")
    _page("whatsapp", [_chat("555@s.whatsapp.net", hours_ago=1, name="Luis", preview="nuevo")])
    rows = {r["chatId"]: r for r in data.view_data()["chat_list"]["whatsapp"]["rows"]}
    assert rows["999@s.whatsapp.net"]["preview"] == "¿y el barco?" and rows["999@s.whatsapp.net"]["name"] == "Pepe"
    assert rows["555@s.whatsapp.net"]["name"] == "Luis" and rows["555@s.whatsapp.net"]["preview"] == "nuevo"
    archive.reset()
