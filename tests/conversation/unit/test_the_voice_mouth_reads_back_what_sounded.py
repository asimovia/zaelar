"""The mouth's voice half reads back what sounded, and his voice cuts ours by a local rule (node 13.90, v3.1 §1.7, B9).

  · `/voice/say` takes `cut` — the speech in course stops first, and with no text that is all it does — and its `done`
    says how much SOUNDED (`spoken_chars`): the speech's own chat item, which LiveKit cuts to what played; a line of
    the manager's (`conv`) keeps that item, and it never reaches the old turn's record;
  · in a session of the manager LiveKit interrupts nothing, so the voice process cuts our voice itself: his voice that
    ROSE after our line began, lasting `min_barge_ms`, cuts it once; a voice already up when our line began (E7) and a
    cough under the threshold do nothing;
  · the body says a line on the voice channel through that door with its `say_id`; its first line is `SayStarted`, its
    `done` is `SayEnded` — `cut` or `played`, what sounded as `agent_estimate` — and an error or a lost line is
    `unknown`, never heard. With no voice session of the manager the line is shown, as before. A stop is the same door.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from conversation.mouth import SayEnded, SayStarted
from voice.engine.pipeline import body_link, child, ear_tap


def _item(text):
    return SimpleNamespace(role="assistant", text_content=text)


def test_what_sounded_is_the_speechs_own_item():
    cut = SimpleNamespace(chat_items=[_item("w1 w2")], interrupted=True)
    assert child.spoken_chars(cut, "w1 w2 w3 w4") == 5
    assert child.spoken_chars(SimpleNamespace(chat_items=[], interrupted=True), "w1 w2") == 0      # nothing played
    assert child.spoken_chars(SimpleNamespace(chat_items=[], interrupted=False), "w1 w2") == 5


class _Resp:
    def __init__(self, headers=None):
        self.lines = []

    async def prepare(self, request):
        return None

    async def write(self, data):
        import json
        self.lines.append(json.loads(data.decode()))


class _Speech:
    def __init__(self, text, interrupted=False, sounded=None):
        self.id, self.interrupted = "sp1", interrupted
        self.chat_items = [_item(sounded if sounded is not None else text)]
        self.allow_interruptions = True

    def done(self):
        return False

    def interrupt(self):
        self.interrupted = True

    def __await__(self):
        return asyncio.sleep(0).__await__()


class _Session:
    def __init__(self, speech=None):
        self.current_speech, self.said = speech, []

    def say(self, text, allow_interruptions=True, add_to_chat_ctx=True):
        self.said.append((text, add_to_chat_ctx))
        return _Speech(text, interrupted=True, sounded=text[:4])


def _call(monkeypatch, body, session):
    monkeypatch.setenv(body_link.TOKEN_ENV, "tok")
    monkeypatch.setattr(child.web, "StreamResponse", _Resp)
    monkeypatch.setattr(child, "has_listener", lambda ctx: True)
    monkeypatch.setitem(child.LIVE, "session", session)
    monkeypatch.setitem(child.LIVE, "conv_says", set())
    monkeypatch.setitem(child.LIVE, "aliases", {})

    async def go():
        monkeypatch.setitem(child.LIVE, "loop", asyncio.get_running_loop())

        async def _json():
            return body
        return await child.say(SimpleNamespace(headers={body_link.HEADER: "tok"}, json=_json))
    return asyncio.run(go()).lines


def test_a_line_of_the_managers_says_what_sounded_and_is_kept_off_the_old_record(monkeypatch):
    s = _Session()
    lines = _call(monkeypatch, {"text": "w1 w2 w3", "alias": "s_000001", "conv": True, "ephemeral": True}, s)
    assert s.said == [("w1 w2 w3", True)]                                      # its item kept, to be read back
    assert lines[0] == {"id": "sp1"} and lines[-1]["done"] and lines[-1]["interrupted"]
    assert lines[-1]["spoken_chars"] == 4 and "sp1" in child.LIVE["conv_says"]


def test_a_cut_with_no_text_is_a_pure_stop(monkeypatch):
    speech = _Speech("w9")
    s = _Session(speech)
    lines = _call(monkeypatch, {"text": "", "cut": True, "conv": True}, s)
    assert lines == [{"id": "", "done": True, "stopped": True}] and speech.interrupted and s.said == []


def _tap(min_ms=500):
    facts, cuts = [], []
    tap = ear_tap.Tap("holder", facts.append)
    tap.on_barge, tap.min_barge_ms = (lambda: cuts.append(1)), min_ms
    return tap, cuts


def test_his_voice_rising_after_our_line_began_cuts_it_once():
    tap, cuts = _tap()
    tap.playback(True, now_ms=1000)
    tap.heard, tap.line = ("wq", "wr"), "w1 w2 w3"                              # his words, not ours
    for t in range(1500, 2400, 30):
        tap.edges.frame(True, t)
    assert cuts == [1]                                                          # once, after 500 ms of his voice


def test_a_voice_already_up_or_a_cough_never_cuts_ours():
    tap, cuts = _tap()
    for t in range(0, 900, 30):
        tap.edges.frame(True, t)                                                # the television, up before us
        if t == 300:
            tap.playback(True, now_ms=300)
    assert cuts == []
    tap2, cuts2 = _tap()
    tap2.playback(True, now_ms=0)
    for t in range(100, 400, 30):
        tap2.edges.frame(True, t)                                               # 300 ms: a cough
    for t in range(400, 700, 30):
        tap2.edges.frame(False, t)
    assert cuts2 == []


class _Client:
    def __init__(self, lines=None, boom=None):
        self.lines, self.boom, self.posts, self.payloads = lines or [], boom, [], []
        self._loop = None

    def env_diff(self):
        return {}

    async def say_stream(self, payload):
        self.payloads.append(payload)
        for line in self.lines:
            yield line
        if self.boom:
            raise self.boom

    def post_soon(self, path, payload):
        self.posts.append((path, payload))


@pytest.fixture
def live(monkeypatch):
    from nucleo.conversation_host import switch
    from voice import observer, remote_session as rs
    monkeypatch.setattr(observer, "emit", lambda *a, **k: None)
    loop = asyncio.new_event_loop()
    import threading
    t = threading.Thread(target=loop.run_forever, daemon=True)
    t.start()

    def make(client):
        client._loop = loop
        sess = SimpleNamespace(_conversation_switch=switch.Decision(True, "voice"))
        monkeypatch.setitem(rs._M, "session", sess)
        monkeypatch.setitem(rs._M, "client", client)
        return client
    yield make
    loop.call_soon_threadsafe(loop.stop)
    t.join(2)


def _order(say_id="s_000001", text="w1 w2 w3", channels=frozenset({"voice", "text"})):
    return SimpleNamespace(say_id=say_id, text=text, channels=channels, endpoint="holder", request_id="r_iv_000001")


def _speak(order):
    import threading
    from nucleo.conversation_host import voice_mouth
    acks, done = [], threading.Event()

    def ack(sig):
        acks.append(sig)
        if isinstance(sig, SayEnded):
            done.set()
    started = voice_mouth.speak(order, ack)
    done.wait(3)
    return started, acks


def test_the_body_says_on_the_voice_and_reads_back_what_sounded(live):
    client = live(_Client([{"id": "sp1"}, {"done": True, "interrupted": True, "spoken_chars": 4}]))
    started, acks = _speak(_order())
    assert started and client.payloads[0]["alias"] == "s_000001" and client.payloads[0]["conv"] is True
    assert isinstance(acks[0], SayStarted)
    assert (acks[1].outcome, acks[1].heard_chars, acks[1].source) == ("cut", 4, "agent_estimate")


@pytest.mark.parametrize("client", [_Client([{"id": ""}, {"done": True, "error": "no_session"}]),
                                    _Client([{"id": "sp1"}], boom=OSError("w_lost")),
                                    _Client([{"id": "sp1"}])])
def test_a_line_whose_end_was_not_heard_is_unknown(live, client):
    live(client)
    _started, acks = _speak(_order())
    assert (acks[-1].outcome, acks[-1].heard_chars, acks[-1].source) == ("unknown", None, "unknown")


def test_with_no_voice_session_of_the_manager_the_line_is_shown(monkeypatch):
    from nucleo.conversation_host import voice_mouth
    from nucleo.conversation_host.mouth import WallMouth
    from voice import observer, remote_session as rs
    monkeypatch.setattr(observer, "emit", lambda *a, **k: None)
    monkeypatch.setitem(rs._M, "session", None)
    acks = []
    m = WallMouth(SimpleNamespace(now_ms=lambda: 5), voice=voice_mouth)
    m.ack = acks.append
    asyncio.run(m.say(_order()))
    assert [type(a).__name__ for a in acks] == ["SayStarted", "SayEnded"] and acks[1].source == "shown"


def test_a_stop_is_the_same_door_with_cut_and_no_text(live):
    from nucleo.conversation_host import voice_mouth
    client = live(_Client())
    assert voice_mouth.stop() and client.posts == [("/voice/say", {"text": "", "cut": True, "conv": True})]


def test_a_voice_line_is_shown_and_its_acks_wait_for_the_voice(monkeypatch):
    from nucleo.conversation_host.mouth import WallMouth
    from voice import observer
    shown = []
    monkeypatch.setattr(observer, "emit", lambda kind, label, **kw: shown.append(kw.get("text")))
    spoken = []
    voice = SimpleNamespace(speak=lambda order, ack: spoken.append(order.say_id) or True, stop=lambda: True)
    acks = []
    m = WallMouth(SimpleNamespace(now_ms=lambda: 5), voice=voice)
    m.ack = acks.append
    asyncio.run(m.say(_order()))
    assert shown == ["w1 w2 w3"] and spoken == ["s_000001"] and acks == []        # on the wall, and said
    asyncio.run(m.say(_order(say_id="s_000002", channels=frozenset({"text"}))))
    assert spoken == ["s_000001"] and [a.source for a in acks if isinstance(a, SayEnded)] == ["shown"]
