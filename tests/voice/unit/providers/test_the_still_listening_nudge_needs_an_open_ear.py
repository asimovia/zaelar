"""«Sigo aquí, cuando quieras sigue» is an invitation to go on talking, so it is never said into a closed microphone.

Measured 2026-11-17: a fragment held because its STT final ended in a comma scheduled the accumulator's
still-listening nudge (`acc_notices._schedule_acc_nudge`); the nudge checked only that he was not speaking and the
voice was not hushed, and it spoke 4 s after the audio input had closed — a line above his pending one, inviting
words nobody would transcribe. The ear is `voice.mic_input.feeds_stt()` (muted, parked for the wake word, or ⏻
stopped all answer no), and the nudge asks it before each of its two checks.
"""
from __future__ import annotations

import asyncio

import pytest

from voice import mic_input, proactive
from voice.engine.llm.providers import acc_notices
from voice.engine.llm.providers import nucleo as nucleo_provider


class _Acc:
    def pending(self) -> bool:
        return True


class _Brain:
    _acc_gen = 7
    _acc = _Acc()


@pytest.fixture
def spoken(monkeypatch):
    said: list[str] = []

    async def _speak(text: str) -> None:
        said.append(text)

    proactive.register_speaker(_speak)
    monkeypatch.setattr(acc_notices, "_ACC_NUDGE_S", 0.0)
    monkeypatch.setattr(acc_notices, "_ACC_SETTLE_S", 0.0)
    monkeypatch.setattr(proactive, "user_speaking", lambda: False)
    monkeypatch.setattr(proactive, "hushed", lambda: False)
    from nucleo import runstate
    monkeypatch.setattr(runstate, "stopped", lambda: False)
    monkeypatch.setitem(mic_input._state, "muted", False)
    monkeypatch.setitem(mic_input._tap, "parked", False)
    # V2-937: an undeclared mic feeds no STT; the open-ear case is a holder that declared its switch open.
    monkeypatch.setitem(mic_input._decl, "declared", True)
    tasks: list = []
    monkeypatch.setattr(nucleo_provider, "_spawn", lambda coro, label: tasks.append(coro))
    yield said, tasks
    proactive.clear_speaker(_speak)


def _nudge(tasks) -> None:
    acc_notices._schedule_acc_nudge(_Brain(), 7)
    assert len(tasks) == 1, "the nudge is scheduled through the provider's task registry"
    asyncio.run(tasks.pop())


def test_the_nudge_speaks_while_his_microphone_reaches_the_recogniser(spoken):
    said, tasks = spoken
    _nudge(tasks)
    assert len(said) == 1, "an open ear and a held fragment: the one reassurance ping is said"


@pytest.mark.parametrize("closed", ["muted", "parked", "stopped"])
def test_the_nudge_is_never_said_into_a_closed_microphone(spoken, monkeypatch, closed):
    said, tasks = spoken
    if closed == "muted":
        monkeypatch.setitem(mic_input._state, "muted", True)
    elif closed == "parked":
        monkeypatch.setitem(mic_input._tap, "parked", True)
    else:
        from nucleo import runstate
        monkeypatch.setattr(runstate, "stopped", lambda: True)
    _nudge(tasks)
    assert said == [], f"the input is closed ({closed}): «go on» would invite words nobody hears"


def test_an_ear_that_closes_during_the_settle_still_silences_it(spoken, monkeypatch):
    """The second check, after the breath: the mic closed between the first look and the line."""
    said, tasks = spoken
    real_sleep = asyncio.sleep
    calls = {"n": 0}

    async def _sleep(s):
        calls["n"] += 1
        if calls["n"] == 2:                       # the settle: he closes the mic during it
            mic_input._state["muted"] = True
        await real_sleep(0)
    monkeypatch.setattr(acc_notices.asyncio, "sleep", _sleep)
    _nudge(tasks)
    assert said == []
