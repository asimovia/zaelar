"""nucleo/acts/self_controls.py — the agent's OWN controls by voice: its speaker and its ⏻ (one door, every lane).

The bottom bar has a 🔊 (the agent's voice OUTPUT, the mic and the session stay on) and a ⏻ (the whole agent off:
`frontend/app/services/power.js`, whose server half is `nucleo/runstate.py`). He often talks from across the room, so
both have to be reachable by voice — the speaker when it bothers him, the ⏻ when he is done.

THE DOOR IS THE BUTTON. Neither act is re-implemented here: the brain emits ONE `controls` event, scoped to the screen
the turn came from (`origin_dev`, V2-792 — `frontend/app/services/event-scope.js`), and that screen runs the very
function its button runs (`session.toggleBotMute` / `session.openSpeakerHere` for the speaker, `power.setPower` for
the ⏻). So the voice and the press can never drift: same server calls, same order, same audit, on the device where he
was heard — a phone session is switched off on the phone, not on the desktop he is away from.

Two lanes reach it: the action map (a known whole-utterance order, `nucleo/actionmap/executor.py`) and the model's
`agent_controls` tool (any other wording, any language). Which one runs is decided upstream — an exact seed or the
model's call — never by a word table over his sentence: a remark about the speaker matches no seed and the model has
no order to obey, so nothing fires.
"""
from __future__ import annotations

#: The closed vocabulary. `mute`/`unmute` = the 🔊 (reversible, the agent keeps listening); `off` = the ⏻.
ACTS: tuple[str, ...] = ("mute", "unmute", "off")

#: The event kind the screens obey (`event-scope.js` scopes it to the origin screen; `sse.js` runs the button's door).
KIND = "controls"


def canon(act) -> str:
    """The act as one of `ACTS`, or '' when it is not one (the caller then does nothing)."""
    a = str(act or "").strip().lower()
    return a if a in ACTS else ""


def apply(act, emit, *, src: str, said: str = "") -> bool:
    """Emit the control for the screen that heard him. True when an act was emitted; False for an unknown act."""
    a = canon(act)
    if not a:
        return False
    emit(KIND, a, text=(said or "")[:160], extra={"act": a, "src": src, "origin": src})
    return True
