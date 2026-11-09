"""voice/lag.py — the voice measures its own lag and acts (V2-831 T-30).

When errands load a small host, the voice goes deaf in stretches: the VAD falls behind real time and the job executor
stops answering its pings — and both were only log lines that nothing in the engine READ. Two declared
signals now feed one reader:
  · the voice loop's own lag: a probe on the session's event loop measures how late its own sleeps wake (`watch`);
  · the SDK's measured delays (VAD inference behind real time, the executor's ping), read from the log RECORD's
    `delay` field, never from its words (`_SdkDelays`).
Over the declared bound (`voice_lag_s` in `config/resources.default.json`, a rule with this reader) it says so: an
event, ONE spoken notice in his language per cooldown, and load shed through the worker envelope (T-27) — a shed
named by its source and released by the reading that drops back under the bound (V2-867 T591).

V2-831 pass 10: the notice was said six times in a TYPED session with the microphone off — the loop lag was the
engine's own heavy turns, not the audio path. So «the voice is falling behind» is ONLY the SDK's audio
signals (VAD inference vs real time, the executor's ping) while audio really flows (`mic_input.hears`) and the cold
start is over (V2-871: the warm-up of the first session is not a lag to shed); the loop's
own lag sheds load QUIETLY (no event, no words); and the notice is spoken only while he is talking and so is the one
not being heard (`proactive.user_speaking`).
"""
from __future__ import annotations

import asyncio
import logging
import time

from loguru import logger

_PERIOD_S = 0.5
_COOLDOWN_S = 60.0
_state = {"last_act": -1e9, "loops": set(), "worst": 0.0, "episode": False}


def bound_s() -> float:
    from nucleo.workers import envelope
    return float(envelope.policy().get("voice_lag_s", 0.5))


LOOP = "voice_loop"     # the session loop's own lag: our turns' work, never the audio path
AUDIO = "voice_audio"   # the SDK's audio signals (VAD vs real time, the executor's ping): the shed source they name


def _audio_flows() -> bool:
    from voice import mic_input
    return mic_input.hears()


def _in_boot_grace() -> bool:
    """V2-871: the cold-start window (`boot_grace_s`) — the first session pays the warm-up, and a hold would only
    slow it."""
    from nucleo.pulse import voice_recycle
    return voice_recycle.in_boot_grace()


def note(lag_s: float, source: str) -> bool:
    """One lag reading. The loop's own lag over the bound only sheds, quietly. An AUDIO signal (the SDK's) over the
    bound while audio flows acts — a shed on every reading, the event once per cooldown, the spoken notice once per EPISODE and only while
    he is talking (said again only after the lag has recovered and come back)."""
    now = time.monotonic()
    from nucleo.workers import envelope
    if source == LOOP:
        if lag_s >= bound_s():
            envelope.shed(_COOLDOWN_S, LOOP)    # quietly: neither an event nor a spoken line
        else:
            envelope.unshed(LOOP)               # V2-867 T591: the hold ends with its cause, the minute is a ceiling
        return False
    _state["worst"] = max(_state["worst"], lag_s)
    if lag_s < bound_s():
        _state["episode"] = False        # recovered: the next episode may be said again
        envelope.unshed(AUDIO)           # releases only the audio's own hold — never the loop's or the watchdog's
        return False
    if not _audio_flows() or _in_boot_grace():
        return False
    envelope.shed(_COOLDOWN_S, AUDIO)    # every reading over the bound holds; only the notice waits a cooldown
    if now - _state["last_act"] < _COOLDOWN_S:
        return False
    _state["last_act"] = now
    first, _state["episode"] = not _state["episode"], True
    try:
        from i18n import langs
        from voice.observer import emit
        emit("alert", str(langs.words("alerts.voice_lag", default="voice_lag")), role="system",
             extra={"cat": "voice", "kind_diag": "voice_lag", "lag_s": round(lag_s, 2), "source": source})
    except Exception as e:  # noqa: BLE001
        logger.debug(f"lag: event not emitted: {e!r}")
    try:
        from i18n import langs
        from nucleo.pulse import notices
        from voice import proactive
        line = str(getattr(langs.current_language(), "voice_lag_notice", "") or "")
        if line and first and proactive.user_speaking():   # he is talking and is the one not being heard
            # one keyed notice per lag episode, through the out-of-turn mouth (V2-851 F2); never to his phone
            asyncio.get_running_loop().create_task(notices.notify(
                "zaelar", line, key=f"voice_lag:{time.time_ns()}", kind="info", push_=False, about="voice_lag"))
    except Exception as e:  # noqa: BLE001 — no running loop (a thread) or no notifier: the event still stands
        logger.debug(f"lag: notice not spoken: {e!r}")
    return True


async def _probe(period_s: float = _PERIOD_S) -> None:
    loop = asyncio.get_running_loop()
    while True:
        t0 = loop.time()
        await asyncio.sleep(period_s)
        note(max(0.0, loop.time() - t0 - period_s), LOOP)


def watch() -> None:
    """Measure the CURRENT event loop (the voice session's) for as long as it runs. Idempotent per loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError as e:
        logger.debug(f"lag: no running loop to measure ({e})")
        return
    if id(loop) in _state["loops"]:
        return
    _state["loops"].add(id(loop))
    loop.create_task(_probe(), name="voice-lag-probe")
    _SdkDelays.install()


def take_worst() -> float:
    """The worst lag since the last call, and reset — the off-host summary's reading (`nucleo/pulse/offhost.py`)."""
    worst, _state["worst"] = float(_state.get("worst") or 0.0), 0.0
    return worst


class _SdkDelays(logging.Handler):
    """The SDK's own measured delays, read from the record's `delay` field (VAD: seconds; executor ping: ms)."""
    _installed = False

    @classmethod
    def install(cls) -> None:
        if not cls._installed:
            logging.getLogger("livekit").addHandler(cls(level=logging.WARNING))
            cls._installed = True

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        delay = getattr(record, "delay", None)
        if not isinstance(delay, (int, float)):
            return
        src = str(getattr(record, "filename", "") or "")
        note(float(delay) / (1000.0 if "executor" in src or "proc" in src else 1.0), src or "livekit")
