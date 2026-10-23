"""WhatsApp and Telegram send files the way their apps do, and create groups (the connector half).

WhatsApp: each file through the bridge's /send-media, the text as the first file's caption — except a voice
note, which carries none, so the text then goes on its own. Telegram: several photos/videos as ONE album with the
text as caption, a voice note as a voice note. Both re-check that every file is inside the messaging widget's data
dir before it leaves, and both hand a new group back as a chat-list row.
"""
from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace

import pytest

from connectors.messaging import ingest


@pytest.fixture
def files(tmp_path, monkeypatch):
    from widgets import store as wstore
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    folder = wstore.data_dir("mensajeria")

    def make(name):
        p = os.path.join(folder, name)
        open(p, "wb").write(b"x")
        return os.path.realpath(p)
    outside = tmp_path / "elsewhere.jpg"
    outside.write_bytes(b"x")
    return SimpleNamespace(make=make, outside=str(outside))


class _Inbox:
    def __init__(self, orders):
        self._o = orders

    def drain(self):
        out, self._o = self._o, []
        return out


def test_whatsapp_sends_files_with_the_caption_where_the_app_puts_it(files, monkeypatch):
    from connectors.whatsapp import client, service
    calls = []

    async def send_media(chat, path, caption=""):
        calls.append(("media", os.path.basename(path), caption))
        return {"messageId": "M"}

    async def send_message(chat, text, reply_to=None):
        calls.append(("text", text))
        return {"messageId": "T"}
    monkeypatch.setattr(client, "send_media", send_media)
    monkeypatch.setattr(client, "send_message", send_message)
    photo, doc = files.make("up_a_foto.jpg"), files.make("up_b_factura.pdf")
    asyncio.run(service._send("1@s.whatsapp.net", "mira", [photo, doc, files.outside]))
    assert calls == [("media", "up_a_foto.jpg", "mira"), ("media", "up_b_factura.pdf", "")], \
        "the text is the first file's caption; a file outside the widget dir never leaves"
    calls.clear()
    asyncio.run(service._send("1@s.whatsapp.net", "escúchalo", [files.make("up_c_nota.ogg")]))
    assert calls == [("media", "up_c_nota.ogg", ""), ("text", "escúchalo")], "a voice note carries no caption"


def test_telegram_sends_an_album_and_a_voice_note_as_its_app_does(files, monkeypatch):
    from connectors.telegram import service
    calls = []

    class _C:
        async def send_file(self, peer, f, **kw):
            calls.append(("file", [os.path.basename(x) for x in (f if isinstance(f, list) else [f])],
                          kw.get("caption"), kw.get("voice_note", False)))
            return [SimpleNamespace(id=1)] if isinstance(f, list) else SimpleNamespace(id=2)

        async def send_message(self, peer, text, **kw):
            calls.append(("text", text))
            return SimpleNamespace(id=3)
    monkeypatch.setattr(service, "_client", _C())
    a, b, v = files.make("up_a_1.jpg"), files.make("up_b_2.mp4"), files.make("up_c_3.ogg")
    asyncio.run(service._send(42, "las fotos", [a, b, v]))
    assert calls == [("file", ["up_a_1.jpg", "up_b_2.mp4"], "las fotos", False),
                     ("file", ["up_c_3.ogg"], None, True)]


def test_a_new_group_comes_back_as_a_chat_and_gets_its_first_message(files, monkeypatch):
    from connectors.whatsapp import client, service
    rows, sent = [], []

    async def create_group(subject, participants):
        assert participants == ["34600111222@s.whatsapp.net", "34600333444@s.whatsapp.net"]
        return {"id": "123@g.us", "subject": subject}

    async def send_message(chat, text, reply_to=None):
        sent.append((chat, text))
        return {}
    monkeypatch.setattr(client, "create_group", create_group)
    monkeypatch.setattr(client, "send_message", send_message)
    monkeypatch.setattr(ingest, "publish_chats", lambda p, chats, **k: rows.append((p, chats)))
    monkeypatch.setattr(service, "_note", lambda text: None)
    monkeypatch.setattr(service, "_group_inbox", _Inbox([{"platform": "whatsapp", "name": "Viaje", "text": "hola",
        "members": [{"to": "+34600111222"}, {"to": "+34600333444"}]}]))
    asyncio.run(service._drain_groups())
    assert rows == [("whatsapp", [{"chatId": "123@g.us", "name": "Viaje", "kind": "group",
                                   "ts": rows[0][1][0]["ts"], "preview": ""}])]
    assert sent == [("123@g.us", "hola")]


def test_a_group_that_cannot_be_created_says_why(files, monkeypatch):
    from connectors.whatsapp import client, service
    failed = []

    async def create_group(subject, participants):
        raise client.BridgeError("POST /group → 500: bad participant")
    monkeypatch.setattr(client, "create_group", create_group)
    monkeypatch.setattr(ingest, "publish_send_failed", lambda order, reason: failed.append(reason))
    monkeypatch.setattr(service, "_note", lambda text: None)
    monkeypatch.setattr(service, "_group_inbox", _Inbox([{"name": "X", "members": [{"to": "+34600111222"}]}]))
    asyncio.run(service._drain_groups())
    assert failed and "bad participant" in failed[0]
