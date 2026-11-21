"""How much of an account's PAST is copied, and how much media stays on the disk, are declared bounds (V2-936).

Measured on one real account: the history walk had copied every conversation back to 2020 (168 000 messages) and
fourteen days of downloaded media were 1.9 GB, one file of 136 MB. Now:

  · the FIRST import walks the newest conversations only, each back to the day bound or its message bound, and
    stops at its own total (`config/messaging.default.json`, read by `history.policy`);
  · what arrives live is always archived — no bound applies to it;
  · a conversation somebody asks about is copied further back ON DEMAND, by id or by the name they used, a bounded
    stretch per ask (`archive.want` → the walker), and a search that names a conversation and finds nothing asks;
  · a file over the per-file cap is not downloaded by itself, and downloaded media leaves oldest first when it is
    over its disk budget, whatever the day window says;
  · a message from an account no contact row holds marks its source as owed a read of the platform's book.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import os
import time
from types import SimpleNamespace

import pytest

from connectors.messaging import archive, history

NOW = dt.datetime.now(dt.timezone.utc)


@pytest.fixture
def tg(tmp_path, monkeypatch):
    from widgets import store as wstore
    from connectors.telegram import backfill
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    archive.reset()
    history._POLICY.clear()
    monkeypatch.setattr(backfill, "GAP_S", 0)
    monkeypatch.setattr(backfill, "WANT_RELIST_S", 3600)
    yield backfill
    archive.reset()
    history._POLICY.clear()


def _bounds(monkeypatch, **kw):
    monkeypatch.setattr(history, "_DEFAULTS", {**history._DEFAULTS, **kw})
    monkeypatch.setattr(history, "_files", lambda: [])
    history._POLICY.clear()


def _dialog(i, days_ago=1, *, channel=False, group=False, name=""):
    return SimpleNamespace(id=i, name=name or f"chat {i}", is_channel=channel or group, is_group=group, entity=i,
                           date=NOW - dt.timedelta(days=days_ago))


def _msg(i, days_ago):
    return SimpleNamespace(id=i, message=f"m{i}", out=False, media=None, photo=None, document=None, voice=None,
                           video=None, video_note=None, audio=None, date=NOW - dt.timedelta(days=days_ago),
                           get_sender=None)


class _Client:
    """`history[chat] = {msg id: days ago}`; ids grow with time, as on the platform."""

    def __init__(self, dialogs, hist):
        self.dialogs, self.hist, self.asked = dialogs, hist, []

    async def iter_dialogs(self, limit):
        for d in self.dialogs:
            yield d

    async def get_messages(self, entity, limit, offset_id):
        self.asked.append(entity)
        rows = self.hist.get(entity, {})
        older = sorted((i for i in rows if not offset_id or i < offset_id), reverse=True)[:limit]
        return [_msg(i, rows[i]) for i in older]


def _run(backfill, client, ticks, walker=None):
    async def go():
        w = walker or backfill.Walker()
        for _ in range(ticks):
            await w.tick(client)
            if w.task:
                await w.task
        return w
    return asyncio.run(go())


def _chat(n, newest_days=1, step=1.0):
    """`n` messages, the newest `newest_days` ago and each earlier one `step` days before."""
    return {i: newest_days + (n - i) * step for i in range(1, n + 1)}


# ── the first import ──────────────────────────────────────────────────────────────────────────────────────────

def test_the_declared_file_and_the_fallback_say_the_same_numbers():
    import json
    declared = {k: v for k, v in json.load(open("config/messaging.default.json", encoding="utf-8")).items()
                if not k.startswith("_")}
    assert declared == history._DEFAULTS
    assert history.policy()["initial_days"] == 90 and history.policy()["media_file_mb"] == 20


def test_a_conversation_is_copied_back_to_the_day_bound_and_no_further(tg, monkeypatch):
    _bounds(monkeypatch, initial_days=30)
    client = _Client([_dialog(1)], {1: _chat(60, 0.5)})            # one message a day for sixty days
    _run(tg, client, ticks=6)
    assert archive.count("telegram", "1") == 30, "thirty days of it, not its beginning"
    assert archive.backfill_state("telegram", "1")["done"] == 1
    asked = len(client.asked)
    _run(tg, client, ticks=3)
    assert len(client.asked) == asked, "a conversation whose first import is over is not walked again"


def test_a_conversation_stops_at_its_message_bound(tg, monkeypatch):
    _bounds(monkeypatch, initial_per_chat=150)
    client = _Client([_dialog(1)], {1: _chat(400, step=0.01)})
    _run(tg, client, ticks=8)
    assert archive.count("telegram", "1") == 150


def test_only_the_newest_conversations_are_walked_and_a_stale_or_broadcast_one_is_not(tg, monkeypatch):
    _bounds(monkeypatch, initial_chats=2)
    dialogs = [_dialog(9, days_ago=400), _dialog(1, 1), _dialog(2, 2), _dialog(3, 3), _dialog(4, 1, channel=True)]
    client = _Client(dialogs, {i: _chat(5) for i in (1, 2, 3, 4, 9)})
    _run(tg, client, ticks=10)
    assert set(client.asked) == {1, 2}, "the pinned old chat, the third newest and the channel are left where they are"
    _bounds(monkeypatch, initial_chats=10)
    client = _Client([_dialog(9, days_ago=400), _dialog(5, 1)], {5: _chat(5), 9: _chat(5, 400)})
    _run(tg, client, ticks=6)
    assert set(client.asked) == {5}, "a conversation with nothing inside the day bound is not asked at all"


def test_the_whole_import_stops_at_its_total(tg, monkeypatch):
    _bounds(monkeypatch, initial_messages=120)
    client = _Client([_dialog(1, 1), _dialog(2, 2)], {1: _chat(100, step=0.01), 2: _chat(100, 2, step=0.01), })
    w = _run(tg, client, ticks=12)
    asked = len(client.asked)
    _run(tg, client, ticks=5, walker=w)
    assert w.full and len(client.asked) == asked, "over its total the import asks the platform nothing more"
    assert archive.held("telegram") == 120 and archive.count("telegram", "2") == 20, "newest conversation first"


def test_what_the_phone_sends_at_pairing_is_trimmed_to_the_same_bounds(monkeypatch):
    _bounds(monkeypatch, initial_days=30, initial_per_chat=3)
    now = time.time()
    rows = [{"messageId": f"m{d}", "ts": now - d * 86400} for d in (1, 5, 10, 20, 45, 200)]
    kept = history.within_first_import(rows)
    assert [r["messageId"] for r in kept] == ["m1", "m5", "m10"], "inside the days, the newest that fit"
    assert history.within_first_import(rows, held=3) == []
    assert len(history.within_first_import(rows, per_chat=False)) == 4, "a history handed over once: the days alone"
    _bounds(monkeypatch, initial_days=0, initial_per_chat=0)
    assert len(history.within_first_import(rows)) == 6, "0 switches a bound off"


# ── on demand ─────────────────────────────────────────────────────────────────────────────────────────────────

def test_a_conversation_asked_about_is_copied_further_back_a_stretch_per_ask(tg, monkeypatch):
    _bounds(monkeypatch, initial_days=30, deep_messages=200)
    client = _Client([_dialog(1)], {1: _chat(600, 0.5)})
    w = _run(tg, client, ticks=6)
    assert archive.count("telegram", "1") == 30
    assert archive.want("telegram", "1") and [r["chat_id"] for r in archive.wanted("telegram")] == ["1"]
    _run(tg, client, ticks=6, walker=w)
    assert archive.count("telegram", "1") == 230, "one ask is one bounded stretch past the day bound"
    assert archive.wanted("telegram") == []
    archive.want("telegram", "1")
    _run(tg, client, ticks=6, walker=w)
    assert archive.count("telegram", "1") == 430


def test_a_conversation_the_archive_holds_nothing_of_is_asked_by_the_name_he_used(tg, monkeypatch):
    _bounds(monkeypatch, initial_chats=1, deep_messages=100)
    dialogs = [_dialog(1, 1), _dialog(7, 300, name="Odile Varga Lund"), _dialog(8, 300, name="Marek Stone")]
    client = _Client(dialogs, {1: _chat(3), 7: _chat(40, 300), 8: _chat(40, 300)})
    w = _run(tg, client, ticks=4)
    assert archive.count("telegram", "7") == 0, "outside the first import"
    archive.want("telegram", name="odile varga")
    archive.want("telegram", name="nobody called this")
    _run(tg, client, ticks=6, walker=w)
    assert archive.count("telegram", "7") == 40 and archive.count("telegram", "8") == 0
    assert archive.wanted("telegram") == [], "an ask nobody answers is closed, never retried for ever"
    assert archive.backfill_stats("telegram")["started"] == 2


def test_a_search_that_names_a_conversation_and_finds_nothing_asks_for_it(tmp_path, monkeypatch):
    from widgets import store as wstore, supervisor
    from widgets.mensajeria import data
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    archive.reset()
    queued = []
    monkeypatch.setattr(supervisor, "enqueue_from_thread", lambda wid, act, pay: queued.append((wid, act, pay)))
    now = time.time()
    archive.record("telegram", "7", [{"messageId": "7:1", "from": "Odile", "body": "see you", "ts": now}],
                   direction="in", chat_name="Odile Varga Lund")
    archive.record("whatsapp", "34600112233@s.whatsapp.net", [{"messageId": "w1", "from": "Odile", "body": "ok", "ts": now}],
                   direction="in", chat_name="Odile Varga Lund")
    res = data.answer_action("search_archive", {"chat": "odile", "q": "invoice"})["result"]
    assert res["count"] == 0
    assert {(a["platform"], a["how"]) for a in res["asked_history"]} == {("telegram", "held"), ("whatsapp", "held")}
    assert [r["chat_id"] for r in archive.wanted("telegram")] == ["7"]
    assert queued == [("mensajeria", "load_more", {"platform": "whatsapp", "chatId": "34600112233@s.whatsapp.net", "limit": 100})]
    assert "repite esta búsqueda" in res["detail"]
    res = data.answer_action("search_archive", {"chat": "marek", "platform": "telegram"})["result"]
    assert res["asked_history"] == [{"platform": "telegram", "chat": "marek", "how": "by_name"}]
    hit = data.answer_action("search_archive", {"chat": "odile", "q": "see"})["result"]
    assert hit["count"] == 1 and "asked_history" not in hit, "a search that found it asks for nothing"
    assert "asked_history" in data.answer_action("search_archive", {"chat": "odile", "q": "see", "deeper": True})["result"]
    assert "asked_history" not in data.answer_action("search_archive", {"q": "nothing like this"})["result"], "no name, no ask"
    archive.reset()


# ── media ─────────────────────────────────────────────────────────────────────────────────────────────────────

def _file(folder, name, size, age_days):
    p = os.path.join(folder, name)
    with open(p, "wb") as fh:
        fh.write(b"0" * size)
    t = time.time() - age_days * 86400
    os.utime(p, (t, t))
    return p


def test_media_over_its_disk_budget_leaves_oldest_first_whatever_the_window(tmp_path):
    from widgets.mensajeria import media
    folder = str(tmp_path)
    for name, age in (("vid_a.mp4", 5), ("img_b.jpg", 3), ("aud_c.ogg", 1)):
        _file(folder, name, 1000, age)
    _file(folder, "state.json", 5000, 9)
    db = {"media_days": 0, "threads": {"k": {"msgs": [{"media": [{"name": "vid_a.mp4"}]}, {"media": [{"name": "aud_c.ogg"}]}]}}}
    assert media.sweep(db, folder)["files"] == 0, "no budget, «always»: nothing leaves"
    res = media.sweep(db, folder, budget=2500)
    assert res["files"] == 1 and sorted(os.listdir(folder)) == ["aud_c.ogg", "img_b.jpg", "state.json"]
    msgs = db["threads"]["k"]["msgs"]
    assert msgs[0].get("mediaGone") and "media" not in msgs[0] and msgs[1]["media"], "the message keeps its place"
    assert media.sweep(db, folder, budget=2500)["files"] == 0, "inside the budget nothing more leaves"


def test_the_budget_is_the_smaller_of_the_absolute_bound_and_a_share_of_the_disk(tmp_path, monkeypatch):
    import shutil
    monkeypatch.setattr(shutil, "disk_usage", lambda p: SimpleNamespace(total=3 * 1024 ** 3, used=0, free=0))
    _bounds(monkeypatch, media_budget_mb=4096, media_disk_ratio=0.15)
    assert history.media_budget_bytes(str(tmp_path)) == int(3 * 1024 ** 3 * 0.15), "a 3 GB volume: 15 % of it"
    monkeypatch.setattr(shutil, "disk_usage", lambda p: SimpleNamespace(total=500 * 1024 ** 3, used=0, free=0))
    history._POLICY.clear()
    assert history.media_budget_bytes(str(tmp_path)) == 4096 * 1024 * 1024, "a large disk: the absolute bound"
    _bounds(monkeypatch, media_budget_mb=0, media_disk_ratio=0)
    assert history.media_budget_bytes(str(tmp_path)) == 0


def test_a_file_over_the_cap_is_not_downloaded_by_itself_on_either_platform(tmp_path, monkeypatch):
    from connectors.telegram.service import inbound
    _bounds(monkeypatch, media_file_mb=20)
    monkeypatch.setattr(inbound, "_media_dir", lambda: str(tmp_path))
    pulled = []

    def _m(size):
        async def download_media(file):
            pulled.append(size)
            return file + ".mp4"
        return SimpleNamespace(id=1, photo=None, voice=None, video=object(), video_note=None, audio=None,
                               document=None, media=object(), file=SimpleNamespace(size=size), download_media=download_media)
    assert asyncio.run(inbound._capture_media(_m(136 * 1024 * 1024), 1)) == ("video", []), "its type travels, the bytes stay"
    assert asyncio.run(inbound._capture_media(_m(5 * 1024 * 1024), 1))[1] and pulled == [5 * 1024 * 1024]
    bridge = open("connectors/whatsapp/bridge/bridge.js", encoding="utf-8").read()
    assert bridge.count("if (overMediaCap(") == 4, "image, video, audio and document are all behind the cap"
    proc = open("connectors/whatsapp/bridge_proc.py", encoding="utf-8").read()
    assert 'env.setdefault("ZAELAR_MEDIA_MAX_BYTES", str(_history.media_cap_bytes()))' in proc


# ── the directory is not bounded by the window ────────────────────────────────────────────────────────────────

def test_a_message_from_nobodys_row_creates_no_contact(tmp_path, monkeypatch):
    """The directory is filled from the platform's book on every pass of a linked source, never from who writes."""
    from widgets import directory, store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from widgets.contactos import data
    msg = {"chatId": "34600112233@s.whatsapp.net", "senderId": "34600112233@s.whatsapp.net", "from": "Odile Varga"}
    assert directory.note_inbound("whatsapp", msg) is False, "it never creates a contact itself"
    assert data.load_db()["contacts"] == []
