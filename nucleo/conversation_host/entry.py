"""The funnel (V2-941, v3.1 §1.7, B5): every line of a switched session enters the manager here — four functions and
no decision of their own beyond the guards every entry shares.

  typed(text, dev)          a typed line (the voice holder's data channel, `/api/chat` from another screen, the text
                            channel): a `TypedSubmit` handed to the account's conversation, in its thread. It does not
                            wait behind a voice by the old typed lane: the inbox orders it, once
  typed_and_wait(text, …)   the same, and the request's close with what was shown — for the text channel, which
                            answers in one response
  (local_phrase and voice facts come with the voice: B8, B10)

The guards every entry shares, here once: a `LOG:` line is a note on the timeline, never a turn; with the engine
stopped (⏻) nothing enters. The line is handed over and the caller goes on: the conversation's thread answers.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import threading
import time
import uuid

_lock = threading.Lock()
_waits: dict[str, dict] = {}                 # client id → {iv, future, said, reads}
_queue: list = []                            # lines handed while the conversation was still opening, in order
_opener: dict = {"t": None, "rt": None}       # the thread that opens the conversation, and what it opened


def _listen(kind: str, label: str, p: dict) -> None:
    """The conversation's telemetry, in its thread: which intervention a line became, and when its request closed."""
    if kind == "conv_ear" and label == "typed":
        with _lock:
            w = _waits.get(str((p.get("cause") or {}).get("ref") or ""))
            if w is not None:
                w["iv"] = (p.get("refs") or {}).get("iv")
    elif kind == "conv_effect" and label in ("read", "refused"):
        req = (p.get("refs") or {}).get("req")
        with _lock:
            for w in _waits.values():
                if w.get("iv") and req == f"r_{w['iv']}":
                    w["reads"].append({"name": p.get("tool"), "args": p.get("args") or {}, "outcome": label})
    elif kind == "conv_close":
        req = (p.get("refs") or {}).get("req")
        with _lock:
            done = [w for w in _waits.values() if w.get("iv") and req == f"r_{w['iv']}"]
        for w in done:
            if not w["future"].done():
                w["future"].set_result(label)


def _said(request_id: str, text: str) -> None:
    with _lock:
        for w in _waits.values():
            if w.get("iv") and request_id == f"r_{w['iv']}":
                w["said"].append(text)


def runtime():
    """The account's conversation, opened if it is not yet. Opening can wait — its lease is a write on the shared
    database, under the lock other writers hold for seconds at times — so it never runs on a caller's loop: see
    `_hand`."""
    from nucleo.conversation_host import boot, sessions
    acct = boot.account()
    return sessions.get(acct) or sessions.open_(acct, "body", boot.make((_listen,), _said))


def reset() -> None:
    """Forget the conversation this process opened (the sandbox's reset): the next line opens a new one."""
    with _lock:
        _opener["rt"] = None
        _queue.clear()
        _waits.clear()


def _hand(fn) -> None:
    """Hand `fn(conversation)` over without waiting. The first time the conversation is opened by a thread of its own,
    and every line handed meanwhile waits in order behind the ones before it."""
    with _lock:
        rt = _opener["rt"]                       # never the account here: resolving it can wait on the database
        if rt is not None and rt.alive() and not _queue:
            rt.submit(fn)
            return
        _queue.append(fn)
        if _opener["t"] is not None and _opener["t"].is_alive():
            return
        _opener["t"] = threading.Thread(target=_open_and_drain, name="conversation-open", daemon=True)
        _opener["t"].start()


def _open_and_drain() -> None:
    rt = runtime()                               # here, off every caller's loop
    with _lock:
        _opener["rt"] = rt
    while True:
        with _lock:
            if not _queue:
                _opener["t"] = None
                return
            fn = _queue.pop(0)
        rt.submit(fn)


def _guards(text: str, dev: str) -> dict | None:
    from nucleo import runstate
    from nucleo.input import support_note
    if support_note.record(str(text or "")[:4000], dev):
        return {"ok": True, "note": True}
    if runstate.stopped():
        return {"ok": False, "reason": "stopped"}
    if not str(text or "").strip():
        return {"ok": False, "reason": "empty"}
    return None


def typed(text: str, dev: str = "", *, wait: bool = False, checked: bool = False) -> dict:
    """Hand a typed line over and return at once. The guards read the engine's state, which can wait on the shared
    database lock: unless the caller already `checked` them off its loop, they run on the conversation's side."""
    if not str(text or "").strip():
        return {"ok": False, "reason": "empty"}
    cid = f"c_{uuid.uuid4().hex[:12]}"
    if wait:
        with _lock:
            _waits[cid] = {"iv": None, "future": concurrent.futures.Future(), "said": [], "reads": []}
    from conversation.ear import signals as S
    sig = S.TypedSubmit(dev or "holder", cid, str(text).strip()[:4000], int(time.time() * 1000))

    def deliver(conv) -> None:
        stop = None if checked else _guards(text, dev)
        if stop is None:
            conv.hear(sig)
            return
        with _lock:
            w = _waits.get(cid)
        if w is not None and not w["future"].done():
            w["future"].set_result(stop.get("reason") or "note")

    _hand(deliver)
    return {"ok": True, "cid": cid}


def voice(sig) -> None:
    """A fact of the ear (a word, an end of turn, the watermark, an edge of his voice): handed over in order."""
    _hand(lambda c: c.hear(sig))


async def typed_and_wait(text: str, dev: str = "", *, timeout_s: float = 90.0) -> dict:
    """The text channel's shape (`ok`, `reply`, `tool_calls`: the reads its run made, with their arguments; `trace`:
    its flow) plus the reads the gateway refused and a `conv` block with the ids."""
    stop = await asyncio.to_thread(_guards, text, dev)      # off the loop: they can wait on the database lock
    if stop is not None:
        return stop
    got = typed(text, dev, wait=True, checked=True)
    if not got.get("cid"):
        return got
    with _lock:
        w = _waits[got["cid"]]
    try:
        label = await asyncio.wait_for(asyncio.wrap_future(w["future"]), timeout_s)
    except asyncio.TimeoutError:
        label = "no_close_yet"
    finally:
        with _lock:
            _waits.pop(got["cid"], None)
    return {"ok": label == "answered", "reply": " ".join(w["said"]), "channel": "conversation",
            "tool_calls": [r for r in w["reads"] if r["outcome"] == "read"],
            "refused_calls": [r for r in w["reads"] if r["outcome"] == "refused"],
            "trace": w.get("iv") or "", "conv": {"cid": got["cid"], "iv": w.get("iv"), "close": label}}
