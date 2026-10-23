"""WhatsApp's past arrives ONCE, at pairing — the phone is never walked — and the linked device is named Zaelar.

Reported by the operator (2026-10-23): his phone showed «Finalizó la sincronización · Google Chrome (Hermes Agent)»
every few seconds. Two defects in one line: every on-demand history request is a notification on the phone, and
the bridge presented itself under the name of the project it was derived from. WhatsApp is now `at_link`
(connectors/messaging/history.py): what the phone sends when the device is paired is archived (bridge GET /sync),
and nothing asks it for more on its own. The device name is ours.
"""
from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import re

from connectors.messaging import archive, history, ingest

BRIDGE = pathlib.Path("connectors/whatsapp/bridge")


def test_whatsapp_is_never_walked():
    assert history.mode("whatsapp") == "at_link" and not history.walk_enabled("whatsapp")
    assert importlib.util.find_spec("connectors.whatsapp.backfill") is None, "no code left that pages the phone"


def test_the_linked_device_and_the_package_are_zaelar():
    src = (BRIDGE / "bridge.js").read_text(encoding="utf-8")
    assert "browser: [DEVICE_NAME, 'Chrome', '120.0']" in src
    assert "process.env.ZAELAR_DEVICE_NAME || 'Zaelar Agent'" in src
    assert not re.search(r"hermes", src, re.I), "the bridge names nobody else, in code or in comments"
    assert '"name": "zaelar-whatsapp-bridge"' in (BRIDGE / "package.json").read_text(encoding="utf-8")


def test_the_pairing_history_goes_to_the_archive_and_nowhere_else(tmp_path, monkeypatch):
    from widgets import store as wstore
    from connectors.whatsapp import client, service
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    archive.reset()
    published = []
    monkeypatch.setattr(ingest, "publish_history", lambda *a, **k: published.append(a))
    monkeypatch.setattr(ingest, "publish_msg", lambda *a, **k: published.append(a))

    async def get_sync():
        return [{"messageId": "S1", "chatId": "1@s.whatsapp.net", "senderName": "Ana", "body": "hace un año",
                 "timestamp": 1700000000, "direction": "in"},
                {"messageId": "S2", "chatId": "1@s.whatsapp.net", "body": "sin hora"}]
    monkeypatch.setattr(client, "get_sync", get_sync)
    asyncio.run(service._drain_sync())
    assert archive.count("whatsapp", "1@s.whatsapp.net") == 1, "a message with no time is not filed as «now»"
    assert published == []
    archive.reset()


def test_the_bridge_queues_the_pairing_sync_and_only_answers_on_demand_pages_as_scrollback():
    src = re.sub(r"//[^\n]*", "", (BRIDGE / "bridge.js").read_text(encoding="utf-8"))
    handler = src.split("sock.ev.on('messaging-history.set'", 1)[1].split("sock.ev.on(", 1)[0]
    assert "syncQueue.push(" in handler and "if (syncType !== 6) {" in handler
    assert "app.get('/sync'" in src
