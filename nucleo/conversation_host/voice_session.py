"""A voice session of the conversation manager, as the body sees it (V2-941, v3.1 §1.7 and §1.9).

The voice process asks BEFORE it builds its session (`ask`): the switch's decision for this room, the session's own
flag first. It builds the manager's session only when the answer is yes AND its ear can hear turns; what it built is
what it reports in «session started», and that report is the session's decision on the body (`started`) — the body
and the voice never disagree on which path a session takes.

In a session of the manager: the voice is live for the owed lines (`owed.set_voice_live`) and the holder's device is
open to the conversation; the old turn's door answers nothing — an `llm_node` LiveKit opened anyway is counted
(`livekit_turns`), said as an alert, and given an empty turn (`refuse_turn`). The session's close takes it all back.
"""
from __future__ import annotations

#: the device the voice process hears for: the holder of the session (a typed line with no device is the same one)
ENDPOINT = "holder"


def ask(flag) -> dict:
    """The switch's decision for a session about to start (`flag`: the session's own `conv`, if it carries one)."""
    from nucleo.conversation_host import switch
    d = switch.decide(flag, voice=True)
    return {"on": d.on, "by": d.by, "why": d.why}


def started(session, ev: dict) -> bool:
    """The voice process's report of what it built is the session's decision. True: a session of the manager."""
    from nucleo.conversation_host import switch
    d = switch.Decision(bool(ev.get("conv")), str(ev.get("conv_by") or "voice"), str(ev.get("conv_why") or ""))
    session._conversation_switch = d
    if not d.on:                                       # it may not answer now: the reason on his screen, silence
        switch.silent(session, d.why or "the voice could not open the conversation's ear")
    if d.on:
        _voice(True)
    return d.on


def closed(session) -> None:
    d = getattr(session, "_conversation_switch", None)
    if d is not None and d.on:
        _voice(False)
        import threading
        from nucleo.conversation_host import controls
        threading.Thread(target=controls.retire_if_off, name="conversation-retire", daemon=True).start()


def _voice(live: bool) -> None:
    from nucleo.conversation_host import entry, owed
    owed.set_voice_live(live)
    entry.device(ENDPOINT, voice_live=live, speaker_open=live)


def refuse_turn(session) -> bool:
    """A LiveKit turn asked of the body: it answers nothing — the manager is the only path (counted and said)."""
    from nucleo.conversation_host import boot, proof
    from voice import observer
    proof.note(boot.account(), "livekit_turns")
    observer.emit("alert", "livekit opened a turn")
    return True
