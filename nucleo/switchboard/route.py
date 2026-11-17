"""One decision per chunk he says: an open process takes it, or Flash does.

`take` runs at the turn's gate, after the ear closed the chunk and the attention judged it his, before the model. With
nothing open it costs nothing and decides nothing. With something open it asks ONE question — «is this for process N,
or for none?» — over the one board, and obeys the answer itself: the chunk is delivered to that process as he said it
(a waiting question gets it as its answer and the task resumes; a running worker gets it as his next words) and the
turn ends there. Every decision is one `thread` event with the board it read, who decided and how long it took.

Two things are decided without a model, by identity: a reply that IS one of the two declared answers of the only
question that waits (the screen's own buttons say exactly these), and a chunk already delivered (the ear hands a
sentence again when it grows: only what is new travels).
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

SYSTEM = (
    "You route what the operator of a voice assistant just said. Background processes of the assistant are OPEN, "
    "listed with a number: each one is carrying out a task for him, and some are WAITING for his answer to a question "
    "they asked. Decide whether what he just said is addressed to ONE of those processes: it answers its question (a "
    "yes, a no, a choice, a fact — in any wording or language, whole or cut short), confirms or refuses what it is "
    "about to do, adds a detail, corrects it, complains about how it did it, or asks it to go on, redo or cancel that "
    "task. Then answer its number.\n"
    "Answer 0 when it is for none of them: a different request (even on a similar subject), an order about the screen "
    "or an app (open, close, play, pause, show), a question he wants answered now (the time, the weather, which tasks "
    "exist or how one is going), small talk, or words meant for somebody else in the room.\n"
    "A bare yes, no or ok while a process WAITS on a question is that process's answer (with several waiting, the one "
    "that asked last). His words may arrive in pieces: a piece that continues what he was telling a process is that "
    "process's.\n"
    'Reply with JSON only: {"to": <number>, "why": "<a few words>"}'
)

_seen: dict = {"text": "", "key": "", "at": 0.0}


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


def ask_the_model(text: str, procs: list[dict], last_reply: str = "", before: list[str] | None = None) -> tuple[int, str]:
    """`(n, why)` — the number of the process the chunk is for (1-based), 0 for none. -1 when unreadable."""
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
        return -1, f"unreadable: {raw[:60]!r}"
    return (n, str(got.get("why") or "")[:80]) if 0 <= n <= len(procs) else (-1, f"out of range: {n}")


def _declared_answer(text: str, procs: list[dict]) -> dict | None:
    """The ONE waiting process, when his whole reply is one of its two declared answers; else None."""
    waiting = [p for p in procs if p["state"] == _board.WAITING]
    if len(waiting) != 1:
        return None
    try:
        from nucleo.circuit import asker
        from nucleo.request import consent_ask
        opts = asker.artefact(waiting[0]["key"]).get("options") or None
        return waiting[0] if consent_ask.declared_answer(text, opts) else None
    except Exception as e:  # noqa: BLE001
        logger.debug(f"switchboard: declared answers unread — {e!r}")
        return None


def deliver(p: dict, text: str) -> bool:
    """Hand `text` to process `p` as he said it: its open question takes it as the answer (the task resumes with it),
    a running worker takes it as his next words."""
    if p["state"] == _board.WAITING and p.get("ask_id"):
        from nucleo.cli import worker_api
        return bool(worker_api.answer_soon(p["ask_id"], text))
    if p.get("dispatch"):
        from nucleo import dispatch as _d
        _d.inject_soon(p["dispatch"], text)
        return True
    return False


def _event(emit, text: str, procs: list[dict], *, to: dict | None, by: str, why: str, ms: float, delivered=None) -> None:
    if emit is None:
        return
    try:
        label = (f"🔀 switchboard → process «{to['title'][:60]}» ({to['state']})" if to
                 else "🔀 switchboard → Flash (for no open process)")
        emit("thread", label, text=str(text)[:200], role="system",
             extra={"cat": "flash", "event": "switchboard", "to": (to or {}).get("key", ""),
                    "state": (to or {}).get("state", ""), "ask_id": (to or {}).get("ask_id", ""), "by": by,
                    "why": why, "ms": round(ms), "delivered": delivered,
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
    fresh, already = _fresh(said)
    if already and not fresh:                       # the same sentence handed again: it already went there
        to = next((p for p in procs if p["key"] == already), None)
        _event(emit, said, procs, to=to, by="seen", why="already delivered", ms=0.0, delivered=False)
        return to is not None
    to, by, why = _declared_answer(fresh, procs), "declared", "one of the question's two answers"
    if to is None and already:                      # what is new continues what that process already took
        to, by, why = next((p for p in procs if p["key"] == already), None), "continues", "the same sentence, growing"
    if to is None:
        last, before = _context(brain)
        try:
            n, why = await asyncio.wait_for(asyncio.to_thread(ask_the_model, fresh, procs, last, before), DECIDE_S)
            by = "model"
        except asyncio.TimeoutError:
            n, why, by = -1, f"no answer in {DECIDE_S}s", "timeout"
        except Exception as e:  # noqa: BLE001 — an unreadable decision is Flash's turn, said on the timeline
            n, why, by = -1, f"{type(e).__name__}: {e}"[:80], "error"
        to = procs[n - 1] if n and n > 0 else None
    ms = (time.monotonic() - t0) * 1000.0
    if to is None:
        _event(emit, said, procs, to=None, by=by, why=why, ms=ms)
        return False
    ok = False
    try:
        ok = deliver(to, fresh)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"switchboard: could not deliver to {to['key']} — {e!r}")
    _event(emit, said, procs, to=to, by=by, why=why, ms=ms, delivered=ok)
    if not ok:
        return False                                # nothing took it: Flash does, rather than his words vanishing
    _seen.update(text=_flat(said), key=to["key"], at=time.time())
    _acknowledge(said, brain, say, window_max)
    return True


def _acknowledge(said: str, brain, say, window_max: int) -> None:
    """One short line so he knows where his words went, and the exchange kept in the window."""
    try:
        from i18n import langs
        line = str(getattr(langs.current_language(), "answer_taken", "") or "")
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
