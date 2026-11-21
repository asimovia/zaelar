"""No voice room outlives a freeze, and a room the token door mints is owed its agent (V2-910).

Measured on a hosted Machine: the host was suspended with a voice room open (the page had gone quiet; the engine idled
out with the room live). On the resume the LiveKit worker re-registered, reported the job it still held, had its
connection dropped, and reconnected at once — several times a second, never registered long enough to be given a
room. Two rooms asked for after the resume were never joined; the job went on «speaking» into the dead room.

The mechanism (`nucleo/pulse/voice_rooms.py`):
  * the sleep closes the live room BEFORE the host freezes (`suspend._go_to_sleep` → `before_sleep`);
  * a room still live on a resume is closed, and a voice process that will not close it is recycled;
  * rooms the token door minted and no agent joined in `room_owed_s` get the voice recycled — unless a person is in
    the live room (a conversation is never the price of the cure);
  * the voice process never speaks into a room with nobody in it.
"""
from __future__ import annotations

import asyncio
import time
import types

import pytest

from nucleo import idle_stop, suspend
from nucleo.pulse import voice_rooms as VR

POL = {"room_close_wait_s": 0.3, "room_owed_s": 30.0, "rooms_unserved_cure": 2.0, "room_cure_cooldown_s": 120.0}


class FakeVoice:
    """The voice process as `voice_rooms` reads it: its status poll, its control client."""

    def __init__(self, *, live=True, room="zaelar-old", closes=True, listener=False):
        self.status = {"live": live, "room": room, "listener": listener}
        self.closes = closes
        self.posts = []
        self.client = types.SimpleNamespace(post=self._post)

    async def _post(self, path, payload=None, timeout_s=3.0):
        self.posts.append((path, payload))
        if path == "/voice/close" and self.closes:
            self.status = {**self.status, "live": False}
        return {"ok": True}

    async def _read_status(self):
        return None

    def live(self):
        return bool(self.status.get("live"))


@pytest.fixture
def rooms(monkeypatch):
    VR._reset_for_tests()
    monkeypatch.setattr(VR, "policy", lambda: dict(POL))
    events = []
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda kind, label, text="", **kw: events.append(label))
    recycled = []

    async def recycle(app):
        recycled.append(app)
        return True

    def use(voice):
        monkeypatch.setattr(VR, "_voice", lambda: voice)
        return voice
    yield types.SimpleNamespace(events=events, recycled=recycled, recycle=recycle, use=use)
    VR._reset_for_tests()


# ── 1 · the sleep closes the live room before the host freezes ───────────────────────────────────────────────────

def test_the_sleep_closes_the_live_room_before_the_host_is_suspended(monkeypatch, rooms):
    voice = rooms.use(FakeVoice())
    record = []
    suspend._reset_for_tests()
    monkeypatch.setenv("ZAELAR_IDLE_STOP_MIN", "1")
    monkeypatch.setenv("ZAELAR_SLEEP_URL", "http://deployment.invalid/sleep")
    monkeypatch.setattr(idle_stop, "_readings", lambda now: (None, False, None))
    monkeypatch.setattr(idle_stop, "_last_presence", lambda: None)
    monkeypatch.setattr(idle_stop, "_STARTED_MS", round((time.time() - 3600) * 1000))
    monkeypatch.setattr(suspend, "SLEEP_FLUSH_S", 0.01)

    async def _flush():
        return True

    async def _post(endpoint, token):
        record.append(("sleep", voice.live()))
        return 202
    monkeypatch.setattr(suspend, "_flush_wake", _flush)
    monkeypatch.setattr(suspend, "_post_sleep", _post)
    suspend.request_exit(lambda: None)

    async def go():
        assert idle_stop.maybe_stop() is True
        await asyncio.sleep(0.2)
    try:
        asyncio.run(go())
    finally:
        suspend._reset_for_tests()
    assert voice.posts and voice.posts[0][0] == "/voice/close", "the live room must be closed before the sleep"
    assert record == [("sleep", False)], "the host is asked to sleep only once the room is closed"
    assert "voice_room_closed" in rooms.events


# ── 2 · a room that crossed the freeze anyway is closed on the resume, or the voice is recycled ─────────────────

def test_a_resume_closes_a_room_that_crossed_the_freeze(rooms):
    voice = rooms.use(FakeVoice())
    suspend._reset_for_tests()
    try:
        assert suspend.note_tick(1000.0, 10.0) is False
        assert suspend.note_tick(1000.0 + 9000, 11.0) is True        # wall clock jumped: a frozen guest
    finally:
        suspend._reset_for_tests()

    async def go():
        VR.tick(object(), rooms.recycle)
        await VR._state["busy"]
    asyncio.run(go())
    assert ("/voice/close", {"reason": "resumed"}) in voice.posts
    assert "voice_room_survived_freeze" in rooms.events
    assert rooms.recycled == [], "a room that closes needs no recycle"


