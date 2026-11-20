"""The guards and the stop stand in front of the ear (node 13.91, V2-941, v3.1 §1.7, B10).

  · at the end of one of his turns the guards judge its words: a closed microphone, our own line heard back within the
    echo window, a turn the attention mode says was not said to us — each is a `Discard` handed to the ear BEFORE the
    end, with its text and reason, so it never closes as his words;
  · his stop — typed or spoken, heard by the engine's own detector outside the package — is a `user.control` handed
    ahead of the line it came with, from the producer of the door it came by;
  · his phrase the browser's own ear caught enters as VOICE, an entry of its own (`LocalPhrase`), and is answered;
  · a batch on the body link keeps a share of its room for the other events, however long the ear's lane is;
  · switched off, the conversation this process opened is retired when its voice session closes — no restart.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from conversation.ear import signals as S
from nucleo.conversation_host import controls, ear_in, entry, guards


@pytest.fixture
def ear(monkeypatch):
    from voice import attention, mic_input
    state = {"mic": False, "directed": True}
    monkeypatch.setattr(mic_input, "blocks_turn", lambda text: state["mic"])
    monkeypatch.setattr(attention, "evaluate", lambda text, now=None: SimpleNamespace(directed=state["directed"]))
    monkeypatch.setattr(attention, "note_ambient", lambda text, now=None: None)
    monkeypatch.setattr(attention, "note_directed", lambda now=None: None)
    monkeypatch.setattr(attention, "is_shut_up", lambda text: "w_stop" in text)
    guards._last.update(text="", at=0.0)
    ear_in._reset_for_tests()
    yield state
    ear_in._reset_for_tests()
    guards._last.update(text="", at=0.0)


def test_each_guard_names_why(ear):
    assert guards.judge("w1 w2") is None
    ear["mic"] = True
    assert guards.judge("w1 w2") == "mic_blocked"
    ear["mic"] = False
    guards.said("w5 w6 w7 w8", at=1000.0)
    assert guards.judge("w5 w6 w7 w8", now=1005.0) == "echo"
    assert guards.judge("w5 w6 w7 w8", now=1100.0) is None                    # past the echo window: his
    ear["directed"] = False
    assert guards.judge("w1 w2", now=1100.0) == "not_addressed"


def _turn(stream="holder", words=("w1", "w2"), seq0=1):
    return [{"t": "words", "stream": stream, "turn": 0, "rev": 1, "final": True,
             "words": [[w, 100, 200, 0.9] for w in words], "window": [0, 300], "boot": "b", "seq": seq0},
            {"t": "eot", "stream": stream, "kind": "end", "prob": .9, "t_ms": 300, "terminal": True, "boot": "b",
             "seq": seq0 + 1}]


def test_a_guarded_turn_reaches_the_ear_as_a_discard_before_its_end(ear):
    ear["mic"] = True
    got = []
    for f in _turn():
        ear_in.receive(f, got.append)
    kinds = [type(s).__name__ for s in got]
    assert kinds == ["WordSpan", "Discard", "EotHint"] and got[1].reason == "mic_blocked" and got[1].text == "w1 w2"
    ear["mic"] = False
    got.clear()
    for f in _turn(seq0=3):
        ear_in.receive(f, got.append)
    assert "Discard" not in [type(s).__name__ for s in got]


def test_his_spoken_stop_is_a_control_ahead_of_his_words(ear, monkeypatch):
    calls = []
    monkeypatch.setattr(controls, "control", lambda op="stop", dev="", by="chat": calls.append((op, dev, by)))
    got = []
    for f in _turn(words=("w_stop",)):
        ear_in.receive(f, lambda s: got.append(s) or calls.append(type(s).__name__))
    assert calls == ["WordSpan", ("stop", "holder", "ear"), "EotHint"]


class _Conv:
    account = "acct"

    def __init__(self):
        self.log = []

    def give(self, env):
        self.log.append(("give", env.kind.value, env.producer, env.channel.value, env.body.op.value))

    def hear(self, sig):
        self.log.append(("hear", type(sig).__name__))


@pytest.fixture
def handed(monkeypatch):
    conv = _Conv()
    monkeypatch.setattr(entry, "_hand", lambda fn: fn(conv))
    return conv


def test_his_typed_stop_is_given_before_the_line(ear, handed):
    entry.typed("w_stop w1", "text:s1", checked=True)
    assert handed.log == [("give", "user.control", "chat:text:s1", "text", "stop"), ("hear", "TypedSubmit")]
    handed.log.clear()
    entry.typed("w1", "text:s1", checked=True)
    assert handed.log == [("hear", "TypedSubmit")]


@pytest.mark.parametrize("by, producer, channel", [("ear", "ear:holder", "voice"), ("chat", "chat:holder", "text")])
def test_a_control_comes_from_the_producer_of_its_door(handed, by, producer, channel):
    controls.control("stop", "", by)
    assert handed.log == [("give", "user.control", producer, channel, "stop")]


def test_the_browsers_phrase_enters_as_voice_and_is_answered(store, handed):
    controls.local_phrase("w1 w2", "")
    assert handed.log == [("hear", "LocalPhrase")]
    from conversation.ports import Done
    from conversation.testing.scripted_model import reply
    from tests.conversation.unit.convkit import Harness
    h = Harness(store)
    h.model.default = lambda ids: [reply("w9"), Done()]
    h.hear(S.LocalPhrase("d1", "l1", "w1 w2", 10))
    h.settle(8000)
    assert [o.text for o in h.mouth.orders] == ["w9"]
    accepted = [p for k, lab, p in h.tel.events if k == "conv_inbox" and lab == "accepted"]
    assert accepted and accepted[0]["refs"]["channel"] == "voice"


def test_a_batch_keeps_room_for_the_other_events(monkeypatch):
    from voice.engine.pipeline import body_link
    link = body_link.BodyLink(base="http://127.0.0.1:1", token="t", max_batch=40)
    batches = []

    async def deliver(batch):
        batches.append(batch)
        return True
    monkeypatch.setattr(link, "_deliver", deliver)

    async def go():
        for i in range(200):
            link.send_ear({"t": "mark", "stream": "holder", "through": i})
        for i in range(5):
            link.send({"k": "session", "what": "w", "i": i})
        link.start()                                                           # all queued, then one wake
        link._kick()
        await asyncio.sleep(0.2)
        await link.aclose()
    asyncio.run(go())
    first = batches[0]
    assert sum(1 for ev in first if ev.get("k") == "session") == 5 and len(first) <= 40


def test_switched_off_the_conversation_is_retired_without_a_restart(monkeypatch):
    from nucleo.conversation_host import sessions, switch
    closed = []
    monkeypatch.setattr(sessions, "close_all", lambda: closed.append(1))
    monkeypatch.setitem(entry._opener, "rt", object())
    monkeypatch.setattr(switch, "decide", lambda session=None: switch.Decision(True, "account"))
    assert controls.retire_if_off() is False and closed == []                     # still on: kept
    monkeypatch.setattr(switch, "decide", lambda session=None: switch.Decision(False, "default"))
    assert controls.retire_if_off() is True and closed == [1] and entry._opener["rt"] is None

