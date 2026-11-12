"""The voice runs in its OWN process, and everything the turn did embedded still crosses the seam (V2-891, node 3.190).

Measured on the operator's machine (session 5b389ca7): with the LiveKit job a THREAD of the body, a host short of
memory stalled the ear — `job executor is unresponsive` ×8, seven Deepgram 1011s (the sentence arriving in pieces) —
because the ear shared a heap and a GIL with everything the body holds. So the voice is its own process
(`python -m voice.engine`) and the body only answers it over loopback. What this file pins:

  (a) the topology is the voice's own process unless `ZAELAR_VOICE_EMBEDDED=1` — the disarm, and the escape hatch;
  (b) the voice process imports none of the brain: no memory, no widgets, no turn, no server;
  (c) it is spawned with a per-spawn token, its parent's pid and the body's loopback address, and the body's doors for
      it refuse a call without that token or from off this host;
  (d) the turn crosses intact: the body's stream carries the lead-in cover as its OWN line, the reply's chunks after
      it, and the voice process turns the cover into a segment of its own (text + FlushSentinel) marked for the
      transcript to strip — the same contract `filler_audio.llm_node_with_filler` keeps embedded;
  (e) the session's facts are replayed through the SAME handlers: his VAD edge sets the «he is speaking» probe the
      proactive mouth asks, his resumed voice leaves the V2-888 mark the turn reads, and the session's typed door
      sends the screen that typed the line with the reply;
  (f) the body's speech requests reach the voice process (say, mute, re-point) and a «say» is awaited until it played.

Disarms (each seen red): `ZAELAR_VOICE_EMBEDDED=1` → (a); a top-level `import nucleo.turn` in `child_session.py` →
(b); drop the token check in `server/voice_child_api._allowed` → (c); drop the `FlushSentinel` branch in
`remote_session.turn_lines` (the cover sent as a chunk) → (d); replay `user_state` without `_on_user_state` → (e).
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

from voice import child_process, remote_session


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    from nucleo.input import typed
    from voice import screens
    monkeypatch.delenv("ZAELAR_VOICE_EMBEDDED", raising=False)
    remote_session.reset_for_tests()
    typed.reset()
    screens._reset_for_tests()
    yield
    remote_session.reset_for_tests()
    typed.reset()
    screens._reset_for_tests()


# ── (a) the topology ────────────────────────────────────────────────────────────────────────────────────────────

def test_the_voice_is_its_own_process_unless_embedded_is_asked(monkeypatch):
    assert not child_process.embedded()
    assert child_process.factory() is child_process.make_child
    monkeypatch.setenv("ZAELAR_VOICE_EMBEDDED", "1")
    from voice.engine.pipeline.agent import make_server
    assert child_process.embedded() and child_process.factory() is make_server


def test_the_heartbeat_and_the_boot_build_the_voice_through_the_one_factory():
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    assert "child_process.factory()" in (root / "server/boot/surfaces.py").read_text(encoding="utf-8")
    assert "child_process.factory()" in (root / "nucleo/pulse/homeostasis.py").read_text(encoding="utf-8")


# ── (b) the voice process holds no brain ────────────────────────────────────────────────────────────────────────

def test_the_voice_process_imports_none_of_the_brain():
    code = ("import sys\n"
            "import voice.engine.pipeline.child, voice.engine.pipeline.child_session, voice.engine.pipeline.remote_brain\n"
            "import voice.engine.pipeline.zaelar_agent, voice.engine.pipeline.agent\n"
            "bad = sorted(m for m in sys.modules if m.split('.')[0] in ('memory', 'widgets', 'server', 'connectors',"
            " 'search', 'rules', 'bus') or m.startswith(('nucleo.turn', 'nucleo.flash', 'voice.engine.llm.providers')))\n"
            "print(__import__('json').dumps(bad))\n")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    assert json.loads(out.stdout.strip().splitlines()[-1]) == []


# ── (c) the spawn contract and the doors ────────────────────────────────────────────────────────────────────────

def test_the_voice_process_is_spawned_with_its_token_its_parent_and_the_body(monkeypatch):
    import os
    monkeypatch.setenv("PORT", "45999")
    monkeypatch.setenv("ZAELAR_VOICE_EMBEDDED", "")
    child = child_process.VoiceChild()
    env = child._env()
    assert env["ZAELAR_VOICE_ROLE"] == "child"
    assert env["ZAELAR_VOICE_TOKEN"] == child.token and len(child.token) >= 24
    assert env["ZAELAR_VOICE_PARENT"] == str(os.getpid())
    assert env["ZAELAR_BODY_URL"] == "http://127.0.0.1:45999" and child.port == 46999
    assert "ZAELAR_VOICE_EMBEDDED" not in env
    assert "ZAELAR_VOICE_TOKEN" not in os.environ, "the token must never reach the body's own env (its workers)"


def _req(host: str, token: str):
    return SimpleNamespace(client=SimpleNamespace(host=host), headers={"x-zaelar-voice-token": token})


def test_the_bodys_doors_answer_only_its_own_voice_process(monkeypatch):
    from server import voice_child_api as api
    monkeypatch.setitem(child_process._STATE, "token", "tok-123")
    assert api._allowed(_req("127.0.0.1", "tok-123"))
    assert not api._allowed(_req("127.0.0.1", "wrong"))
    assert not api._allowed(_req("127.0.0.1", ""))
    assert not api._allowed(_req("203.0.113.9", "tok-123")), "a call from off this host is never the voice process"
    monkeypatch.setitem(child_process._STATE, "token", "")
    assert not api._allowed(_req("127.0.0.1", "")), "an embedded engine (no token) answers nobody"


# ── (d) the turn crosses intact ─────────────────────────────────────────────────────────────────────────────────

class _FakeBrainStream:
    def __init__(self, chunks, delay):
        self._chunks, self._delay = chunks, delay

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        from livekit.agents.llm import ChatChunk, ChoiceDelta
        await asyncio.sleep(self._delay)
        for c in self._chunks:
            yield ChatChunk(id="x", delta=ChoiceDelta(role="assistant", content=c))


class _FakeBrain:
    def __init__(self, chunks, delay=0.0):
        self.chunks, self.delay, self.seen = chunks, delay, []

    def chat(self, *, chat_ctx, **_k):
        self.seen.append(chat_ctx.items[-1].text_content)
        return _FakeBrainStream(self.chunks, self.delay)


def _collect(agen):
    async def _run():
        return [line async for line in agen]
    return asyncio.run(_run())


def test_the_turn_stream_carries_the_cover_as_its_own_line_then_the_reply(monkeypatch):
    from voice.engine.speech import filler_audio as fa
    fa._reset_for_tests()
    brain = _FakeBrain(["Cuatro.", " ¿Algo más?"], delay=0.5)
    remote_session._M["brain"] = brain
    monkeypatch.setattr(fa, "delay_ms", lambda: 50)
    monkeypatch.setattr(fa, "_consume_arm", lambda: (SimpleNamespace(), "neutral", "Un segundo…"))
    monkeypatch.setattr(fa, "_pick_phrase", lambda b, k, p: p)
    lines = _collect(remote_session.turn_lines({"text": "¿cuánto es dos más dos?", "speech_id": "sp_1"}))
    kinds = [ln["t"] for ln in lines if ln["t"] != "env"]
    assert kinds[0] == "filler" and lines[[ln["t"] for ln in lines].index("filler")]["text"] == "Un segundo…"
    assert "".join(ln["text"] for ln in lines if ln["t"] == "c") == "Cuatro. ¿Algo más?"
    assert kinds[-1] == "end"
    assert brain.seen == ["¿cuánto es dos más dos?"]
    assert not fa._pending_strip, "the body's own strip queue must not grow: the voice process strips its transcript"


def test_a_turn_that_fails_in_the_body_says_so_on_the_stream():
    class _Boom(_FakeBrain):
        def chat(self, **_k):
            raise RuntimeError("provider down")
    remote_session._M["brain"] = _Boom([])
    lines = _collect(remote_session.turn_lines({"text": "hola"}))
    assert lines[-1]["t"] == "err" and "provider down" in lines[-1]["msg"]


class _FakeLink:
    def __init__(self, lines):
        self.lines, self.sent, self.queued, self.returned = lines, [], [{"k": "user_state", "state": "listening"}], []

    async def ahead(self):
        out, self.queued = self.queued, []
        return out

    def back(self, events):
        self.returned.append(list(events))

    async def stream(self, _path, payload):
        self.payload = payload
        for ln in self.lines:
            yield ln

    def send(self, ev):
        self.sent.append(ev)


def test_the_voice_process_speaks_the_cover_as_its_own_segment(monkeypatch):
    from livekit.agents.types import FlushSentinel
    from voice.engine.pipeline import body_link, remote_brain
    from voice.engine.speech import filler_audio as fa
    fa._reset_for_tests()
    link = _FakeLink([{"t": "env", "env": {"ZAELAR_LANGUAGE": "es"}}, {"t": "filler", "text": "Un segundo…"},
                      {"t": "c", "text": "Cuatro."}, {"t": "end"}])
    monkeypatch.setattr(body_link, "get", lambda: link)
    monkeypatch.delenv("ZAELAR_LANGUAGE", raising=False)
    ctx = SimpleNamespace(items=[SimpleNamespace(role="user", text_content="¿cuánto es dos más dos?")])

    async def _run():
        tok = remote_brain.CHILD_ORIGIN.set("phone")
        try:
            return [x async for x in remote_brain.remote_llm_node(None, ctx, [], None)]
        finally:
            remote_brain.CHILD_ORIGIN.reset(tok)
    out = asyncio.run(_run())
    assert out[0] == "Un segundo… " and isinstance(out[1], FlushSentinel) and out[2] == "Cuatro."
    assert fa.strip_if_filler("Un segundo…"), "the cover is marked for the transcript node to strip"
    assert link.payload["events"] == [{"k": "user_state", "state": "listening"}] and not link.returned, \
        "the turn carries the facts queued before it (node 3.203 holds the order)"
    assert link.payload["text"] == "¿cuánto es dos más dos?" and link.payload["origin"] == "phone"
    import os
    assert os.environ.get("ZAELAR_LANGUAGE") == "es", "the body's live settings reach the voice before it speaks"
    monkeypatch.delenv("ZAELAR_LANGUAGE", raising=False)


def test_a_lost_body_is_said_slow_never_silence(monkeypatch):
    """E0: a body that cannot be reached is tried once more and then said SLOW — his words were heard, the host did
    not run — never «say that again» (node 3.203 holds the retry, the pacing and the kept line)."""
    from voice.engine.pipeline import body_link, remote_brain

    class _Down(_FakeLink):
        async def stream(self, _p, _payload):
            raise OSError("connection refused")
            yield  # pragma: no cover

    monkeypatch.setattr(body_link, "get", lambda: _Down([]))
    monkeypatch.setattr(remote_brain, "RETRY_S", 0.01)
    monkeypatch.setattr(remote_brain, "_line", {"say_again": "Perdona, ¿me lo repites?",
                                                "brain_slow": "Un momento, el sistema va lento."}.get)
    ctx = SimpleNamespace(items=[SimpleNamespace(role="user", text_content="hola")])

    async def _run():
        return [x async for x in remote_brain.remote_llm_node(None, ctx, [], None)]
    assert asyncio.run(_run()) == ["Un momento, el sistema va lento."]


# ── (e) the session's facts replayed through the same handlers ──────────────────────────────────────────────────

class _FakeClient:
    def __init__(self):
        self.calls = []
        self.base = "http://127.0.0.1:1"

    def bind(self, loop):
        pass

    def env_diff(self):
        return {}

    def post_soon(self, path, payload=None):
        self.calls.append((path, payload or {}))

    async def post(self, path, payload=None, timeout_s=3.0):
        self.calls.append((path, payload or {}))
        return {"ok": True}

    async def say_stream(self, payload):
        self.calls.append(("/voice/say", payload))
        yield {"id": "speech_lk1"}
        await asyncio.sleep(0.05)
        yield {"done": True}


def _start(monkeypatch, client):
    remote_session.use_client(client)
    remote_session._M["brain"] = _FakeBrain([])
    from voice.engine.speech import live_tts
    monkeypatch.setattr(live_tts, "attach", lambda *a, **k: None)


def test_his_voice_edge_reaches_the_probes_and_the_resume_mark(monkeypatch):
    from nucleo.input import typed
    from voice import proactive
    client = _FakeClient()

    async def _run():
        _start(monkeypatch, client)
        remote_session.handle_batch([{"k": "session", "what": "started", "room": "zaelar-t"}])
        mark = typed.mark()
        remote_session.handle_batch([{"k": "user_state", "state": "speaking"}])
        speaking = proactive.user_speaking()
        resumed_on = typed.resumed_since(mark)
        remote_session.handle_batch([{"k": "user_state", "state": "listening"}])
        after = proactive.user_speaking()
        remote_session.handle_batch([{"k": "session", "what": "closed", "cause": "participant_disconnected"}])
        return speaking, after, resumed_on
    speaking, after, _ = asyncio.run(_run())
    assert speaking is True and after is False
    assert typed._state["onset"] > 0 and typed._state["end"] >= typed._state["onset"], \
        "his edges reach the typed-order marks the V2-888 supersede reads"
    assert not remote_session.live()


def test_the_typed_door_sends_the_screen_that_typed_it(monkeypatch):
    from voice import screens
    client = _FakeClient()

    async def _run():
        _start(monkeypatch, client)
        remote_session.handle_batch([{"k": "session", "what": "started", "room": "zaelar-t"}])
        assert screens.has_session()
        await screens.deliver_typed("¿y tres por tres?", "phone-1")
        await asyncio.sleep(0.05)
        remote_session.handle_batch([{"k": "session", "what": "closed"}])
    asyncio.run(_run())
    replies = [p for path, p in client.calls if path == "/voice/reply"]
    assert replies and replies[0]["text"] == "¿y tres por tres?" and replies[0]["origin"] == "phone-1"
    assert not screens.has_session(), "the typed door closes with the session"


def test_a_room_closing_late_never_unregisters_the_room_that_replaced_it(monkeypatch):
    from voice import screens
    client = _FakeClient()

    async def _run():
        _start(monkeypatch, client)
        remote_session.handle_batch([{"k": "session", "what": "started", "room": "zaelar-a"}])
        remote_session.handle_batch([{"k": "session", "what": "started", "room": "zaelar-b"}])
        remote_session.handle_batch([{"k": "session", "what": "closed", "room": "zaelar-a"}])
        alive = remote_session.live() and screens.has_session()
        remote_session.handle_batch([{"k": "session", "what": "closed", "room": "zaelar-b"}])
        return alive, remote_session.live()
    alive, after = asyncio.run(_run())
    assert alive, "the screen the voice moved to lost its session when the old room closed"
    assert after is False


# ── (f) what the body asks of the voice ─────────────────────────────────────────────────────────────────────────

def test_a_proactive_line_is_said_by_the_voice_process_and_awaited_until_it_played(monkeypatch):
    from voice import proactive
    client = _FakeClient()

    async def _run():
        _start(monkeypatch, client)
        remote_session.handle_batch([{"k": "session", "what": "started", "room": "zaelar-t"}])
        sp = proactive._speaker
        t0 = asyncio.get_running_loop().time()
        await sp("Tu tarea ha terminado.")
        waited = asyncio.get_running_loop().time() - t0
        remote_session.handle_batch([{"k": "data", "topic": "zaelar-voice",
                                      "data": __import__("base64").b64encode(b'{"audio": false}').decode()}])
        await asyncio.sleep(0.02)
        remote_session.handle_batch([{"k": "session", "what": "closed"}])
        return waited
    waited = asyncio.run(_run())
    says = [p for path, p in client.calls if path == "/voice/say"]
    assert says and says[0]["text"] == "Tu tarea ha terminado." and says[0]["alias"].startswith("rs_")
    assert waited >= 0.04, "the speaker returned before the voice process said the line had played"
    assert ("/voice/audio", {"output": False}) in client.calls, "the 🔊 mute reaches the synthesis it silences"


def test_the_live_voice_is_re_pointed_in_the_voice_process():
    client = _FakeClient()
    tts = remote_session.RemoteTTS(client)
    from voice.engine.speech import live_tts
    live_tts.attach(tts, "inworld")
    try:
        assert live_tts.apply_voice("Alvaro", "es") is True
    finally:
        live_tts.detach(tts)
    assert ("/voice/tts", {"voice_id": "Alvaro", "lang": "es"}) in client.calls