def test_a_room_that_will_not_close_after_a_resume_gets_the_voice_recycled(rooms):
    rooms.use(FakeVoice(closes=False))
    VR.note_resumed(1000.0)

    async def go():
        VR.tick(object(), rooms.recycle, 1000.0)
        await VR._state["busy"]
    asyncio.run(go())
    assert len(rooms.recycled) == 1, "a job that will not leave its dead room is ended with its process"
    assert "voice_room_cure" in rooms.events


def test_a_resume_with_no_room_open_touches_nothing(rooms):
    voice = rooms.use(FakeVoice(live=False))
    VR.note_resumed(1000.0)

    async def go():
        VR.tick(object(), rooms.recycle, 1000.0)
        await VR._state["busy"]
    asyncio.run(go())
    assert voice.posts == [] and rooms.recycled == []


# ── 3 · rooms asked for and never joined ─────────────────────────────────────────────────────────────────────────

def test_rooms_no_agent_joined_get_the_voice_recycled(rooms):
    rooms.use(FakeVoice(live=True, listener=False))
    VR.note_minted("zaelar-a", 1000.0)
    VR.note_minted("zaelar-b", 1026.0)
    assert asyncio.run(VR.check_owed(object(), rooms.recycle, 1040.0)) == "ok", "one room past due is not a pattern"
    assert asyncio.run(VR.check_owed(object(), rooms.recycle, 1057.0)) == "recycled"
    assert len(rooms.recycled) == 1 and "voice_rooms_unserved" in rooms.events
    VR.note_minted("zaelar-c", 1060.0)
    VR.note_minted("zaelar-d", 1061.0)
    assert asyncio.run(VR.check_owed(object(), rooms.recycle, 1100.0)) == "wait", "at most one cure per cooldown"


def test_a_room_the_agent_joined_is_owed_nothing(rooms):
    rooms.use(FakeVoice(live=False))
    VR.note_minted("zaelar-a", 1000.0)
    VR.note_minted("zaelar-b", 1001.0)
    VR.note_served("zaelar-b")
    assert VR.unserved(2000.0) == [], "the agent arriving forgives the rooms asked before it"
    assert asyncio.run(VR.check_owed(object(), rooms.recycle, 2000.0)) == "ok"


def test_a_person_in_the_live_room_is_never_cut_by_the_cure(rooms):
    rooms.use(FakeVoice(live=True, listener=True))
    VR.note_minted("zaelar-a", 1000.0)
    VR.note_minted("zaelar-b", 1001.0)
    assert asyncio.run(VR.check_owed(object(), rooms.recycle, 1100.0)) == "held"
    assert rooms.recycled == []


def test_the_token_door_and_the_voice_session_feed_the_count():
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    door = (root / "server" / "livekit_api.py").read_text(encoding="utf-8")
    assert door.count("_owed(") >= 3, "both the direct and the mediated token note the room they mint"
    assert "voice_rooms.note_served(room)" in (root / "voice" / "remote_session.py").read_text(encoding="utf-8")
    # (the embedded session that also noted it went with the old turn, INI-078 L1: the voice's own process is the one)
    loop = (root / "nucleo" / "pulse" / "loop.py").read_text(encoding="utf-8")
    assert "self._supervise_voice_rooms(now)" in loop


# ── 4 · never speak into a room nobody is in ─────────────────────────────────────────────────────────────────────

def test_the_voice_never_speaks_into_an_empty_room():
    from livekit import rtc
    from voice.engine.pipeline.child import has_listener

    def room(connected, *kinds):
        parts = {f"p{i}": types.SimpleNamespace(kind=k, identity=("agent-x" if k == rtc.ParticipantKind.PARTICIPANT_KIND_AGENT
                                                                    else "operator-1")) for i, k in enumerate(kinds)}
        return types.SimpleNamespace(room=types.SimpleNamespace(isconnected=lambda: connected, remote_participants=parts))
    std, agent = rtc.ParticipantKind.PARTICIPANT_KIND_STANDARD, rtc.ParticipantKind.PARTICIPANT_KIND_AGENT
    assert has_listener(room(True, std)) is True
    assert has_listener(room(True)) is False, "nobody in the room"
    assert has_listener(room(True, agent)) is False, "only another agent in the room"
    assert has_listener(room(False, std)) is False, "a room that is not connected carries nothing"
    assert has_listener(None) is True, "a context it cannot read is never refused"
