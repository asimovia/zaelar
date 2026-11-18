# mic_input.py — THE microphone switch (V2-654) and THE input door to the STT (V2-831 T-18).
#
# ONE server-side fact — is his microphone muted? — that everything acting on what it heard asks (session 85eec898:
# the icon moved, the audio did not, and he was transcribed for seven minutes). `frontend/app/services/mic.js`
# writes it, the ~4 s heartbeat re-asserts it. Muted is STICKY (the safe side of a dead client); boot is UNDECLARED
# and the input stays closed until the voice holder speaks for its mic (2026-11-18, below — a silent client is heard
# after a bounded grace, so a stale one still never leaves the agent deaf). NOT the attention mode: it is his own hand — consulted first,
# never lifted by a wake word, and lifting it changes no attention state.
#
# THE INPUT DOOR: a cloud STT bills every frame it is PUSHED (Deepgram: one report per 5 s), so closed states
# used to cost what an open mic did (12 usage reports a minute for silence). The one rule,
#     feeds_stt() = not muted  and  not parked  and  not stopped (⏻),
# is re-applied on every write to the session's audio INPUT, whose room input then drops frames before VAD and
# STT. A future closed state joins the conjunction, never a gate elsewhere; `blocks_turn` stays as the backstop;
# `parked` (the wake-word mode's TRANSPORT fact, `wakeword.js`) is never persisted and resets with each session.
from __future__ import annotations

import threading
import time

_mx = threading.Lock()
_state = {"muted": False, "at": 0.0, "source": ""}
_tap = {"parked": False}
_input = {"sink": None, "applied": None}   # the live session's `(enabled) -> None`; one voice holder at a time

# ── FAIL CLOSED UNTIL THE HOLDER HAS SPOKEN FOR ITS MIC (2026-11-18) ─────────────────────────────────────────────
# Measured on his engine (session af04be1f): the engine restarted, a screen reconnected, and the session's input
# opened the STT at the boot default (`muted=False`) before any screen had said what its switch was. A boot default
# is a guess about a person's microphone, and «open» is the guess that transcribes him. So the input stays CLOSED
# until the voice holder DECLARES its switch — on `POST /api/session/acquire`/`steal` (the lock carries it, before any
# room exists), `POST /api/mic` and every heartbeat. A change of holder undeclares: the new surface speaks for its own
# mic. A client that never declares (an old tab, a bare test participant) is heard after `UNDECLARED_GRACE_S` —
# three heartbeats, so any real screen has declared long before and only a silent one ever reaches the grace.
UNDECLARED_GRACE_S = 12.0
_decl = {"declared": False, "since": 0.0, "timer": None}


def is_muted() -> bool:
    """The one answer. Cheap enough for the hot path of every turn."""
    with _mx:
        return bool(_state["muted"])


def snapshot() -> dict:
    """The whole fact, for the API and the viewer — `muted`, when it last changed, who said so, and whether the
    holder has declared it at all since boot or since the voice changed hands."""
    with _mx:
        return {"muted": bool(_state["muted"]), "at": _state["at"], "source": _state["source"],
                "declared": bool(_decl["declared"])}


def _undeclared_locked(now: float | None = None) -> bool:
    """Caller holds `_mx`. True while nobody has spoken for the mic and the grace has not run out."""
    if _decl["declared"]:
        return False
    since = _decl["since"]
    now = time.time() if now is None else now
    return not since or (now - since) < UNDECLARED_GRACE_S


def _arm_grace_locked() -> None:
    """Caller holds `_mx`. Re-apply the input when the grace runs out, so a silent client is heard after it."""
    old = _decl["timer"]
    if old is not None:
        old.cancel()
    t = threading.Timer(UNDECLARED_GRACE_S + 0.05, apply_input)
    t.daemon = True
    _decl["timer"] = t
    t.start()


def _disarm_grace_locked() -> None:
    old = _decl["timer"]
    if old is not None:
        old.cancel()
    _decl["timer"] = None


def undeclare(*, reason: str = "holder_changed") -> None:
    """The voice changed hands: the switch it carried belonged to the previous surface. Closed until the new one
    speaks (or the grace runs out)."""
    with _mx:
        if not _decl["declared"] and _decl["since"]:
            return
        _decl["declared"], _decl["since"] = False, time.time()
        if _input["sink"] is not None:
            _arm_grace_locked()
    apply_input()


