"""voice/engine/pipeline/first_air.py — a reply that has not made a sound cannot be interrupted (V2-745).

## The session this comes from

Measured in the operator's own session `8fc3e1c9` (2026-09-21), a brand-new agent from power-on:

    +1.06 s  kickoff dispatched
    +4.04 s  reply generated («¡Hola! Soy Zaelar, tu asistente personal. ¿Cómo te llamas?») — the first
             model call of a session pays a cold handshake, TTFT 2.43 s
    +4.07 s  🎤 VAD on, `over_agent: false`   ← four seconds of silence, so he said «¿Qué pasa?»
    +4.62 s  TTSMetrics: 6.77 s of audio SYNTHESISED
    +4.63 s  bot_speech → IDLE, with no `speaking` edge anywhere before it

Six seconds of speech, generated and paid for, thrown away 30 ms after the text existed. His next two
turns were ruled ambient and the first thing he ever heard was a filler, at **+22 s**. In his words:
*«se pasará diez segundos hablando contra una pared y pensará que no [funciona]»*.

It happened again mid-conversation at +157 s: 14.05 s of audio synthesised for «Me alegra que lo veas
mejor…», never a `speaking` edge, and the sentence sat on his chat wall having never been said — the
complaint that V2-745's other half answers, on the client.

## The two rules, and why they are one object

**A barge-in is the operator cutting into something he is HEARING.** That is the whole meaning of the
gesture, and the engine already knows the difference: the VAD edge that killed the greeting carries
`over_agent: false`. So a speech handle parked here is uninterruptible until the first frame is actually
on air, and interruption is handed back the instant it is — cutting a greeting he is hearing keeps working
exactly as it did.

**The boot veil lifts when the agent can SPEAK, not when it has been BUILT.** It used to lift two phases
earlier, under a comment claiming «the greeting lands as the orb appears»; measured, the orb appeared at
+0.8 s and the greeting never came. A phase that ASSERTS warmth is not warmth. His rule: *«no deberíamos
dar acceso a la gente hasta que eso estuviera totalmente inicializado y operativo»*.

They live in one object because they are the same edge: the first audio frame both hands interruption back
and lifts the veil, and splitting them across two files is how one of them would stop firing.

## What keeps it safe

`lift()` is idempotent and can be called from anywhere, so every path that will NOT greet — a silent first
run, a duplicate job, a resumed session — lifts it at once. And the wait is BOUNDED: `arm_safety_net`
lifts it anyway after `READY_MAX_S`, because a stranded splash is worse than an early one, the same
direction the client's own 60 s net already chose. Nothing here raises: a barrier that throws is not a
barrier.
"""
from __future__ import annotations

import asyncio
import time

from loguru import logger

#: ONE KICKOFF PER ROOM (V2-047 F8, moved here from `agent.py` with V2-745's extraction — it is part of
#: "does this session greet at all", which is the same question the veil's early lift answers). A 2nd job
#: for the SAME room in a short window does not greet again (LiveKit double dispatch / rapid reconnect).
_KICKOFF_SEEN: dict = {}
_KICKOFF_WINDOW_S = 8.0


def kickoff_recent(room: str) -> bool:
    t = _KICKOFF_SEEN.get(room or "")
    return t is not None and (time.time() - t) < _KICKOFF_WINDOW_S


def mark_kickoff(room: str) -> None:
    now = time.time()
    _KICKOFF_SEEN[room or ""] = now
    for k in [k for k, v in _KICKOFF_SEEN.items() if now - v > 300]:   # prune old entries
        _KICKOFF_SEEN.pop(k, None)


#: FIRST-RUN LANGUAGE ONBOARDING (V2-101, INVERTED by V2-672): on a brand-new install NOTHING IS SAID.
#:
#: That branch used to greet and ask the question OUT LOUD, deliberately, «in English (the product
#: default)». The operator's rule, 2026-09-11: *«me pide los idiomas, pero por detrás está hablando ya en
#: un idioma por defecto… no quiero que la gente hable hasta que no hayamos seleccionado el idioma»*. Half
#: the people who see that screen do not speak the language it is spoken in, so the one utterance they
#: cannot understand is the one asking them which language they understand — and the modal that blocks the
#: UI already asks it, with flags, wordlessly. The session still STARTS (the mic has to be live to hear a
#: spoken answer); the first thing the operator ever hears is `onboarding.confirmSpoken`, in the language
#: he just chose, spoken by `i18n_api` after the lock — which is also the greeting.
def silent_first_run() -> bool:
    try:
        from i18n.init import detect as _d
        return bool(_d.should_detect())
    except Exception:                                 # noqa: BLE001 — unreadable state greets, never mutes
        return False


def _own_name() -> str:
    """The assistant-name slot (never a literal): what it is called right now."""
    try:
        from voice.attention import assistant_name
        return assistant_name() or "Zaelar"
    except Exception:                                 # noqa: BLE001 — an unreadable slot greets with the default
        return "Zaelar"


def greeting_prompt(lang) -> str:
    """The memory-aware FIRST-TURN instruction. V2-027: the verbose capabilities brief is NOT re-injected
    here — the per-turn system prompt already carries the state and the concise resources, and dumping it
    again bloated the most latency-sensitive turn of the session."""
    return (f"[The operator's selected interface language is {lang.native} — SPEAK {lang.name}.]\n"
            "I just connected. FIRST turn — SHORT and warm. CHECK YOUR MEMORY first: if you "
            "already know me (my name), greet me BY NAME and pick up naturally — do NOT ask my "
            "name again. If you do NOT know me yet, introduce yourself in one line and ask my name; and say, in "
            f"natural words, that for now your default name is {_own_name()} but I can give you any name I like, "
            "and that I can also give you a male or a female voice. "
            f"Reply in {lang.name}. Three sentences max. Then stop and wait for me.")


