"""The guards in front of the ear (V2-941, v3.1 §1.7 and §1.6 bis, B10): speech they throw away never reaches the
conversation as his words — the ear gets a `Discard` with its reason (I4: the text and the reason are kept).

Judged at every close of one of his turns with words (the ear asks: `Ear.guard`, wired by the host's boot — the
provider's end, the cap, too long, a stall), over its words, in this order:
  · `mic_blocked` — his microphone is closed (or the engine stopped): closed is not an opinion (`mic_input`);
  · `echo` — his voice rose while one of our last lines sounded (or within `ECHO_AFTER_S` of its end) AND his words are,
    in order, words of that line (`voice.echo_text`) — never the similarity of a whole line, and never after a question
    of ours ended (his answer may repeat it: «¿A Rowan?» «A Rowan.»);
  · `voice_lock` — «stick to my voice» is on, a voice is enrolled, and every verdict the browser gave on this turn's
    segments says another voice (`voice.voice_lock`, the old turn's own rule, asked with no grace: the close comes
    after the segment);
  · `not_addressed` — the attention mode says it was not said to us (`attention.evaluate`, pure; a directed turn keeps
    the conversation's window warm, an ambient one is noted; a cold one let in says why the conversation began,
    `attention_opening.note`, as the old turn's gate does — only the old turn's prompt reads it today, the manager's
    does not).
A voice entry the conversation then closes with no reply (the model judged it not for us) gives back the window its
admission renewed (`listen`), as the old turn's line found not addressed does.
"""
from __future__ import annotations

import time

from nucleo.conversation_host.declared import declared

#: the manager's thresholds the guards read (`configure`, from the boot): the ambient tail a wake word takes back
_cfg: dict = {"reclaim_tail_ms": 3000}


def configure(cfg) -> None:
    _cfg["reclaim_tail_ms"] = int(getattr(cfg, "reclaim_tail_ms", _cfg["reclaim_tail_ms"]))


#: our last lines on the voice, newest last: [text, start, end, heard] (end None while it sounds; heard: what sounded)
_lines: list = []
KEEP = 3
#: an echo still arrives this long after our line ended (the room and the provider's lag)
ECHO_AFTER_S = 2.0


def said(text: str, at: float | None = None) -> None:
    """Our line starts on the voice (`voice_mouth`): what the echo guard compares his words against."""
    _lines.append([str(text or ""), time.time() if at is None else at, None, None])
    del _lines[:-KEEP]


def ended(at: float | None = None, heard: str | None = None) -> None:
    """Our line in course ended (played, cut or lost): the echo window counts from here, against what SOUNDED of it."""
    for line in reversed(_lines):
        if line[2] is None:
            line[2] = time.time() if at is None else at
            line[3] = heard
            return


def _echo(text: str, rose: float) -> bool:
    from voice import echo_text
    for line, start, end, heard in reversed(_lines):
        if rose < start or (end is not None and rose > end + ECHO_AFTER_S):
            continue
        if end is not None and rose > end:      # our line had ENDED: only its TAIL can still echo — the middle of a
            said = str(heard if heard is not None else line).split()   # finished line in his mouth is him quoting us
            line = " ".join(said[-(len(text.split()) + 2):])
        if end is not None and rose > end and line.rstrip().endswith("?"):
            continue                        # his answer to our question may repeat it: never an echo
        if text.rstrip().endswith("?") and not line.rstrip().endswith("?"):
            continue                        # a question back on our statement («¿A las cinco?») is his, not its echo
        if echo_text.contained(text, line):
            return True
    return False


def judge(text: str, now: float | None = None, rose: float | None = None) -> str | None:
    """Why this turn of his is thrown away, or None when it goes to the conversation. `rose`: when his voice rose (his
    first word), the echo's timing."""
    from voice import attention, mic_input
    now = time.time() if now is None else now
    if mic_input.blocks_turn(text):
        return "mic_blocked"
    if _echo(text, now if rose is None else rose):
        return "echo"
    from voice import voice_lock
    if not voice_lock.admit_now(onset=rose or 0.0, now=now)[0]:
        return "voice_lock"
    verdict = attention.evaluate(text, now=now)
    if not verdict.directed:
        attention.note_ambient(text, now=now)
        return "not_addressed"
    if verdict.reason != "active_window":           # a cold turn let in: the conversation starts here, and says why
        from voice import attention_opening
        attention_opening.note(verdict.reason, text)
    attention.note_directed(now=now)
    return None