def set_muted(muted: bool, *, source: str = "frontend", now: float | None = None, dev: str = "") -> dict:
    """Write the fact. Idempotent BY DESIGN: the heartbeat re-asserts the same value every ~4s, so only a real
    CHANGE is worth an event — otherwise the timeline would carry 15 rows a minute saying nothing happened."""
    muted = bool(muted)
    now = time.time() if now is None else now
    with _mx:
        changed = muted != bool(_state["muted"])
        _state["muted"], _state["at"], _state["source"] = muted, now, (source or "")[:40]
        _decl["declared"] = True
        _disarm_grace_locked()
    if changed:
        _say("🎤⃠ micrófono CERRADO" if muted else "🎤 micrófono abierto",
             extra={"muted": muted, "src": source, **({"dev": dev} if dev else {})})
    apply_input()
    return {"ok": True, "muted": muted, "changed": changed}


def set_parked(parked: bool) -> None:
    """The browser parked (or unparked) its track for the wake word; applied at once, so the unpark of a spotted
    name opens the STT before the sentence behind it arrives."""
    with _mx:
        _tap["parked"] = bool(parked)
    apply_input()


def feeds_stt() -> bool:
    """THE input rule: may audio reach the speech recogniser right now? Every closed state answers no."""
    with _mx:
        if _state["muted"] or _tap["parked"] or _undeclared_locked():
            return False
    from nucleo import runstate
    return not runstate.stopped()


def hears() -> bool:
    """Audio is being PROCESSED now: a live voice session holds the input and the input feeds the recogniser."""
    with _mx:
        held = _input["sink"] is not None
    return held and feeds_stt()


def use_input(sink) -> None:
    """The voice session installs its input setter. It APPLIES at once (a session born with the mic closed feeds
    not one frame) and starts unparked."""
    with _mx:
        _input["sink"], _input["applied"], _tap["parked"] = sink, None, False
        if not _decl["declared"]:
            _decl["since"] = time.time()      # the grace counts from the moment there is an input to open
            _arm_grace_locked()
    apply_input()


def clear_input(sink) -> None:
    """Only OUR sink: when the voice moves, the next session registers before this one closes."""
    with _mx:
        if _input["sink"] is sink:
            _input["sink"], _input["applied"] = None, None


# ── a discarded turn leaves no words behind (2026-11-06) ────────────────────────────────────────────────────
# Measured on his engine: a line the gate judged ambient («So now open, uh, the messages.») was never committed by the
# speech engine — the tap parked before the end of turn — so it stayed in its transcript buffer and came back 15 s
# later, byte-identical, as a NEW turn behind the agent's own question. The gate consumed those words; the buffer
# must know. The session installs the clearer; every early exit of the gate calls `discard_pending_turn`.
_clearer = {"fn": None}


def use_turn_clearer(fn) -> None:
    """The voice session's «forget the uncommitted user turn» (`AgentSession.clear_user_turn`)."""
    with _mx:
        _clearer["fn"] = fn


def clear_turn_clearer(fn) -> None:
    with _mx:
        if _clearer["fn"] is fn:
            _clearer["fn"] = None


def discard_pending_turn() -> bool:
    """The words of a turn the gate did not take are forgotten by the speech engine too. True when a clearer ran."""
    with _mx:
        fn = _clearer["fn"]
    if fn is None:
        return False
    try:
        fn()
        return True
    except Exception as e:  # noqa: BLE001 — a buffer that could not be cleared never stops the gate
        from loguru import logger
        logger.debug(f"mic_input: the pending turn was not discarded ({e!r})")
        return False


