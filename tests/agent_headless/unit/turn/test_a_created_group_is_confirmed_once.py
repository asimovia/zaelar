"""One act gets one confirmation, from one door (INI-071 B9, 2026-11-16).

Heard in the local test of 2026-11-16: «create a WhatsApp group» was confirmed TWICE — the connector's note («Listo, ya
creé el grupo…», from `_note(«Grupo … creado … Díselo al operador»)`) and the task's own receipt («Hecho: el grupo…»,
the circuit's line when the order's echo settles its outbox row). The receipt is the act's end state (V2-919 M3), so the
connector's success note was a second door saying the same act.

The class: an order the card queued with a receipt is confirmed by the circuit when its echo lands — the connector
publishes the echo and says nothing of its own on success. Its FAILURE keeps its reason line (not this class).
Both connectors (WhatsApp, Telegram); the circuit's one line is exercised with the real owner applier and `tick`.
"""
from __future__ import annotations

import asyncio

import pytest

from memory import db as memdb, embeddings as mememb
from nucleo import circuit
from nucleo.circuit import spec
from nucleo.request import model as rq
from tests.outbound_lane import his_hand  # noqa: F401,E402 — these tests run the card's own acts, as his hand


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    memdb.reset_db()
    memdb.get_db()
    spec.reset()
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})
    from widgets.mensajeria import data as md         # the card first: its actions package imports through it
    from widgets.mensajeria.actions import groups
    monkeypatch.setattr(md._outbound, "resolve_target",
                        lambda p: {"ok": True, "to": "34600", "chatId": "34600@s.whatsapp.net",
                                   "name": str(p.get("contact")), "contactId": "c1"})
    monkeypatch.setattr(groups, "_by_id", lambda members, payload: list(members))
    # the connector's echo reaches the card through the owner's real applier (no bus, no thread)
    from connectors.messaging import ingest
    from widgets.mensajeria import owner

    def _apply(platform, chats, **_kw):
        o = owner._Owner.__new__(owner._Owner)
        o._chats_sub = o._failed_sub = object()
        o._drain = lambda sub: [{"platform": platform, "chats": list(chats)}]
        o._apply_chats()
    monkeypatch.setattr(ingest, "publish_chats", _apply)
    said: list = []
    from nucleo.events import task_event       # the connectors' door to his ear (`_note` → `told`)
    monkeypatch.setattr(task_event, "told", lambda text, **k: said.append(("connector", text)))
    from nucleo.workers import spoken_delivery
    from voice import proactive

    async def line(goal, fact, **k):
        said.append(("circuit", fact))
        return fact

    async def notify(*_a, **_k):
        return True
    monkeypatch.setattr(spoken_delivery, "line", line)
    monkeypatch.setattr(proactive, "notify", notify)
    yield said
    spec.reset()
    memdb.reset_db()
    mememb.reset()


class _Inbox:
    def __init__(self, orders):
        self.orders = list(orders)

    def drain(self):
        out, self.orders = self.orders, []
        return out


def _order(platform: str, name: str, said_words: str) -> tuple[dict, dict]:
    """His order through the card's door, with its end state opened on its row (as `data_ops` does)."""
    from widgets.mensajeria import data as md
    payload = {"platform": platform, "name": name, "members": ["Ana Prat"]}
    rq.begin(said_words)
    e = spec.open_for_action("mensajeria", "create_group", payload, text=said_words)
    got = md.apply_action("create_group", payload)
    assert got["ok"] and e is not None, got
    e["row"], e["turn"] = rq.opened("mensajeria", "create_group"), rq.current()
    return e, {"platform": platform, "ref": got["result"]["ref"], "name": name,
               "members": [{"to": "34600", "chatId": "34600@s.whatsapp.net"}], "text": "", "attachments": []}


def _whatsapp(monkeypatch, order):
    from connectors.whatsapp import client
    from connectors.whatsapp import service as wa
    from connectors.whatsapp.service import directory
    monkeypatch.setattr(wa, "_group_inbox", _Inbox([order]))

    async def _create(name, members):
        return {"id": "120363@g.us"}
    monkeypatch.setattr(client, "create_group", _create)
    return directory._drain_groups


def _telegram(monkeypatch, order):
    import telethon.utils
    from connectors.telegram import service as tg
    monkeypatch.setattr(tg, "_group_inbox", _Inbox([dict(order, members=[{"to": "@ana", "chatId": ""}])]))
    monkeypatch.setattr(telethon.utils, "get_peer_id", lambda ch: -100123)

    class _Client:
        async def __call__(self, req):
            return type("R", (), {"chats": [object()]})()

        async def get_input_entity(self, ref):
            return ref
    monkeypatch.setattr(tg, "_client", _Client())
    return tg._drain_groups


@pytest.mark.parametrize("platform,name,words,drain", [
    ("whatsapp", "Cena del viernes", "crea un grupo de WhatsApp con Ana que se llame Cena del viernes", _whatsapp),
    ("telegram", "Book club", "make a Telegram group with Ana called Book club", _telegram)])
def test_a_created_group_is_confirmed_once_by_its_receipt(world, monkeypatch, platform, name, words, drain):
    said = world

    async def run():
        e, order = _order(platform, name, words)
        await drain(monkeypatch, order)()
        circuit.tick(now=float(e["born"]) + circuit.CHECK_EVERY_S + 1)
        await asyncio.sleep(0.05)
    asyncio.run(run())
    assert [who for who, _t in said] == ["circuit"], f"one act, one confirmation, one door: {said}"
    assert said[0][1].startswith(circuit.SENT)


def test_a_failed_creation_still_says_its_reason(world, monkeypatch):
    said = world
    from connectors.whatsapp import client
    from connectors.whatsapp import service as wa
    from connectors.whatsapp.service import directory
    from connectors.messaging import ingest
    monkeypatch.setattr(ingest, "publish_send_failed", lambda order, reason: None)
    monkeypatch.setattr(wa, "_group_inbox", _Inbox([{"platform": "whatsapp", "ref": "r-1", "name": "Cena",
                                                     "members": [{"to": "34600"}]}]))

    async def _create(name, members):
        raise RuntimeError("not-authorized")
    monkeypatch.setattr(client, "create_group", _create)
    asyncio.run(directory._drain_groups())
    assert any(who == "connector" and "not-authorized" in t for who, t in said)
