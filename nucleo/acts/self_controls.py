"""nucleo/acts/self_controls.py — the agent's OWN controls by voice: its speaker, its volume, the mic and the ⏻ (one door).

The bottom bar has a 🔊 (the agent's voice OUTPUT, the mic and the session stay on) and a ⏻ (the whole agent off: `power.js`,
whose server half is `nucleo/runstate.py`). He often talks from across the room, so both are reachable by voice.

THE DOOR IS THE BUTTON. Neither act is re-implemented here: the brain emits ONE `controls` event, scoped to the screen the turn
came from (`origin_dev`, V2-792 — `event-scope.js`), and that screen runs the very function its button runs
(`session.toggleBotMute` / `openSpeakerHere`, `power.setPower`): same server calls, same order, same audit, on the device
where he was heard — a phone session is switched off on the phone, not on the desktop he is away from.

Two lanes reach it: the action map (a known whole-utterance order, `nucleo/actionmap/executor.py`) and the model's `agent_controls`
tool (any other wording, any language). Which one runs is decided upstream — an exact seed or the model's call — never by a
word table over his sentence: a remark about the speaker matches no seed and the model has no order to obey, so nothing fires.

Every act names a TARGET STATE, never a toggle: «mute» on a muted speaker leaves it muted (`self-controls.js` reads the
button's state first). The volume is the agent's OWN voice on that screen (0-100, kept per device), never the device's
system volume, which a web page cannot set. `off` and `mic_off` are ONE-WAY: once done he cannot be heard, so there is
no voice way back — the way back is the button, and the act's line saying so is always spoken (`one_way`), before the
screen acts (it waits for the line to finish).
"""
from __future__ import annotations

import math
from enum import Enum


class Act(str, Enum):
    """The closed vocabulary of act ids (not words of a language: his words reach them through the model's call). `mute`/`unmute`
    = the 🔊 (reversible, the agent keeps listening); `off` = the ⏻; then his voice, the locked language, its face (presence)
    and the camera its face follows him with."""
    MUTE = "mute"
    UNMUTE = "unmute"
    OFF = "off"
    VOICE_MALE = "voice_male"
    VOICE_FEMALE = "voice_female"
    VOICE_LIST = "voice_list"
    VOICE_SETTINGS = "voice_settings"
    LANGUAGE = "language"
    # V2-928 — its face on the screen: shown, hidden, or the Presence settings opened for him to choose it.
    PRESENCE_ON = "presence_on"
    PRESENCE_OFF = "presence_off"
    PRESENCE_SETTINGS = "presence_settings"
    # V2-928 T10 — «look at me»: the camera that lets its face follow him, on that screen (its switch's own door).
    CAMERA_ON = "camera_on"
    CAMERA_OFF = "camera_off"
    # His voice's volume on that screen (up/down by one step, or a level 0-100) and the mic, closed by voice (one-way).
    VOLUME_UP = "volume_up"
    VOLUME_DOWN = "volume_down"
    VOLUME_SET = "volume_set"
    MIC_OFF = "mic_off"


ACTS: tuple[str, ...] = tuple(a.value for a in Act)

#: After these he cannot be heard (mic closed, agent off): no voice way back, so their line is always said.
ONE_WAY = frozenset({Act.OFF.value, Act.MIC_OFF.value})

#: The event kind the screens obey (`event-scope.js` scopes it to the origin screen; `sse.js` runs the button's door).
KIND = "controls"


def canon(act) -> str:
    """The act as one of `ACTS`, or '' when it is not one (the caller then does nothing)."""
    a = str(act or "").strip().lower()
    return a if a in ACTS else ""


def level(value) -> int | None:
    """A volume level as 0-100 (clamped), or None when there is no number. A number, not a word: «30 %», 30, "30"."""
    try:
        n = float(str(value).strip().rstrip("%").strip())
    except ValueError:
        n = math.nan                           # no number is an answer here («nothing to set»), not a failure
    return max(0, min(100, round(n))) if math.isfinite(n) else None


def apply(act, emit, *, src: str, said: str = "", value=None) -> bool:
    """Emit the control for the screen that heard him. True when an act was emitted; False for an unknown act, or a
    `volume_set` without a level (nothing to set: the caller falls through instead of claiming it)."""
    a = canon(act)
    n = level(value) if a == Act.VOLUME_SET.value else None
    if not a or (a == Act.VOLUME_SET.value and n is None):
        return False
    emit(KIND, a, text=(said or "")[:160], extra={"act": a, "src": src, "origin": src, **({"value": n} if n is not None else {})})
    return True


def one_way(act) -> bool:
    """True for an act after which he cannot be heard: its line names the button as the way back and is always said."""
    return canon(act) in ONE_WAY


def said(act, value=None) -> str:
    """The act's own line, said instead of «Done.»: a chooser opened, a refusal, the state it leaves (2026-11-14)."""
    from i18n import langs
    a = canon(act)
    line = str(langs.words(f"controls_said.{a}", default="") or "") if a else ""
    return line.replace("{n}", str(level(value) if level(value) is not None else "")) if line else ""

