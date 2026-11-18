"""One decision per chunk he says: an open process takes it, or Flash does.

`take` runs at the turn's gate, after the ear closed the chunk and the attention judged it his, before the model. With
nothing open it costs nothing and decides nothing. With something open it asks ONE question — «is this for process N,
or for none?» — over the one board, and obeys the answer itself: the chunk is delivered to that process as he said it
(a waiting question gets it as its answer and the task resumes; a running worker gets it as his next words) and the
turn ends there. Every decision is one `thread` event with the board it read, who decided and how long it took.

Two things are decided without a model, by identity: a reply that IS one of the two declared answers of the only
question that waits (the screen's own buttons say exactly these), and a chunk already delivered (the ear hands a
sentence again when it grows: only what is new travels).

The same decision says what KIND of reply it is to a process that waits on his yes: a plain yes or no decides the
retained act at once — exactly as the screen's button does, with no session resumed — and he hears ONE line
(«OK, sending it…», «OK, I won't send it»); a cut-off piece that says nothing yet is held and joined to what he says
next; an order to stop ends the process — or all of them — through the row's own cancel door, at once; anything else
(a change, a detail, a complaint) resumes the process with his words. What a decision does lives in `act.py`.
"""
from __future__ import annotations

import asyncio
import json
import re
import time

from loguru import logger

from nucleo.switchboard import board as _board

#: The decision's budget inside a turn. Past it Flash takes the chunk (and the event says so): a slow judge never
#: holds his words.
DECIDE_S = 3.0
#: How long a delivered chunk is remembered, to peel it off the same sentence handed again.
SEEN_S = 90.0
#: How long a cut-off piece waits for the rest of his sentence before it is forgotten.
PIECE_S = 20.0
from nucleo.switchboard.act import (FRAGMENT, NO, OTHER, STOP, STOP_ALL, YES, _line, deliver, early_yes,  # noqa: E402,F401
                                    line_key, line_of, stop, waits_on_his_yes)

SYSTEM = (
    "You route what the operator of a voice assistant just said. Background processes of the assistant are OPEN, "
    "listed with a number: each one is carrying out a task for him, and some are WAITING for his answer to a question "
    "they asked. Decide whether what he just said is addressed to ONE of those processes: it answers its question (a "
    "yes, a no, a choice, a fact — in any wording or language, whole or cut short), confirms or refuses what it is "
    "about to do, adds a detail, corrects it, complains about how it did it, or asks it to go on, redo or cancel that "
    "task. Then answer its number.\n"
    "Answer 0 when it is for none of them: a different request (even on a similar subject), an order about the screen "
    "or an app (open, close, play, pause, show), a question he wants answered now (the time, the weather, which tasks "
    "exist, or how a task is going or whether it is done — the assistant answers those itself), small talk, or words "
    "meant for somebody else in the room.\n"
    "A bare yes, no or ok while a process WAITS on a question is that process's answer (with several waiting, the one "
    "that asked last). His words may arrive in pieces: a piece that continues what he was telling a process is that "
    "process's.\n"
    "Also say what it IS for that process: \"yes\" — it plainly accepts or authorises what a WAITING process asked, "
    "with no change and no condition (yes, go ahead, send it, I authorise it); \"no\" — it plainly refuses or cancels "
    "it; \"fragment\" — a cut-off piece that carries no decision and no content yet (a word or two, a sentence that "
    "stops); \"stop\" — he orders that process to STOP: stop it, cancel it, drop it, do not do it, he never asked "
    "for it (add \"all\": true when he orders every process to stop); \"other\" — anything else: a change, a "
    "detail, a correction, a complaint, a question.\n"
    'Reply with JSON only: {"to": <number>, "is": "yes|no|stop|other|fragment", "why": "<a few words>"}'
)

_seen: dict = {"text": "", "key": "", "at": 0.0}
_piece: dict = {"text": "", "at": 0.0}


def _flat(text: str) -> str:
    return " ".join(re.findall(r"\w+", str(text or "").lower()))


