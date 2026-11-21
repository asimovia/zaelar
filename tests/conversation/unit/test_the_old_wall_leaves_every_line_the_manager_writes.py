"""The old wall's events of a session of the manager are marked `conv`, so the old wall's writer leaves the lines the
manager writes on the wall itself (node 13.124, V2-941, INI-042 #49 — the wall plan's commit 4/5, the review's F3-1 and
F3-2). Never two writers for one line:

  · his spoken line as the record writes it (`transcript` 🗣, `wall_lines`) and the replayed provider interim/final;
  · his typed line's announcement (`transcript` text-injected chat) when a text door goes by the manager;
  · our line owed and written (`brain` reply, `transcript` zaelar) and a notice's 🔔 card the manager's mouth paints;
  · a typed line's announcement carries the screen's own id for it (`cid`) whatever the switch says, so the screen
    that typed it reads it as ITS line — one line, with the switch off too.
An old-path session leaves its events unmarked: the old wall's writer is theirs.

Disarms seen red: each mark removed in turn; the `cid` left off the announcement.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest


@pytest.fixture
def events(monkeypatch):
    from voice import observer
    out = []
    monkeypatch.setattr(observer, "emit", lambda kind, label, text="", role="", extra=None, piece=None:
                        out.append((kind, label, dict(extra or {}))))
    return out


def _marked(events, kind):
    return [x.get("conv") is True for k, _l, x in events if k == kind]


def test_his_line_as_the_record_writes_it_is_marked(events):
    from nucleo.conversation_host import wall_lines
    wall_lines.listen("conv_inbox", "accepted", {"kind": wall_lines.UTTERANCE, "text": "w1",
                                                 "refs": {"iv": "iv_1", "channel": "voice"}})
    assert _marked(events, "transcript") == [True]


@pytest.mark.parametrize("final, kind", [(False, "interim"), (True, "transcript")])
@pytest.mark.parametrize("manager", [True, False])
def test_the_replayed_provider_words_are_marked_in_a_session_of_the_manager(events, final, kind, manager):
    from voice import remote_session
    remote = SimpleNamespace(_conversation_switch=SimpleNamespace(on=manager))
    monkey = remote_session._M.get("session")
    remote_session._M["session"] = remote
    try:
        remote_session.handle({"k": "transcript", "final": final, "text": "w1"})
    finally:
        remote_session._M["session"] = monkey
    if final:                                        # the manager is the only path (INI-078 F2): any session's
        assert _marked(events, kind) == []           # final words are its ear's, written once (`wall_lines`)
    else:
        assert _marked(events, kind) == [True]


def test_our_lines_and_a_notice_card_of_the_manager_are_marked(events):
    from conversation.mouth import SayStarted
    from nucleo.conversation_host.mouth import WallMouth
    from voice import proactive

    class Voice:
        def speak(self, order, ack):
            self.ack = ack
            return True
    v = Voice()
    order = SimpleNamespace(say_id="s_1", text="w1", channels=frozenset({"voice"}), endpoint="holder",
                            request_id="r_iv_1", notice_key=None)
    asyncio.run(WallMouth(SimpleNamespace(now_ms=lambda: 5), voice=v, ack_later=lambda s: None).say(order))
    v.ack(SayStarted("s_1", 1))
    from conversation.mouth import SayEnded
    v.ack(SayEnded("s_1", "done", None, 2, "holder"))
    shown = SimpleNamespace(say_id="s_2", text="w2", channels=frozenset({"text"}), endpoint="holder",
                            request_id="r_iv_2", notice_key=None)
    asyncio.run(WallMouth(SimpleNamespace(now_ms=lambda: 5), ack_later=lambda s: None).say(shown))
    proactive.paint("w3", "w4", key="k1")
    assert _marked(events, "brain") == [True] and _marked(events, "transcript") == [True, True]
    assert _marked(events, "notify") == [True]


def test_a_notice_the_old_mouth_says_is_not_marked(events):
    from voice import proactive
    proactive._paint("notify", "w3", "w4", key="k1", task_id="")
    assert _marked(events, "notify") == [False]


@pytest.mark.parametrize("manager", [True, False])
def test_a_typed_line_announced_carries_its_cid_and_the_managers_mark(monkeypatch, manager):
    """F3-2: the `cid` rides the announcement with the switch off too — the old wall acknowledges the screen's line by
    it instead of comparing texts — and F3-1: with the text door on the manager, the announcement is marked."""
    from nucleo.conversation_host import entry, switch
    from voice.engine.pipeline import agent_events
    monkeypatch.setattr(switch, "on", lambda session=None: manager)
    monkeypatch.setattr(entry, "typed", lambda *a, **k: None)
    monkeypatch.setattr(agent_events, "_route_typed", lambda *a, **k: None)
    got = []
    agent_events.receive_typed("w1", _emit=lambda kind, label, **kw: got.append((kind, label, kw.get("extra") or {})),
                               session=SimpleNamespace(), dev="desktop:d1", cid="c_abc")
    said = [x for k, label, x in got if k == "transcript" and label == "text-injected chat"]
    assert said == [{"dev": "desktop:d1", "cid": "c_abc", **({"conv": True} if manager else {})}]