#: How long the veil may wait for a first audio frame before giving up on it. Generous against the cold
#: handshake measured above (~4.6 s from kickoff to synthesis) and short enough that a dead TTS costs a
#: pause rather than a dead screen.
def decide_kickoff(room: str, emit) -> str:
    """The FIRST TURN of a session: the instruction to greet, or "" when nothing must sound. One decision for the
    embedded session and for the voice's own process (which asks the body for it, V2-891). Marks the room and says why.

      · no language chosen yet → silent: the picker owns this screen (V2-765);
      · a TYPED LINE IS WAITING (operator, 2026-11-08) → that line is the session's first turn, and a greeting over
        it is the «good to have you» he got instead of an answer;
      · another job greeted this room seconds ago → skip (V2-047 F8: a quick reconnection or a double dispatch
        starts two jobs for the SAME room, and he heard the greeting twice);
      · he spoke recently (`ZAELAR_RESUME_WINDOW_S`, 30 min) → a RECONNECTION to a conversation in progress resumes
        in silence (2026-07-25: «I send it a message and it says ‘what do you need?’»);
      · otherwise greet — and, in the modes that PARK the microphone, the greeting opens the attention window it
        asks into (V2-749b, session 5789bad4: greeting at +4 s, the first thing heard at +33 s).
    """
    import os
    if silent_first_run():
        mark_kickoff(room)
        emit("brain", "🤐 kickoff en silencio — no hay idioma elegido todavía (el selector manda)", role="system")
        return ""
    from voice.engine.core import langs
    text = greeting_prompt(langs.current_language())
    resume_window = float(os.getenv("ZAELAR_RESUME_WINDOW_S", "1800"))
    try:
        from memory import api as _mem
        last_conv_age = _mem.seconds_since_last_conv()
    except Exception:                                 # noqa: BLE001
        last_conv_age = None
    from voice import screens as _screens
    if _screens.typed_waiting():
        mark_kickoff(room)
        emit("brain", "↩️ kickoff omitido — hay una línea escrita esperando, esa es el primer turno", role="system")
        return ""
    if kickoff_recent(room):
        emit("brain", "🚫 kickoff duplicado evitado (otra sesión ya saludó esta sala)", role="system")
        return ""
    if last_conv_age is not None and last_conv_age < resume_window:
        mark_kickoff(room)
        emit("brain", f"↩️ kickoff omitido — reconexión a sesión en curso (último turno hace {int(last_conv_age)}s), "
                      "retomando en silencio", role="system")
        return ""
    mark_kickoff(room)
    emit("brain", "kickoff (saludo memory-aware vía cerebro)", role="system")
    try:
        from voice import attention as _attn
        if _attn._has_wake_recovery():
            _attn.note_addressed_speech()
    except Exception:                                 # noqa: BLE001
        pass
    return text


READY_MAX_S = 12.0


class FirstAir:
    """The first audio frame of the session: it unlocks interruption and lifts the boot veil."""

    def __init__(self, ready, emit=None) -> None:
        self._ready = ready                 # the barrier to publish once (BootChannel.ready)
        self._emit = emit
        self._handle = None                 # the speech that may not be interrupted until it sounds
        self._on_air = None                 # what to run when it does
        self.lifted = False

    # ── the greeting ───────────────────────────────────────────────────────────────────────────────
    def park(self, handle, on_air=None) -> None:
        """Hold a speech handle that is not allowed to be interrupted until it has made a sound."""
        self._handle, self._on_air = handle, on_air

    def on_speaking(self) -> None:
        """The state machine saw `speaking`: there is audio. Hand interruption back and lift the veil."""
        handle, on_air = self._handle, self._on_air
        self._handle = self._on_air = None
        if handle is not None:
            try:
                handle.allow_interruptions = True     # he can cut it now: it is a sound, not a plan
            except Exception:                         # noqa: BLE001 — already interrupted, or an old handle
                logger.debug("first_air: could not re-enable interruptions", exc_info=True)
        if callable(on_air):
            try:
                on_air()
            except Exception:                         # noqa: BLE001 — never take the session down for this
                logger.debug("first_air: on_air callback failed", exc_info=True)

    # ── the boot veil ──────────────────────────────────────────────────────────────────────────────
    def lift(self) -> None:
        """Publish the READY barrier, once. Safe to call from every path, including the ones that
        will never greet — on those there is simply nothing to wait for."""
        if self.lifted:
            return
        self.lifted = True
        try:
            self._ready()
        except Exception:                             # noqa: BLE001
            logger.debug("first_air: ready() failed", exc_info=True)

    async def _net(self, seconds: float) -> None:
        try:
            await asyncio.sleep(seconds)
            if not self.lifted:
                if callable(self._emit):
                    self._emit("brain", f"⏱ velo de arranque levantado sin voz tras {seconds:.0f}s "
                                        "— el saludo no llegó a sonar", role="system")
                self.lift()
        except asyncio.CancelledError:                # the session is being torn down
            raise
        except Exception:                             # noqa: BLE001 — a net that throws is no net
            logger.debug("first_air: safety net failed", exc_info=True)
            self.lift()

    def arm_safety_net(self, seconds: float = READY_MAX_S):
        """Lift the veil anyway if no audio ever arrives. Returns the task, for the caller to hold."""
        task = asyncio.get_event_loop().create_task(self._net(seconds))
        task.add_done_callback(lambda t: t.cancelled() or t.exception())
        return task