def _fresh(text: str) -> tuple[str, str]:
    """`(what is new in this chunk, the process the rest already went to)`: the ear hands a growing sentence again, and
    what a process already received is not delivered twice. ("", key) when nothing is new."""
    said, was = _flat(text), _seen["text"]
    if not was or time.time() - float(_seen["at"]) > SEEN_S:
        return text, ""
    if said == was:
        return "", _seen["key"]
    if said.startswith(was + " "):
        return said[len(was):].strip(), _seen["key"]     # the words that are new, as heard
    return text, ""


def _context(brain) -> tuple[str, list[str]]:
    """Our last line and his last two — what a reply is a reply TO."""
    last, his = "", []
    try:
        last = str(getattr(brain, "_last_reply", "") or "")[:300]
        for m in reversed(list(getattr(brain, "_window", None) or [])[-8:]):
            if m.get("role") == "user" and len(his) < 2:
                his.append(str(m.get("content") or "")[:200])
    except Exception as e:  # noqa: BLE001
        logger.debug(f"switchboard: context unread — {e!r}")
    return last, list(reversed(his))


def ask_the_model(text: str, procs: list[dict], last_reply: str = "",
                  before: list[str] | None = None) -> tuple[int, str, str]:
    """`(n, why, is)` — the number of the process the chunk is for (1-based), 0 for none, -1 when unreadable; and what
    the chunk is for it (`yes` · `no` · `other` · `fragment`)."""
    menu = "\n".join(_board.line(i + 1, p) for i, p in enumerate(procs))
    user = f"OPEN PROCESSES:\n{menu}\n\n"
    if last_reply:
        user += f"THE ASSISTANT JUST SAID: «{last_reply}»\n"
    if before:
        user += "HE SAID BEFORE: " + " · ".join(f"«{b}»" for b in before) + "\n"
    user += f"HE NOW SAYS: «{str(text)[:600]}»"
    from nucleo.memory_agent.processor import llm
    raw = llm.chat_sync("switchboard", SYSTEM, user, max_tokens=60, temperature=0.0, timeout=DECIDE_S + 1.0) or ""
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        got = json.loads(m.group(0)) if m else {}
        n = int(got.get("to"))
    except Exception:  # noqa: BLE001
        return -1, f"unreadable: {raw[:60]!r}", OTHER
    kind = str(got.get("is") or OTHER).strip().lower()
    kind = kind if kind in (YES, NO, OTHER, FRAGMENT, STOP) else OTHER
    if kind == STOP and got.get("all") is True:
        kind, n = STOP_ALL, n or 1
    return (n, str(got.get("why") or "")[:80], kind) if 0 <= n <= len(procs) else (-1, f"out of range: {n}", OTHER)


def _declared_answer(text: str, procs: list[dict]) -> tuple[dict | None, str]:
    """`(the ONE waiting process, yes|no)` when his whole reply is one of its two declared answers; else (None, "")."""
    waiting = [p for p in procs if p["state"] == _board.WAITING]
    if len(waiting) != 1:
        return None, ""
    try:
        from nucleo.circuit import asker
        from nucleo.request import consent_ask
        opts = asker.artefact(waiting[0]["key"]).get("options") or None
        said = consent_ask.declared_answer(text, opts)
        return (waiting[0], said) if said else (None, "")
    except Exception as e:  # noqa: BLE001
        logger.debug(f"switchboard: declared answers unread — {e!r}")
        return None, ""


def _event(emit, text: str, procs: list[dict], *, to: dict | None, by: str, why: str, ms: float, delivered=None,
           kind: str = "") -> None:
    if emit is None:
        return
    try:
        label = (f"🔀 switchboard → process «{to['title'][:60]}» ({to['state']})" if to
                 else "🔀 switchboard → Flash (for no open process)")
        emit("thread", label, text=str(text)[:200], role="system",
             extra={"cat": "flash", "event": "switchboard", "to": (to or {}).get("key", ""),
                    "state": (to or {}).get("state", ""), "ask_id": (to or {}).get("ask_id", ""), "by": by,
                    "why": why, "ms": round(ms), "delivered": delivered, "is": kind,
                    "board": [_board.line(i + 1, p) for i, p in enumerate(procs)]})
    except Exception as e:  # noqa: BLE001 — the record never decides the route
        logger.debug(f"switchboard: event not emitted — {e!r}")


