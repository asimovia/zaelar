"""The chat wall hears a session of the manager as actions with ids (node 13.119, V2-941, INI-042 #49, the wall plan
§3 — commit 2/5).

  · his spoken line: `append` live at his first words (id = the intervention, writer `ear:<device>`), `update` live as
    he speaks — over the stream only, never stored (W-1) — `update` final with the words the inbox accepted; a line
    the ear discards before it is final is deleted; one that never had live words is appended final;
  · his typed line: id = the screen's own `cid` (`keyboard:<device>`), a malformed one replaced by the intervention;
    the `cid` travels from `POST /api/chat` to the manager's entry, which keeps a well-formed one and mints otherwise;
  · our line: `append` live when its voice starts, answering his (`re`), `update` final with what sounded; shown, it
    is final at once; one whose voice never started is on the wall whole, never said to have sounded.

Disarms seen red: a live update stored; the final words not written; a typed line by its intervention instead of its
`cid`; the `cid` dropped on its way to the entry; our line with no `re`.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from conversation.mouth import SayEnded, SayStarted
from nucleo.conversation_host import wall


@pytest.fixture
def ops(monkeypatch):
    from voice import observer
    out = []
    monkeypatch.setattr(observer, "emit", lambda kind, label, text="", role="", extra=None, piece=None:
                        kind == "wall" and out.append((extra["writer"], extra["op"], bool(extra.get("live")))))
    wall._reset_for_tests()
    yield out
    wall._reset_for_tests()


def _ear(label, iv, device="holder", **p):
    wall.listen("conv_ear", label, {"refs": {"iv": iv, "endpoint": device, "channel": "voice"}, **p})


def test_his_spoken_line_is_live_then_final(ops):
    _ear("opened", "iv_1")
    wall.heard("holder", 1, "w1")
    wall.heard("holder", 1, "w1 w2")
    wall.heard("holder", 2, "w3")
    wall.listen("conv_inbox", "accepted", {"kind": "user.utterance", "text": "w1 w2 w3",
                                           "refs": {"iv": "iv_1", "endpoint": "holder", "channel": "voice"}})
    assert [(w, o["op"], o.get("state"), o.get("text"), live) for w, o, live in ops] == [
        ("ear:holder", "append", "live", "w1", False),
        ("ear:holder", "update", None, "w1 w2", True),
        ("ear:holder", "update", None, "w1 w2 w3", True),
        ("ear:holder", "update", "final", "w1 w2 w3", False)]


def test_a_discarded_line_goes_and_one_with_no_live_words_is_appended_final(ops):
    _ear("opened", "iv_1")
    wall.heard("holder", 1, "w1")
    _ear("discarded", "iv_1")
    _ear("opened", "iv_2")
    wall.listen("conv_inbox", "accepted", {"kind": "user.utterance", "text": "w5",
                                           "refs": {"iv": "iv_2", "endpoint": "holder"}})
    assert [(o["op"], o["id"], o.get("state")) for _w, o, _l in ops] == [
        ("append", "iv_1", "live"), ("delete", "iv_1", None), ("append", "iv_2", "final")]


@pytest.mark.parametrize("cid, line", [("c_abc123", "c_abc123"), ("NOT a cid!", "iv_9")])
def test_his_typed_line_is_the_screens_own(ops, cid, line):
    wall.listen("conv_ear", "typed", {"cause": {"kind": "client", "ref": cid},
                                      "refs": {"iv": "iv_9", "endpoint": "desktop:d1", "channel": "text"}})
    wall.listen("conv_inbox", "accepted", {"kind": "user.text", "text": "w1",
                                           "refs": {"iv": "iv_9", "endpoint": "desktop:d1", "channel": "text"}})
    assert ops == [("keyboard:desktop:d1", {"op": "append", "id": line, "role": "you", "state": "final", "text": "w1"},
                    False)]


def test_the_cid_travels_from_the_screen_to_the_entry(monkeypatch):
    from nucleo.conversation_host import entry
    from voice import screens
    got = []

    async def fn(text, dev, cid=""):
        got.append((text, dev, cid))
    monkeypatch.setitem(screens._typed, "fn", fn)
    assert asyncio.run(screens.deliver_typed("w1", "desktop:d1", cid="c_abc"))
    assert got == [("w1", "desktop:d1", "c_abc")]
    handed = []
    monkeypatch.setattr(entry, "_hand", lambda deliver: handed.append(deliver))
    assert entry.typed("w1", "d1", checked=True, cid="c_abc")["cid"] == "c_abc"
    assert entry.typed("w1", "d1", checked=True, cid="x; drop")["cid"] != "x; drop"


def _order(text="w1 w2 w3", rid="r_iv_1"):
    return SimpleNamespace(say_id="s_1", text=text, channels=frozenset({"voice"}), endpoint="holder",
                           request_id=rid, notice_key=None)


def test_our_line_answers_his_and_ends_as_it_sounded(ops):
    from nucleo.conversation_host.mouth import WallMouth

    class Voice:
        def speak(self, order, ack):
            self.ack = ack
            return True
    v = Voice()
    m = WallMouth(SimpleNamespace(now_ms=lambda: 5), voice=v, ack_later=lambda s: None)
    asyncio.run(m.say(_order()))
    v.ack(SayStarted("s_1", 1))
    v.ack(SayEnded("s_1", "cut", 4, 2, "holder"))
    assert [(w, o) for w, o, _l in ops] == [
        ("mouth", {"op": "append", "id": "s_1", "role": "agent", "re": ["iv_1"], "text": "w1 w2 w3", "state": "live"}),
        ("mouth", {"op": "update", "id": "s_1", "state": "final", "heard": 4})]
    ops.clear()
    m2 = WallMouth(SimpleNamespace(now_ms=lambda: 5), voice=v, ack_later=lambda s: None)
    asyncio.run(m2.say(_order()))
    v.ack(SayEnded("s_1", "unknown", None, 2, "holder", "unknown"))      # its voice never started
    assert [o["state"] for _w, o, _l in ops] == ["final"] and "heard" not in ops[0][1]


def test_a_live_update_is_never_stored(monkeypatch):
    """W-1, through the real observer: the live update reaches the stream and never the record."""
    from bus import sse
    from voice import observer
    published = []
    monkeypatch.setattr(sse, "publish", lambda ev: published.append(dict(ev)))
    wall._reset_for_tests()
    _ear("opened", "iv_1")
    wall.heard("holder", 1, "w1")
    wall.heard("holder", 1, "w1 w2")
    stored = [e for e in observer.debug_events("wall") if e.get("op", {}).get("id") == "iv_1"]
    assert [e["op"]["op"] for e in stored] == ["append"]
    assert [e["op"]["op"] for e in published if e.get("kind") == "wall"] == ["append", "update"]
    wall._reset_for_tests()


def test_our_line_answers_every_line_of_its_batch_by_its_id_on_the_wall(ops):
    """The review's W2-1: a typed line's id on the wall is its `cid`, so our answer names it so — and every line of the
    batch it answers, a voice one too — or the wall counts a missing cause and cannot keep the order."""
    from nucleo.conversation_host.mouth import WallMouth
    wall.listen("conv_ear", "typed", {"cause": {"kind": "client", "ref": "c_abc"},
                                      "refs": {"iv": "iv_9", "endpoint": "desktop:d1", "channel": "text"}})
    wall.listen("conv_inbox", "accepted", {"kind": "user.text", "text": "w1",
                                           "refs": {"iv": "iv_9", "env": "e_9", "endpoint": "desktop:d1"}})
    wall.listen("conv_inbox", "accepted", {"kind": "user.utterance", "text": "w2",
                                           "refs": {"iv": "iv_10", "env": "e_10", "endpoint": "holder"}})
    wall.listen("conv_run", "started", {"batch_envs": ["e_9", "e_10"], "refs": {"run": "run_1"}})
    m = WallMouth(SimpleNamespace(now_ms=lambda: 5), ack_later=lambda s: None)
    order = SimpleNamespace(say_id="s_1", run_id="run_1", text="w9", channels=frozenset({"text"}), endpoint="d1",
                            request_id="r_iv_9", notice_key=None)
    asyncio.run(m.say(order))
    ours = [o for w, o, _l in ops if w == "mouth"]
    assert ours[0]["re"] == ["c_abc", "iv_10"]
