"""Closing the mic keeps what was heard, drops what came after, and never silences the agent (audit 2026-11-14, C).

The operator used the mic as push-to-talk that night:
- **failure 13** — he closed it 0.4 s after his last word and the sentence was lost: the input closed, the STT never
  produced a final, and no turn was born.
- **failure 15** — on reopening, that unconfirmed leftover came back glued in front of his next sentence.
- **failure 12** — he closed it mid-sentence at 00:02:42; from then on every reply was synthesised and none was spoken
  (state stuck at «thinking») until the mic reopened at 00:03:34. Every LiveKit reply waits for his silence
  (`_user_silence_event`); a VAD inference queued before the close re-cleared it and no frame could set it again.

One door (`agent_events.set_ear`, behind `mic_input`'s lever, for the embedded session and the voice process): a close
commits what was heard (LiveKit's push-to-talk commit), keeps his silence while closed, and an open clears the leftover.
His rule stays: audio after the close never acts — only the one turn the close committed passes `blocks_turn`.
Every closed state of the lever (mic, parked tap, ⏻) is the same close. es/en; each mechanism disarmed → red.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from voice import attention, mic_input
from voice.engine.pipeline import agent_events


class _Input:
    def __init__(self):
        self.audio_enabled = True

    def set_audio_enabled(self, on):
        self.audio_enabled = bool(on)


class _Session:
    """The slice of LiveKit's AgentSession the ear uses."""
    def __init__(self, heard="abre la agenda"):
        self.input, self.log, self.heard = _Input(), [], heard
        self._activity = SimpleNamespace(_user_silence_event=asyncio.Event())

    def commit_user_turn(self, *, transcript_timeout, stt_flush_duration):
        self.log.append(("commit", transcript_timeout, stt_flush_duration))
        fut = asyncio.get_running_loop().create_future()
        fut.set_result(self.heard)
        return fut

    def clear_user_turn(self):
        self.log.append(("clear",))

    def on(self, *_a, **_k):
        return None


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    mic_input.reset()
    attention.reset()
    monkeypatch.setattr(agent_events, "_SILENCE_RECHECK_S", (0.01,))
    yield
    mic_input.reset()
    attention.reset()


async def _settle():
    await asyncio.sleep(0.05)


def _run(coro):
    return asyncio.run(coro)


# ── the close commits what was heard; the open clears the leftover ─────────────────────────────────────────────────
def test_a_close_commits_what_was_heard_and_an_open_clears_the_leftover():
    async def go():
        s, said = _Session(), []
        agent_events.set_ear(s, False, _emit=lambda *a, **k: said.append((a[1], k.get("text"))))
        await _settle()
        assert s.input.audio_enabled is False and s.log == [("commit", 2.0, 2.0)]
        assert said == [("🎤⃠ heard before the close — committed", "abre la agenda")]
        agent_events.set_ear(s, False)                       # the beat re-asserting it: no second commit
        agent_events.set_ear(s, True)
        assert s.input.audio_enabled is True and s.log[-1] == ("clear",) and len(s.log) == 2
    _run(go())


def test_nothing_heard_is_dropped_and_said():
    async def go():
        s, said = _Session(heard=""), []
        agent_events.set_ear(s, False, _emit=lambda *a, **k: said.append(a[1]))
        await _settle()
        assert said == ["🎤⃠ nothing heard before the close — dropped"]
    _run(go())


def test_disarmed_a_bare_input_close_commits_nothing(monkeypatch):
    """RED proof: the lever back to the old body (it only flips the input) → the heard words get no turn (failure 13)."""
    monkeypatch.setattr(agent_events, "set_ear", lambda session, enabled, **k: session.input.set_audio_enabled(enabled))

    async def go():
        s = _Session()
        agent_events.open_mic_door(session=s)
        mic_input.set_muted(True, source="test")
        await _settle()
        assert s.input.audio_enabled is False and s.log == []
    _run(go())


# ── every closed state of the lever is the same close, through the one door ───────────────────────────────────────
def _close(how):
    if how == "mic":
        mic_input.set_muted(True, source="test")
    elif how == "parked":
        mic_input.set_parked(True)
    else:
        from nucleo import runstate
        real = runstate.stopped
        runstate.stopped = lambda: True
        try:
            mic_input.apply_input()
        finally:
            runstate.stopped = real


