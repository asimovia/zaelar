"""The guards in front of the ear (V2-941, v3.1 §1.7 and §1.6 bis, B10): speech they throw away never reaches the
conversation as his words — the ear gets a `Discard` with its reason (I4: the text and the reason are kept).

Judged at every close of one of his turns with words (the ear asks: `Ear.guard`, wired by the host's boot — the
provider's end, the cap, too long, a stall), over its words, in this order:
  · `mic_blocked` — his microphone is closed (or the engine stopped): closed is not an opinion (`mic_input`);
  · `echo` — his voice rose while one of our last lines sounded (or within `ECHO_AFTER_S` of its end) AND his words are,
    in order, words of that line (`voice.echo_text`) — never the similarity of a whole line, and never after a question
    of ours ended (his answer may repeat it: «¿A Rowan?» «A Rowan.»);
  · `not_addressed` — the attention mode says it was not said to us (`attention.evaluate`, pure; a directed turn keeps
    the conversation's window warm, an ambient one is noted).
The voice lock needs no guard here: the voice process hears only the room of the session that holds the voice.
"""
from __future__ import annotations

import time

#: our last lines on the voice, newest last: [text, start, end] (end None while it sounds)
_lines: list = []
KEEP = 3
#: an echo still arrives this long after our line ended (the room and the provider's lag)
ECHO_AFTER_S = 2.0


def said(text: str, at: float | None = None) -> None:
    """Our line starts on the voice (`voice_mouth`): what the echo guard compares his words against."""
    _lines.append([str(text or ""), time.time() if at is None else at, None])
    del _lines[:-KEEP]


def ended(at: float | None = None) -> None:
    """Our line in course ended (played, cut or lost): the echo window counts from here."""
    for line in reversed(_lines):
        if line[2] is None:
            line[2] = time.time() if at is None else at
            return


def _echo(text: str, rose: float) -> bool:
    from voice import echo_text
    for line, start, end in reversed(_lines):
        if rose < start or (end is not None and rose > end + ECHO_AFTER_S):
            continue
        if end is not None and rose > end and line.rstrip().endswith("?"):
            continue                        # his answer to our question may repeat it: never an echo
        if text.rstrip().endswith("?") and not line.rstrip().endswith("?"):
            continue                        # a question back on our statement («¿A las cinco?») is his, not its echo
        if echo_text.contained(text, line):
            return True
    return False


def orders_stop(text: str) -> bool:
    """Does his turn order a stop? The engine's own detector (`attention.is_shut_up`): the package reads no words."""
    return split_stop(text)[0]


#: where a sentence ends, as the provider and the keyboard write it
SENTENCE_END = ".!?…"


def split_stop(text: str) -> tuple[bool, str]:
    """His turn, sentence by sentence: is one of them a stop (the engine's whole-sentence detector), and what is the
    rest? «Cállate. ¿Qué tiempo hace?» is a stop AND a question: the stop a control, the question his words."""
    from voice import attention
    parts, cur = [], ""
    for ch in str(text or ""):
        cur += ch
        if ch in SENTENCE_END:
            parts.append(cur)
            cur = ""
    parts.append(cur)
    stops = [p for p in parts if p.strip() and attention.is_shut_up(p)]
    return bool(stops), "".join(p for p in parts if p not in stops).strip()


def judge(text: str, now: float | None = None, rose: float | None = None) -> str | None:
    """Why this turn of his is thrown away, or None when it goes to the conversation. `rose`: when his voice rose (his
    first word), the echo's timing."""
    from voice import attention, mic_input
    now = time.time() if now is None else now
    if mic_input.blocks_turn(text):
        return "mic_blocked"
    if _echo(text, now if rose is None else rose):
        return "echo"
    verdict = attention.evaluate(text, now=now)
    if not verdict.directed:
        attention.note_ambient(text, now=now)
        return "not_addressed"
    attention.note_directed(now=now)
    return None


def for_ear(endpoint: str, text: str):
    """The guards as the ear asks them, at every close with words (`Ear.guard`): his turn's rise is the one the voice
    process reported for that device (`ear_in.rose_of`). A turn that holds a stop AND more is judged by the rest, and
    the entry is that rest — the stop was already his control (`ear_in`)."""
    from conversation.ear.arbiter import REPLACE
    from nucleo.conversation_host import ear_in
    from voice import attention
    rose = ear_in.rose_of(endpoint)
    stopped, rest = split_stop(text)
    if stopped and not rest:
        return "stop"
    why = judge(rest if stopped else text, rose=rose / 1000 if rose else None)
    if why is None and stopped:
        return (REPLACE, rest)
    if why is None and attention.has_wakeword(text):     # «para la música» set aside, then «Johnny»: his order whole
        tail = attention.reclaim_ambient_tail("")
        if tail:
            from conversation.ear.arbiter import RECLAIM
            return (RECLAIM, tail)
    return why