def foreign_voice(endpoint: str, onset_ms: int) -> bool:
    """The manager asks whether an open voice holds our line (`Conversation.foreign_voice`, E6): it does not when the
    enrolled voice's verdicts judged it another person's. Only on the device whose browser sends those verdicts — the
    holder of the voice session; anywhere else, and with no verdict, the voice holds."""
    from nucleo.conversation_host import voice_session
    from voice import voice_lock
    return endpoint == voice_session.ENDPOINT and voice_lock.judged_other(onset_ms / 1000 if onset_ms else 0.0)


def vault(text: str):
    """THE vault gate, at the manager's one door for his words — every close of his voice (`for_ear`) and every typed
    line (`entry.typed`) — before they reach the store or the model: the one vault gate.
    Returns `(kept, shown)`: a security rule or a secret that IS the line is consumed — its line is owed to him, nothing
    enters (`kept` None) and only `shown` (redacted) may be kept of it; a secret inside a line goes on redacted.
    Anything else, as it is."""
    from nucleo import consequence
    from memory.vault import gate as vault_gate
    from voice import observer
    v = vault_gate.inspect_now(text, store=consequence.passes("vault.write"))
    if v.kind == "config":
        observer.emit("secret", "config", role="system", extra={"key": v.config[0], "value": v.config[1]})
    elif v.kind:
        observer.emit("secret", "no_vault" if v.kind == "need_vault" else "saved", role="system",
                      extra={"n": len(v.labels), "labels": v.labels})      # need_vault: the screen offers to create it
    if not v.consumed:
        return v.text, v.text
    if v.line:
        _owe(v.line)
    return None, v.text


def typed(sig):
    """A typed line at the same gate (`entry.typed`): the line that enters — redacted if a secret rode in it — or None
    when the gate consumed it."""
    import dataclasses
    kept, _shown = vault(sig.text)
    return None if kept is None else sig if kept == sig.text else dataclasses.replace(sig, text=kept)


def _owe(line: str) -> None:
    """The line a consumed secret or rule answers with, owed through the one ledger: the manager says it when free."""
    import asyncio
    from nucleo import dispatch
    from nucleo.pulse import notices
    loop = dispatch._LOOP
    if loop is not None and loop.is_running():
        asyncio.run_coroutine_threadsafe(notices.notify("zaelar", line, kind="vault"), loop)


def for_ear(endpoint: str, text: str):
    """The guards as the ear asks them, at every close with words (`Ear.guard`): his turn's rise is the one the voice
    process reported for that device (`ear_in.rose_of`). A stop in his words is not read here: the model chooses one."""
    from nucleo.conversation_host import ear_in
    from voice import attention
    rose = ear_in.rose_of(endpoint)
    why = judge(text, rose=rose / 1000 if rose else None)
    if why is None:                                       # his words, before they enter: the vault gate
        kept, shown = vault(text)
        if kept is None:                                  # consumed: thrown away, and never kept as he said it
            from conversation.ear.arbiter import DISCARD
            return (DISCARD, "vault", shown)
        if kept != text:
            from conversation.ear.arbiter import REPLACE
            return (REPLACE, kept)
    if why is None and attention.has_wakeword(text):     # «para la música» set aside, then «Johnny»: his order whole —
        at = rose / 1000 if rose else time.time()         # only what he said right before, in the same breath
        tail = attention.reclaim_ambient_tail("", now=at, within_s=_cfg["reclaim_tail_ms"] / 1000,
                                              since=attention.utterance_onset())
        if tail:
            from conversation.ear.arbiter import RECLAIM
            return (RECLAIM, tail)
    return why



#: the silent closes that are not the model's judgement on his words — our own failure (an empty reply, an order
#: written as text) or a door that took them (`routed`, `actionmap`): declared data
OURS = frozenset(declared()["own_silences"])


def listen(kind: str, label: str, p: dict) -> None:
    """The conversation's telemetry: a run over his VOICE that ended with no reply, judged by the model and not cut
    by his barge-in, gives back the window its entry renewed (`attention.retract_last_directed`: only if nothing
    re-anchored it since)."""
    if kind != "conv_run" or label != "ended" or p.get("outcome") != "no_reply":
        return
    if p.get("typed_only") or p.get("barge_cut") or p.get("reason") in OURS:
        return
    from voice import attention
    attention.retract_last_directed()
