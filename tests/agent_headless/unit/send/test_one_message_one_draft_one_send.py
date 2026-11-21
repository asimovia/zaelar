"""One message, one draft, one send — the class as a property (C2, pin 9).

Through a whole sequence with doubles — opened, changed by his voice, changed by his hand in the box, confirmed, sent
with the card's own Send — at every moment the open draft's box holds the owner's text, and at the end exactly one
order has left. Any of the A2/A3 disarms (no paint, no hand lane, a Send the owner does not adopt) breaks it.
"""
from __future__ import annotations

import asyncio

import pytest

from connectors import exit as door
from nucleo.send import ask, card, deliver, draft, owner, receipt
from widgets import effects, owners


@pytest.fixture
def world(monkeypatch):
    from widgets import server_api
    write, drop = effects.acts_of("mensajeria", card.WRITE)[0], effects.acts_of("mensajeria", card.DISCARD)[0]
    w: dict = {"box": {}, "orders": []}

    async def dispatch(wid, act, payload):
        if act == write:
            w["box"][f"c:{payload.get('contact_id')}"] = payload["text"]
            return {"ok": True, "key": f"c:{payload.get('contact_id')}"}
        if act == drop:
            w["box"].pop(payload["key"], None)
            return {"ok": True}
        return {"ok": False}
    monkeypatch.setattr(server_api, "_dispatch", dispatch)
    monkeypatch.setattr(deliver, "run", lambda d: w["orders"].append(("owner", d.text)) or {"ok": True, "ref": "x"})
    monkeypatch.setattr(ask, "confirm", lambda *a, **k: asyncio.sleep(0, result="w_send it?"))
    monkeypatch.setattr(receipt, "follow_soon", lambda d: None)
    draft.reset()
    yield w
    draft.reset()


def _hand(act: str, payload: dict):
    """His hand on the card: the owner's claim first, then the card's act as it would run."""
    p = door.by(door.HAND, payload)
    if owners.claim("mensajeria", act, p) is None and act == "send_draft":
        _world["w"]["orders"].append(("card", payload["text"]))
    owners.settle("mensajeria", act, p, {"ok": True})


_world: dict = {}


def _box_is_the_drafts(w, d) -> bool:
    return d.state != draft.OPEN or w["box"].get(d.box_key) == d.text


def test_through_voice_hand_and_send_the_box_is_the_drafts_and_one_order_leaves(world):
    _world["w"] = world
    d = draft.start("w_tell ana goodnight")
    d.target, d.text = {"name": "W_Ana", "contact_id": "a1", "platform": "w_chat"}, "w_goodnight"
    owner._emit("opened", d)
    assert _box_is_the_drafts(world, d)
    d.text = "w_good night, sleep well"                                 # his voice changes it
    owner._emit("taken", d)
    assert _box_is_the_drafts(world, d)
    write = effects.acts_of("mensajeria", card.WRITE)[0]
    _hand(write, {"key": d.box_key, "text": "w_good night, sleep well!"})   # his hand changes it
    world["box"][d.box_key] = "w_good night, sleep well!"               # the card saves what he typed
    assert d.text == "w_good night, sleep well!" and _box_is_the_drafts(world, d)
    d.confirm_line, d.heard = "w_send it?", True
    owner._emit("asked", d)
    assert _box_is_the_drafts(world, d)
    _hand("send_draft", {"ref": "r1", "box_key": d.box_key, "text": d.text})   # his Send
    took, _line = asyncio.run(owner.take("w_yes"))                      # and a yes after it
    assert world["orders"] == [("card", "w_good night, sleep well!")] and not took
    assert draft.current() is None, "his Send took the draft: no yes can send it a second time"


def test_the_mail_screens_send_over_the_open_draft_is_his_go_ahead_once(world):
    """The same property by the mail draft screen: its Send is `compose` with `send` and its own `ref` on the draft's
    box — the owner adopts it, so no yes of his can send it again."""
    _world["w"] = world
    d = draft.start("w_mail ana the report")
    d.target, d.text = {"name": "W_Ana", "contact_id": "a1", "platform": "email"}, "w_the report"
    owner._emit("opened", d)
    p = door.by(door.HAND, {"key": d.box_key, "text": "w_the report, attached", "send": True, "ref": "r2"})
    if owners.claim("mensajeria", "compose", p) is None:
        world["orders"].append(("card", "w_the report, attached"))
    owners.settle("mensajeria", "compose", p, {"ok": True})
    took, _line = asyncio.run(owner.take("w_yes send it"))
    assert world["orders"] == [("card", "w_the report, attached")] and not took and draft.current() is None
