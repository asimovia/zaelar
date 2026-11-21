"""The open message is the one in its card (C2 A2, pin 4).

A message has ONE draft, its owner's (the operator's decision P-2). The owner paints it into the box of the person it
goes to — through the card's own act for a message being written, read by its declared event type, on the owner's
lane — once it has a person and a text, and again when his words change it; when the draft ends (cancelled, idle,
replaced) the box is taken away, and a sent one's box goes once its receipt is read.
"""
from __future__ import annotations

import time

import pytest

from connectors import exit as door
from nucleo.send import card, draft, owner, receipt
from widgets import effects


@pytest.fixture
def box(monkeypatch):
    """The card's box, a double behind the one funnel: what each act left there, and on which lane."""
    from widgets import server_api
    write, drop = effects.acts_of("mensajeria", card.WRITE)[0], effects.acts_of("mensajeria", card.DISCARD)[0]
    seen: dict = {"box": {}, "lanes": []}

    async def dispatch(wid, act, payload):
        seen["lanes"].append(door.stamped(payload.get("_lane")))
        if act == write:
            k = f"to:{payload.get('contact_id')}"
            seen["box"][k] = payload["text"]
            return {"ok": True, "key": k}
        if act == drop:
            seen["box"].pop(payload["key"], None)
            return {"ok": True}
        return {"ok": False}
    monkeypatch.setattr(server_api, "_dispatch", dispatch)
    draft.reset()
    yield seen
    draft.reset()


def _open(text="w_goodnight", cid="c1"):
    d = draft.start("w_tell ana goodnight")
    d.target, d.text = {"name": "W_Ana", "contact_id": cid, "platform": "whatsapp"}, text
    owner._emit("opened", d)
    return d


def test_an_open_draft_is_painted_in_its_persons_box_and_follows_his_words(box):
    d = _open()
    assert box["box"] == {"to:c1": "w_goodnight"} and d.box_key == "to:c1" and box["lanes"] == [door.OWNER]
    d.text = "w_see you tomorrow"
    owner._emit("taken", d)
    assert box["box"] == {"to:c1": "w_see you tomorrow"}
    d.target = {"name": "W_Eva", "contact_id": "c2", "platform": "whatsapp"}
    owner._emit("taken", d)
    assert box["box"] == {"to:c2": "w_see you tomorrow"} and d.box_key == "to:c2", "the old person's box goes"


def test_a_draft_with_no_person_or_text_paints_nothing(box):
    d = draft.start("w_send a message")
    d.text = "w_hi"
    owner._emit("opened", d)
    assert box["box"] == {} and d.box_key == ""


def test_a_cancelled_an_idle_or_a_replaced_draft_leaves_its_box(box):
    d = _open()
    draft.close(d, draft.CANCELLED)
    assert box["box"] == {}
    d = _open(cid="c3")
    d.touched_at = time.time() - draft.IDLE_S - 1                 # nobody spoke about it: it ends where it is seen
    assert draft.current() is None and box["box"] == {}
    _open(cid="c4")
    draft.start("w_another message")
    assert box["box"] == {}, "a new send takes the place of the one it replaces, and its box"


def test_a_sent_draft_keeps_its_box_until_its_receipt_is_read(box, monkeypatch):
    import asyncio

    from nucleo.request import send_receipt
    d = _open()
    d.ref = "r1"
    draft.close(d, draft.SENT)
    assert box["box"] == {"to:c1": "w_goodnight"}
    monkeypatch.setattr(send_receipt, "receipt", lambda w, ref, _x: ("sent", ""))
    monkeypatch.setattr(receipt, "_say", lambda *a, **k: asyncio.sleep(0))
    async def followed():
        got = await receipt.follow(d, poll_s=0)
        await asyncio.gather(*card._tasks)                       # the view's own task, on this loop
        return got
    assert asyncio.run(followed()) == "sent" and box["box"] == {}


# ── C2 A3 · his hand on the box of the open draft (pins 5 and 6) ──────────────────────────────────────────────────────
def _hand(act_event: str, **payload):
    from widgets import owners
    act = effects.acts_of("mensajeria", act_event)[0] if act_event.startswith("messaging.draft") else act_event
    return owners.claim("mensajeria", act, door.by(door.HAND, payload))


def test_what_his_hand_types_in_the_box_is_the_drafts_text_asked_about_anew(box):
    d = _open()
    d.heard, d.confirm_line = True, "w_send it?"
    assert _hand(card.WRITE, key="to:c1", text="w_goodnight my dear") is None        # the card saves it as always
    assert d.text == "w_goodnight my dear" and d.heard is False and d.confirm_line == ""
    _hand(card.WRITE, key="c:other", text="w_another chat")                         # another box: not the owner's
    from widgets import owners
    owners.claim("mensajeria", effects.acts_of("mensajeria", card.WRITE)[0],
                 door.by(door.OWNER, {"key": "to:c1", "text": "w_the owner's own paint"}))
    assert d.text == "w_goodnight my dear", "only his hand: the owner's own paint never comes back to it"


def test_his_hands_send_is_his_go_ahead_once_and_the_owner_never_sends_it_again(box, monkeypatch):
    from nucleo.send import ask, deliver
    sent, asked = [], []
    monkeypatch.setattr(deliver, "run", lambda d: sent.append(d) or {"ok": True})
    monkeypatch.setattr(ask, "confirm", lambda *a, **k: asked.append(a))
    monkeypatch.setattr(receipt, "follow_soon", lambda d: None)
    d = _open()
    assert _hand("send_draft", ref="r9", box_key="to:c1", text="w_goodnight!") is None   # the card queues it ONCE
    assert d.state == draft.SENDING and d.ref == "r9" and d.text == "w_goodnight!" and draft.current() is None
    import asyncio
    took, _line = asyncio.run(owner.take("w_yes send it"))
    assert not took and sent == [] and asked == [], "no confirmation, and nothing the owner sends after it"


def test_his_hands_discard_drops_the_draft(box):
    d = _open()
    assert _hand(card.DISCARD, key="to:c1") is None and d.state == draft.CANCELLED and draft.current() is None