async def take(text: str, *, brain=None, emit=None, say=None, window_max: int = 0) -> bool:
    """Route one chunk. True: an open process took it and the turn ends here. False: Flash takes the turn."""
    said = " ".join(str(text or "").split())
    if not said:
        return False
    procs = _board.open_processes()
    if not procs:
        return False
    t0 = time.monotonic()
    if _piece["text"] and time.time() - float(_piece["at"]) <= PIECE_S:     # the piece he had started: one sentence
        said = f"{_piece['text']} {said}"
    _piece.update(text="", at=0.0)
    fresh, already = _fresh(said)
    if already and not fresh:                       # the same sentence handed again: it already went there
        to = next((p for p in procs if p["key"] == already), None)
        _event(emit, said, procs, to=to, by="seen", why="already delivered", ms=0.0, delivered=False)
        return to is not None
    (to, kind), by, why = _declared_answer(fresh, procs), "declared", "one of the question's two answers"
    if to is None and already:                      # what is new continues what that process already took
        to, by, why = next((p for p in procs if p["key"] == already), None), "continues", "the same sentence, growing"
    if to is None:
        last, before = _context(brain)
        try:
            n, why, kind = await asyncio.wait_for(asyncio.to_thread(ask_the_model, fresh, procs, last, before), DECIDE_S)
            by = "model"
        except asyncio.TimeoutError:
            n, why, by = -1, f"no answer in {DECIDE_S}s", "timeout"
        except Exception as e:  # noqa: BLE001 — an unreadable decision is Flash's turn, said on the timeline
            n, why, by = -1, f"{type(e).__name__}: {e}"[:80], "error"
        to = procs[n - 1] if n and n > 0 else None
    kind = kind or OTHER
    ms = (time.monotonic() - t0) * 1000.0
    if to is None:
        _event(emit, said, procs, to=None, by=by, why=why, ms=ms)
        return False
    if kind in (STOP, STOP_ALL):                    # his stop: the row's own cancel door, now — never words to relay
        ended = stop(procs if kind == STOP_ALL else [to])
        _event(emit, said, procs, to=to, by=by, why=why, ms=ms, delivered=bool(ended), kind=kind)
        if ended:
            _acknowledge(said, brain, say, window_max, await asyncio.to_thread(_line, "stopped_now", to["title"]))
        return bool(ended)
    if kind == FRAGMENT:                            # his, for that process, and nothing yet: wait for the rest
        _piece.update(text=fresh, at=time.time())
        _event(emit, said, procs, to=to, by=by, why=why, ms=ms, delivered=False, kind=kind)
        return True
    early = not waits_on_his_yes(to) and early_yes(to, kind)   # his go-ahead before the send's question exists
    kind = kind if waits_on_his_yes(to) else OTHER     # a yes or a no decides only what a process asked him
    key = "send_going" if early else line_key(to, kind)   # read BEFORE the answer clears what it held
    ok = False
    try:
        ok = deliver(to, fresh, kind)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"switchboard: could not deliver to {to['key']} — {e!r}")
    _event(emit, said, procs, to=to, by=by, why=why, ms=ms, delivered=ok, kind=kind)
    if not ok:
        return False                                # nothing took it: Flash does, rather than his words vanishing
    _seen.update(text=_flat(said), key=to["key"], at=time.time())
    _acknowledge(said, brain, say, window_max, await asyncio.to_thread(_line, key, to["title"]))   # worded, off the loop
    return True


async def at_the_gate(text: str, brain, emit, say, motor) -> bool:
    """`take` as the turn's gate calls it: a chunk a process took releases the turn's fresh trace (no turn follows)."""
    if not await take(text, brain=brain, emit=emit, say=say, window_max=motor._WINDOW_MAX):
        return False
    motor._release_acc_trace_if_fresh(brain)
    return True


def _acknowledge(said: str, brain, say, window_max: int, line: str) -> None:
    """One short line so he knows what his words did, and the exchange kept in the window."""
    try:
        if brain is not None:
            from nucleo.flash import dialog
            dialog.push_user(brain._window, said)
            if line:
                brain._window.append({"role": "assistant", "content": line})
                brain._last_spoken, brain._last_spoke_at = line, time.time()
            if window_max:
                dialog.live_slice(brain._window, window_max)
        if line and say is not None:
            say(line)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"switchboard: not acknowledged — {e!r}")
