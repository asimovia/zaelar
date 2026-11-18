"""The STT stays closed until the voice holder has spoken for its microphone (2026-11-18, session af04be1f).

Measured on his engine: it restarted at 12:52, the screen reconnected, and at 12:53:06 the session's input opened
the speech recogniser («👂 audio input OPEN (STT)») at the boot default — `muted=False`, a value nobody had sent — and
transcribed a sentence he was dictating somewhere else. A boot default is a guess about a person's microphone, and
«open» is the guess that transcribes him.

Pinned here, over the real `voice/mic_input.py` and the real lock routes of `server/livekit_api.py`:
  * after a boot nobody has declared, so an installed input stays CLOSED;
  * the lock (`acquire`/`steal`) carries the holder's switch, so it is known before any room or input exists;
  * a change of hands undeclares — the new surface speaks for its own mic;
  * a client that never declares (an old tab, a bare test participant) is heard after the bounded grace, never deaf.
"""
from __future__ import annotations

import pytest

from voice import mic_input


@pytest.fixture(autouse=True)
def _fresh_boot(monkeypatch):
    monkeypatch.setattr("nucleo.runstate.stopped", lambda: False)
    mic_input.reset(fresh_boot=True)
    yield
    mic_input.reset()


class Sink:
    def __init__(self) -> None:
        self.applied: list[bool] = []

    def __call__(self, enabled: bool) -> None:
        self.applied.append(bool(enabled))


def test_after_a_boot_an_installed_input_stays_closed_until_declared():
    sink = Sink()
    mic_input.use_input(sink)
    assert sink.applied == [False], "THE BUG: the input opened at the boot default before any screen spoke"
    assert mic_input.feeds_stt() is False and mic_input.snapshot()["declared"] is False
    mic_input.set_muted(True, source="heartbeat")
    assert sink.applied == [False], "declared closed: still closed"
    mic_input.set_muted(False, source="orb")
    assert sink.applied == [False, True], "his own open opens it"
    mic_input.clear_input(sink)


def test_the_lock_carries_the_switch_before_any_input_exists():
    from server import livekit_api as la
    la.session_release("tab-a")
    assert la.session_acquire("tab-a", "desktop:aa", True)["ok"] is True
    assert mic_input.snapshot()["declared"] is True and mic_input.is_muted() is True
    sink = Sink()
    mic_input.use_input(sink)
    assert sink.applied == [False], "a reconnect with his mic closed: the session is born deaf to it"
    mic_input.clear_input(sink)
    la.session_release("tab-a")


def test_a_change_of_hands_undeclares():
    from server import livekit_api as la
    la.session_release("tab-a")
    la.session_acquire("tab-a", "desktop:aa", False)
    sink = Sink()
    mic_input.use_input(sink)
    assert sink.applied == [True]
    la.session_steal("phone", "mobile:bb")                 # an older client: no switch with the lock
    assert sink.applied[-1] is False, "the previous surface's open is not the new holder's"
    la.session_heartbeat({"sid": "phone", "muted": False, "dev": "mobile:bb"})
    assert sink.applied[-1] is True
    mic_input.clear_input(sink)
    la.session_release("phone")


def test_a_client_that_never_declares_is_heard_after_the_grace(monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr(mic_input.time, "time", lambda: clock["now"])
    monkeypatch.setattr(mic_input.threading, "Timer", lambda *a, **k: type("T", (), {
        "daemon": True, "start": lambda self: None, "cancel": lambda self: None})())
    sink = Sink()
    mic_input.use_input(sink)
    assert sink.applied == [False]
    clock["now"] += mic_input.UNDECLARED_GRACE_S - 1
    assert mic_input.apply_input() is False, "inside the grace: closed"
    clock["now"] += 2
    assert mic_input.apply_input() is True, "a silent client is never left deaf for good"
    mic_input.clear_input(sink)