def apply_input() -> bool | None:
    """Push `feeds_stt()` into the live input — only on a CHANGE, so the ~4 s beat never flaps the lever (and the
    beat is what carries a ⏻ stop made elsewhere to the input). Returns what is applied; None = no session."""
    with _mx:
        sink, applied = _input["sink"], _input["applied"]
    if sink is None:
        return None
    want = feeds_stt()
    if applied is want:
        return want
    with _mx:
        _input["applied"] = want
    try:
        sink(want)
    except Exception as e:  # noqa: BLE001 — never fatal on the hot path; forgetting it makes the next beat retry
        with _mx:
            _input["applied"] = None
        _say("⚠️ audio input lever failed", extra={"stt_input": want, "error": str(e)[:160]})
        return None
    with _mx:
        why = "" if want else ("undeclared" if _undeclared_locked() else "")
        lapsed = want and not _decl["declared"]
    extra = {"stt_input": want, **({"why": why} if why else {}), **({"why": "undeclared_grace"} if lapsed else {})}
    _say("👂 audio input OPEN (STT)" if want else "👂⃠ audio input CLOSED (no STT)", extra=extra)
    return want


# ── what was heard before the close is said (audit 2026-11-14, failures 13/15) ─────────────────────────────────
# Closing the input commits the words already heard (`agent_events.set_ear`); that ONE turn reaches the gate after the
# switch closed and is not swallowed. Audio after the close never reaches the STT, so nothing else can ride this.
#: The commit's own bound: the STT's final (4 s) after its flush, plus the turn's way to this gate.
CLOSE_COMMIT_S = 8.0
_closed_on = {"at": 0.0}


def note_ear(enabled: bool, now: float | None = None) -> None:
    """The lever APPLIED: a close opens the window of the turn its commit makes, an open ends it."""
    _closed_on["at"] = 0.0 if enabled else (time.time() if now is None else now)


def note_closed_on_words(now: float | None = None) -> None:
    note_ear(False, now)


def _heard_before_close(now: float | None = None) -> bool:
    """A LICENCE PER WINDOW, never a one-shot: every invocation of the model for that turn (preemptive drafts LiveKit
    discards, a second final) asks this gate, and each must pass while the input has stayed closed since that close and
    for `CLOSE_COMMIT_S` (audit of 072fc6da7, P1-B). Safe for the same reason as the commit: closed, nothing new
    reaches the STT."""
    at = _closed_on["at"]
    return bool(at) and 0.0 <= (time.time() if now is None else now) - at <= CLOSE_COMMIT_S


def undouble(text: str) -> str:
    """A slow ear's final appended to the interim the commit already promoted reads «X X»: the turn is X. Structural
    (the same words twice in a row), only for the turn the close committed."""
    words = str(text or "").split()
    half = len(words) // 2
    norm = [w.strip(".,;:!?¿¡«»\"'").casefold() for w in words]
    if half and len(words) % 2 == 0 and _heard_before_close() and norm[:half] == norm[half:]:
        return " ".join(words[:half])
    return text


def blocks_turn(text: str) -> bool:
    """The BACKSTOP: does the switch swallow this turn? True = no model, tool, widget, memory or errand. Asked
    BEFORE the attention gate (closed is not an opinion about who was addressed). The typed turn is the one
    exemption, consumed one-shot (`attention.consume_typed`) — the mic is closed IN ORDER to type. Firing at all
    means audio reached the STT with the switch closed, so the event carries the TEXT: it is the evidence."""
    from voice import attention
    if attention.consume_typed():
        return False
    from nucleo import runstate
    if not runstate.stopped() and (not is_muted() or _heard_before_close()):
        return False                          # ⏻ swallows even what was heard before it: a stop is a stop
    _say("🎤⃠ turno DESCARTADO — el micrófono está cerrado", text=(text or "")[:200], role="user",
         extra={"muted": True, "src": snapshot().get("source") or ""})
    return True


def reset(*, fresh_boot: bool = False) -> None:
    """Back to an open, DECLARED switch (what most tests start from). `fresh_boot=True` is the real boot default:
    nobody has spoken for the mic yet, so the input is closed. NOT a way to lift a mute."""
    with _mx:
        _state.update(muted=False, at=0.0, source="")
        _tap["parked"] = False
        _input.update(sink=None, applied=None)
        _disarm_grace_locked()
        _decl.update(declared=not fresh_boot, since=0.0)
    _closed_on["at"] = 0.0


def _say(label: str, *, role: str = "system", **kw) -> None:
    """Observability, never fatal: called from the turn's hot path and from route handlers."""
    try:
        from voice.observer import emit
        emit("mic", label, role=role, **kw)
    except Exception:  # noqa: BLE001
        pass