@pytest.mark.parametrize("how", ["mic", "parked", "stopped"])
def test_every_closed_state_commits_through_the_same_door(how):
    async def go():
        s = _Session()
        agent_events.open_mic_door(session=s)
        _close(how)
        await _settle()
        assert s.log == [("commit", 2.0, 2.0)], how
        if how == "mic":                                     # …and the turn it commits passes the closed switch, once
            assert mic_input.blocks_turn("abre la agenda") is False
            assert mic_input.blocks_turn("abre la agenda") is True
        mic_input.reset()
    _run(go())


def test_the_voice_process_applies_the_same_door(monkeypatch):
    """The body's RemoteSession only carries the lever (`/voice/audio`); the voice process runs `set_ear` on it."""
    from voice.engine.pipeline import body_link, child
    posted = []
    remote = SimpleNamespace(input=SimpleNamespace(set_audio_enabled=lambda on: posted.append(on)))
    agent_events.set_ear(remote, False)
    assert posted == [False]
    live = _Session()
    monkeypatch.setenv(body_link.TOKEN_ENV, "tok")
    monkeypatch.setitem(child.LIVE, "session", live)

    async def go():
        monkeypatch.setitem(child.LIVE, "loop", asyncio.get_running_loop())

        async def _json():
            return {"input": False}
        await child.audio(SimpleNamespace(headers={body_link.HEADER: "tok"}, json=_json))
        await _settle()
    _run(go())
    assert live.log == [("commit", 2.0, 2.0)]


# ── the agent still speaks with the mic closed (failure 12) ────────────────────────────────────────────────────────
def test_his_silence_holds_while_the_input_is_closed():
    async def go():
        s = _Session()
        agent_events.set_ear(s, False)
        s._activity._user_silence_event.clear()            # the late VAD inference «speaking» after the close
        await _settle()
        assert s._activity._user_silence_event.is_set(), "every reply would wait for a silence no frame can bring"
    _run(go())


def test_an_open_input_leaves_the_vad_in_charge():
    s = _Session()
    s._activity._user_silence_event.clear()
    agent_events._silent_while_closed(s)
    assert not s._activity._user_silence_event.is_set()


def test_disarmed_without_the_silence_guard_the_replies_wait_again(monkeypatch):
    """RED proof: no re-assertion → the event stays cleared, as in failure 12."""
    monkeypatch.setattr(agent_events, "_silent_while_closed", lambda session: None)

    async def go():
        s = _Session()
        agent_events.set_ear(s, False)
        s._activity._user_silence_event.clear()
        await _settle()
        assert not s._activity._user_silence_event.is_set()
    _run(go())


# ── his rule: only the turn the close committed passes the closed switch ───────────────────────────────────────────
@pytest.mark.parametrize("heard", ["ábreme el mensaje de Laura, por favor", "open the message from Laura, please"])
def test_the_committed_turn_passes_once_and_audio_after_the_close_never_does(heard):
    mic_input.set_muted(True, source="test")
    mic_input.note_closed_on_words()
    assert mic_input.blocks_turn(heard) is False             # heard BEFORE the close: said
    assert mic_input.blocks_turn(heard) is True              # anything else with the switch closed: swallowed


def test_a_stale_close_licenses_nothing():
    mic_input.set_muted(True, source="test")
    mic_input.note_closed_on_words(now=1.0)
    assert mic_input.blocks_turn("abre la agenda") is True


def test_a_typed_line_still_passes_a_closed_mic():
    mic_input.set_muted(True, source="test")
    attention.note_typed(text="abre la agenda")
    assert mic_input.blocks_turn("abre la agenda") is False


def test_disarmed_without_the_mark_the_heard_sentence_is_swallowed(monkeypatch):
    """RED proof: the gate no longer knows the close committed it → the sentence dies at the switch (failure 13)."""
    monkeypatch.setattr(mic_input, "_heard_before_close", lambda now=None: False)
    mic_input.set_muted(True, source="test")
    mic_input.note_closed_on_words()
    assert mic_input.blocks_turn("open the message from Laura") is True
