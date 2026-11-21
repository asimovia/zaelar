"""The audit of B7f–B9 holds on the voice paths (node 13.94, V2-941, v3.1 B8d — TH-2, TH-3 and its minors).

  · a conversation that never opens leaves no line unheard at ANY door: a line of the data channel goes the old way
    (its session falls back, said), and his voice makes the session fall back and tells him once that it lost him;
  · closing the microphone in a session of the manager never commits LiveKit's turn (it clears it), and a commit
    that still happens anywhere is counted where it happens (`commit_user_turn`, a counter that must stay zero);
  · an owed line whose mouth raises goes back to its ledger, never kept and never out of the pump;
  · an ephemeral notice in a session of the manager is claimed for its voice — no second mouth;
  · what the voice process is told of the settings is computed on the body's loop, the one that keeps what was sent.
"""
from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace

import pytest

from nucleo.conversation_host import entry, switch


def _live(name: str):
    """The module the code reads now (another test may have purged and imported it again)."""
    import importlib
    return importlib.import_module(name)


@pytest.fixture
def never_opens(monkeypatch):
    from voice import observer
    alerts = []
    monkeypatch.setattr(observer, "emit", lambda kind, label, **kw: alerts.append(label) if kind == "alert" else None)
    monkeypatch.setattr(entry, "OPEN_BACKOFF_S", 0.0)

    def runtime():
        raise TimeoutError("w_lease")
    monkeypatch.setattr(entry, "runtime", runtime)
    entry.reset()
    yield alerts
    entry.reset()


def test_a_data_channel_line_is_answered_no_other_way_when_the_conversation_never_opens(never_opens, monkeypatch):
    from voice.engine.pipeline import agent_events
    routed = []
    monkeypatch.setattr(agent_events, "_route_typed", lambda txt, **kw: routed.append(txt))
    session = SimpleNamespace(_conversation_switch=switch.Decision(True, "voice"))
    agent_events.receive_typed("w1", _emit=lambda *a, **k: None, session=session)
    for th in [th for th in threading.enumerate() if th.name == "conversation-open"]:
        th.join(5)
    assert routed == []                                                        # no old path: said, never answered
    assert "a typed line was not answered: the conversation could not open" in never_opens


def test_his_voice_lost_tells_him_once_and_the_session_answers_nothing_more(never_opens, monkeypatch):
    from conversation.ear import signals as S
    words, notices, remote_session = (_live(m) for m in ("nucleo.conversation_host.words", "nucleo.pulse.notices",
                                                          "voice.remote_session"))
    told = []

    async def notify(title, text, key="", **kw):
        told.append(text)
    monkeypatch.setattr(notices, "notify", notify)
    monkeypatch.setattr(words.PackWords, "line", lambda self, key: "w_lost" if key == "mute_lines" else "")
    session = SimpleNamespace(_conversation_switch=switch.Decision(True, "voice"))
    monkeypatch.setitem(remote_session._M, "session", session)
    for t in (10, 20, 30):
        entry.voice(S.Watermark("holder", t))
    for th in [th for th in threading.enumerate() if th.name == "conversation-open"]:
        th.join(5)                                                             # every attempt, however many started
    assert told == ["w_lost"] and not switch.on(session)
    assert "the conversation cannot answer now" in never_opens               # the reason, on his screen


class _Session:
    def __init__(self, manager):
        self._zaelar_manager_ear = manager
        self.input = SimpleNamespace(audio_enabled=True, set_audio_enabled=lambda v: setattr(self.input,
                                                                                               "audio_enabled", v))
        self.log = []

    def clear_user_turn(self):
        self.log.append("clear")

    def commit_user_turn(self, **kw):
        self.log.append("commit")
        f = asyncio.get_event_loop().create_future()
        f.set_result("")
        return f


def test_closing_the_mic_in_a_session_of_the_manager_never_commits():
    from voice.engine.pipeline import agent_events

    async def go(manager):
        s = _Session(manager)
        agent_events.set_ear(s, False)
        return s.log
    assert asyncio.run(go(True)) == ["clear"]
    assert asyncio.run(go(False)) == ["commit"]                                   # the old path, as before


def test_a_commit_that_still_happens_is_counted_where_it_happens(monkeypatch):
    from voice import remote_session
    from voice.engine.pipeline import body_link, child_session, ear_tap
    sent, counted = [], []
    monkeypatch.setattr(body_link, "get", lambda: SimpleNamespace(send=sent.append))
    session = SimpleNamespace(clear_user_turn=lambda: None, commit_user_turn=lambda **kw: "w_done",
                              on=lambda *a, **k: None)
    tap = ear_tap.Tap("holder", lambda f: None)
    child_session._wire_ear(session, tap, {"min_duration": 0.5})
    assert session.commit_user_turn() == "w_done" and sent == [{"k": "proof", "counter": "commit_user_turn"}]
    monkeypatch.setattr(entry, "count", counted.append)
    remote_session.handle(sent[0])
    assert counted == ["commit_user_turn"]
    child_session.LIVE["tap"] = None


def test_an_owed_line_whose_mouth_raises_goes_back_to_its_ledger(store):
    from tests.conversation.unit.convkit import Harness
    h = Harness(store)

    async def broken(**kw):
        raise RuntimeError("w_mouth")
    h.conv.speaker.say = broken
    h.owed.add("k1", "w5")
    h.settle(2000)                                                                # nothing raised out of the pump
    assert h.owed.rows["k1"]["state"] == "owed"


def test_an_ephemeral_notice_is_claimed_for_the_managers_voice(monkeypatch):
    from memory.api import notices as store
    owed, notices, proactive = (_live(m) for m in ("nucleo.conversation_host.owed", "nucleo.pulse.notices",
                                                    "voice.proactive"))

    async def paint(title, text, *, key="", speak=True, **kw):
        return True
    monkeypatch.setattr(proactive, "notify", paint)
    monkeypatch.setattr(notices, "_targets", lambda: ["d1"])
    monkeypatch.setattr(notices, "someone_looking", lambda now=None: False)
    import uuid
    key = f"k_eph_{uuid.uuid4().hex[:8]}"
    owed.set_voice_live(True)
    try:
        got = asyncio.run(notices.notify("t", "w_still", key=key, ephemeral=True))
        assert got["state"] == "claimed" and store.by_key(key)["state"] == "claimed"   # the one mouth, never two
    finally:
        owed.set_voice_live(False)
        owed._handed.clear()


def test_the_settings_for_the_voice_are_computed_on_the_bodys_loop(monkeypatch):
    from nucleo.conversation_host import voice_mouth
    from voice import observer, remote_session as rs
    monkeypatch.setattr(observer, "emit", lambda *a, **k: None)
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=loop.run_forever, daemon=True)
    t.start()
    where, done = [], threading.Event()

    class _Client:
        _loop = loop

        def env_diff(self):
            where.append(threading.current_thread() is t)
            return {}

        async def say_stream(self, payload):
            yield {"done": True, "interrupted": False, "spoken_chars": 1}
            done.set()
    monkeypatch.setitem(rs._M, "session", SimpleNamespace(_conversation_switch=switch.Decision(True, "voice")))
    monkeypatch.setitem(rs._M, "client", _Client())
    voice_mouth.speak(SimpleNamespace(say_id="s1", text="w1", endpoint="holder"), lambda sig: None)
    done.wait(3)
    loop.call_soon_threadsafe(loop.stop)
    t.join(2)
    assert where == [True]
