"""A voice session of the manager hears for it, and LiveKit opens no turn of its own (node 13.86, v3.1 §1.7, B8b).

Before it builds a session the voice process asks the body's switch (the room's own `conv` flag first); it builds the
manager's session only when the answer is yes AND the streaming provider gives turns, and what it built rides
«session started», where it is the session's decision on the body. In that session:
  · every raw provider message reaches the ear first (`ear_tap`), the plugin's own handler runs untouched after it,
    each stream with its own clock, and after an end of turn the session's own turn is cleared — never committed;
  · the ear's own edges of his voice (E1): a rise at the first speaking frame, a fall after 200 ms of quiet stamped at
    the last speaking frame, `echo_safe` false while our voice sounds;
  · turn detection is manual and there is no early reply; the body's kickoff greets nothing; an `llm_node` LiveKit
    opens anyway is counted (`livekit_turns`), said, and answered with an empty turn;
  · the owed lines are claimed for the voice while it lives, and the close gives it back.
A body stalled for five seconds of speech loses nothing and declares no gap.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from voice.engine.pipeline import body_link, ear_feed, ear_tap


def _msg(event, turn=0, words=(), end=1.0, transcript=None, prob=None):
    ws = [{"word": w, "start": end - .3, "end": end - .1, "confidence": .9} for w in words]
    return {"type": "TurnInfo", "event": event, "turn_index": turn, "audio_window_start": 0.0, "audio_window_end": end,
            "words": ws, "transcript": transcript if transcript is not None else " ".join(words),
            "end_of_turn_confidence": prob}


class _Stream:
    def __init__(self):
        self.seen = []

    def _process_stream_event(self, data):
        self.seen.append(data)


class _STT:
    _zaelar_stream_class = _Stream                    # the stream it opens has a message handler: tappable

    def __init__(self):
        self.streams = []

    def stream(self, *a, **kw):
        s = _Stream()
        self.streams.append(s)
        return s


def test_the_ear_hears_each_message_first_and_the_plugin_still_handles_it():
    facts, ends = [], []
    tap = ear_tap.Tap("holder", facts.append)
    tap.on_end = lambda: ends.append(len(facts))
    stt = ear_tap.install_stt(_STT(), tap)
    s = stt.stream()
    for m in (_msg(ear_feed.START, words=["w1"]), _msg(ear_feed.UPDATE, words=["w1", "w2"], end=1.4),
              _msg(ear_feed.END, words=["w1", "w2"], end=1.6, transcript="w1 w2.", prob=.8), {"type": "Metadata"}):
        s._process_stream_event(m)
    assert len(s.seen) == 4                                                   # the plugin's own path, untouched
    eot = [f for f in facts if f["t"] == "eot"]
    assert eot == [{**eot[0], "kind": "end", "prob": .8, "terminal": True}] and eot[0]["stream"] == "holder"
    assert [f["rev"] for f in facts if f["t"] == "words"] == [1, 2, 3]
    assert ends == [len(facts)]                                               # cleared once, after its end


def test_each_stream_has_its_own_clock_and_untapped_the_stt_is_as_before():
    facts = []
    tap = ear_tap.Tap("holder", facts.append)
    raw = _STT()
    stt = ear_tap.install_stt(raw, tap)
    stt.stream()._process_stream_event(_msg(ear_feed.UPDATE, words=["w1"], end=100.0))
    first = tap.clock.t0_wall_ms
    stt.stream()._process_stream_event(_msg(ear_feed.UPDATE, words=["w1"], end=0.5))
    assert tap.clock.t0_wall_ms != first and tap.turns.revisions == {0: 1}    # a new stream: a new clock, new turns
    ear_tap.uninstall(stt)
    plain = stt.stream()
    assert plain._process_stream_event.__func__ is _Stream._process_stream_event   # the warm STT given back


def test_a_terminal_mark_is_the_providers_punctuation():
    assert ear_tap.terminal_of({"transcript": "w1 w2?"}) is True
    assert ear_tap.terminal_of({"transcript": "w1 w2"}) is False
    assert ear_tap.terminal_of({"transcript": "", "words": []}) is None


def test_the_ears_own_edges_fall_after_a_short_quiet_and_know_our_voice():
    facts = []
    tap = ear_tap.Tap("holder", facts.append)
    for t in range(0, 300, 30):
        tap.edges.frame(True, t)
    for t in range(300, 510, 30):
        tap.edges.frame(False, t)                                             # 210 ms after the last speech at 270
    assert [(f["edge"], f["t_ms"]) for f in facts] == [("rise", 0), ("fall", 270)]
    tap.playback(True)
    tap.edges.frame(True, 800)
    assert facts[-1]["edge"] == "rise" and facts[-1]["echo_safe"] is False and facts[-2]["t"] == "playback"
    facts.clear()
    tap.edges.frame(True, 1000)
    tap.edges.frame(False, 1150)
    tap.edges.frame(True, 1300)                                               # a 300 ms gap with 150 ms quiet seen
    assert facts == []                                                        # under the quiet tail: still one voice


def test_the_vad_wrapper_reads_the_frames_and_hands_them_on():
    from livekit.agents import vad as vadmod

    class _Inner:
        capabilities = vadmod.VADCapabilities(update_interval=0.03)

        def stream(self):
            evs = [SimpleNamespace(type=vadmod.VADEventType.INFERENCE_DONE, speaking=True),
                   SimpleNamespace(type=vadmod.VADEventType.START_OF_SPEECH, speaking=True)]

            class _S:
                async def __anext__(self):
                    if not evs:
                        raise StopAsyncIteration
                    return evs.pop(0)
            return _S()

    facts = []
    tap = ear_tap.Tap("holder", facts.append)
    wrapped = ear_tap.tap_vad(_Inner(), tap).stream()

    async def go():
        return [ev.type async for ev in wrapped]
    assert len(asyncio.run(go())) == 2 and [f["edge"] for f in facts] == ["rise"]


def test_the_session_is_manual_and_the_room_may_carry_its_own_flag():
    h = ear_tap.manual({"turn_detection": "stt", "endpointing": {"x": 1}, "preemptive_generation": {"enabled": True}})
    assert h == {"turn_detection": "manual", "endpointing": {"x": 1}, "preemptive_generation": {"enabled": False}}
    assert ear_tap.flag_of('{"conv": 1}') == 1 and ear_tap.flag_of("") is None and ear_tap.flag_of("w1") is None
    from nucleo.conversation_host import voice_session
    assert ear_tap.ENDPOINT == voice_session.ENDPOINT


class _Link:
    def __init__(self, answer):
        self.answer, self.posts = answer, []

    async def post(self, path, body, timeout_s=0):
        self.posts.append((path, body))
        return self.answer


@pytest.mark.parametrize("answer, flux, want", [
    ({"on": True, "by": "env"}, True, {"conv": True, "conv_by": "env"}),
    ({"on": True, "by": "env"}, False, {"conv": False, "conv_by": "env",
                                        "conv_why": "the manager's ear needs the streaming provider's turns"}),
    ({"on": False, "by": "default", "why": ""}, True, {"conv": False, "conv_by": "default", "conv_why": ""}),
    (None, True, {"conv": False, "conv_by": "", "conv_why": "the body did not answer in time"}),   # said, then alerted
])
def test_the_voice_builds_the_managers_session_only_on_the_bodys_yes_and_with_turns(answer, flux, want):
    from voice.engine.pipeline import child_session
    link = _Link(answer)
    got = asyncio.run(child_session._conv(link, SimpleNamespace(name="r1", metadata='{"conv": 1}'), flux))
    assert got == want and link.posts == [("/api/voice/child/conv", {"room": "r1", "flag": 1})]


@pytest.fixture
def body(monkeypatch):
    from nucleo.conversation_host import boot, entry, owed, proof
    seen = {"devices": [], "alerts": []}
    monkeypatch.setattr(entry, "device", lambda ep, **st: seen["devices"].append((ep, st)))
    monkeypatch.setattr(boot, "account", lambda: "acct_t")
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda kind, label, **kw: seen["alerts"].append(label) if kind == "alert"
                        else None)
    proof.forget("acct_t")
    yield seen
    owed.set_voice_live(False)
    proof.forget("acct_t")


def test_what_the_voice_built_is_the_sessions_decision_and_the_close_gives_the_voice_back(body):
    from nucleo.conversation_host import owed, switch, voice_session
    s = SimpleNamespace()
    assert voice_session.started(s, {"conv": True, "conv_by": "env"}) is True
    assert switch.on(s) and owed.voice_live() and body["devices"] == [("holder", {"voice_live": True,
                                                                                  "speaker_open": True})]
    voice_session.closed(s)
    assert not owed.voice_live() and body["devices"][-1] == ("holder", {"voice_live": False, "speaker_open": False})
    off = SimpleNamespace()
    assert voice_session.started(off, {"conv": False, "conv_by": "env", "conv_why": "w1"}) is False
    assert not switch.on(off) and body["alerts"] == ["the conversation cannot answer now"]   # silence, and why


def test_the_old_turns_door_answers_nothing_in_a_session_of_the_manager(body, monkeypatch):
    from nucleo.conversation_host import proof, voice_session
    from voice import remote_session
    s = SimpleNamespace()
    voice_session.started(s, {"conv": True})
    monkeypatch.setitem(remote_session._M, "session", s)

    async def go():
        return [line async for line in remote_session.turn_lines({"text": "w1"})]
    assert asyncio.run(go()) == [{"t": "end"}]
    assert proof.report("acct_t")["counters"]["livekit_turns"] == 1
    assert "livekit opened a turn" in body["alerts"]
    from voice.engine.pipeline import first_air
    monkeypatch.setattr(first_air, "decide_kickoff", lambda room, emit: "w_greet")   # the old door would greet
    assert remote_session.kickoff("r1") == {"greet": "", "env": {}}           # what is said is the manager's
    monkeypatch.setitem(remote_session._M, "session", SimpleNamespace())
    assert remote_session.kickoff("r1")["greet"] == ""                        # any session: the only path
    assert voice_session.refuse_turn(SimpleNamespace()) is True               # any session: LiveKit answers nothing


def test_a_body_stalled_for_five_seconds_of_speech_loses_nothing(monkeypatch):
    """Flux at its fastest (a message every 50 ms: words and the watermark) with his voice's frames every 30 ms, for
    five seconds, while the body answers nothing — then it answers: every fact arrives, once, and no gap."""
    link = body_link.BodyLink(base="http://127.0.0.1:1", token="t")
    delivered, calls = [], {"n": 0}

    async def deliver(batch):
        calls["n"] += 1
        if not stalled["over"]:
            link._fail_streak += 1
            await asyncio.sleep(0.001)                                        # a refused POST takes its time
            return False
        delivered.extend(ev for ev in batch if ev.get("k") == "ear")
        link._fail_streak = 0
        return True

    stalled = {"over": False}
    monkeypatch.setattr(link, "_deliver", deliver)
    monkeypatch.setattr(body_link, "RETRY_GAP_S", 0.0)
    tap = ear_tap.Tap("holder", link.send_ear)

    async def go():
        link.start()
        for i in range(100):                                                  # 5 s of messages
            tap.on_message(_msg(ear_feed.UPDATE, turn=0, words=["w1"] * (1 + i % 5), end=0.05 * (i + 1)))
        for t in range(0, 5000, 30):
            tap.edges.frame((t // 600) % 2 == 0, t)
        await asyncio.sleep(0.05)
        stalled["over"] = True
        await asyncio.sleep(0.3)
        await link.aclose()
    asyncio.run(go())
    assert not any(ev.get("t") == "gap" for ev in delivered) and link.stats["ear_lost"] == 0
    seqs = [ev["seq"] for ev in delivered]
    assert seqs == list(range(1, len(seqs) + 1)) and len(seqs) > 200
