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
        refs = p.get("refs") or {}
        with _lock:
            done = [w for w in _waits.values() if w.get("iv") and refs.get("req") == f"r_{w['iv']}"]
        for w in done:
            if not w["future"].done():
                w["run"] = refs.get("run")              # the run that closed it: its line may come after the close
                w["future"].set_result(label)
    elif kind == "conv_run" and label == "ended":
        run = (p.get("refs") or {}).get("run")
        with _lock:
            for w in _waits.values():
                if run and w.get("run") == run and w.get("ended") is not None:
                    w["ended"].set()


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
        _opener["lost_told"] = False
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


#: the conversation may not open (its lease waits on the shared database lock): tried this many times, waiting longer
#: each time, an alert each; then every line waiting is handed to its own way back (`fallback`), never left queued
OPEN_TRIES, OPEN_BACKOFF_S = 3, 0.5
#: after the conversation failed to open while he spoke, new sessions take the old path for this long
BROKEN_S = 300.0


def broken() -> bool:
    """The conversation failed to open while he spoke, a moment ago: a new session goes the old way."""
    return time.time() < float(_opener.get("broken_until") or 0)


#: the close a typed line reports when the conversation never opened: its door answers it the old way
NOT_OPENED = "not_opened"


def _open():
    from voice import observer
    for attempt in range(OPEN_TRIES):
        try:
            return runtime()                     # here, off every caller's loop
        except Exception as e:  # noqa: BLE001 — said as an alert, tried again, and the lines never left waiting
            observer.emit("alert", "the conversation could not open", text=repr(e)[:200],
                          extra={"attempt": attempt + 1, "of": OPEN_TRIES})
            time.sleep(OPEN_BACKOFF_S * 2 ** attempt)
    return None


def _give_up() -> None:
    with _lock:
        queued, _queue[:] = list(_queue), []
        _opener["t"] = None
    done: set = set()
    for fn in queued:
        back = getattr(fn, "fallback", None)
        if back is not None and back not in done:   # one fallback once, however many lines carried it
            done.add(back)
            back()


def _open_and_drain() -> None:
    rt = _open()
    if rt is None:
        _give_up()
        return
    with _lock:
        _opener["rt"] = rt
        _opener["lost_told"] = False
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


def typed(text: str, dev: str = "", *, wait: bool = False, checked: bool = False, old=None) -> dict:
    """Hand a typed line over and return at once. The guards read the engine's state, which can wait on the shared
    database lock: unless the caller already `checked` them off its loop, they run on the conversation's side. `old`:
    how its door answers it the old way if the conversation never opens (a waiting caller gets `NOT_OPENED`)."""
    if not str(text or "").strip():
        return {"ok": False, "reason": "empty"}
    cid = f"c_{uuid.uuid4().hex[:12]}"
    if wait:
        with _lock:
            _waits[cid] = {"iv": None, "future": concurrent.futures.Future(), "said": [], "reads": [],
                           "ended": threading.Event()}
    from conversation.ear import signals as S
    sig = S.TypedSubmit(dev or "holder", cid, str(text).strip()[:4000], int(time.time() * 1000))

    def _end(label: str) -> None:
        with _lock:
            w = _waits.get(cid)
        if w is not None and not w["future"].done():
            w["future"].set_result(label)

    def deliver(conv) -> None:
        stop = None if checked else _guards(text, dev)
        if stop is None:
            from nucleo.conversation_host import controls, guards
            if guards.orders_stop(sig.text):           # a stop is his CONTROL, never a line for the model: the
                conv.give(controls.make(conv, "stop", sig.endpoint, "chat", sig.t_ms))   # next one is answered
                _end("stop")                           # on its own
                return
            conv.hear(sig)
            return
        _end(stop.get("reason") or "note")

    def fallback() -> None:                      # the conversation never opened: his line goes back to its door
        from voice import observer
        if old is None and not wait:             # nobody can take it the old way: said as it is, never «went»
            observer.emit("alert", "a typed line was not answered: the conversation could not open",
                          text=str(text)[:200])
            return
        observer.emit("alert", "a typed line went the old way: the conversation could not open", text=str(text)[:200])
        if old is not None:
            old()
        _end(NOT_OPENED)

    deliver.fallback = fallback
    _hand(deliver)
    return {"ok": True, "cid": cid}


def ack(sig) -> None:
    """An ack of our voice (a line started, ended, what sounded), from the voice's loop: handed over in order."""
    _hand(lambda c: c.ack(sig))


def count(counter: str) -> None:
    """One more on a proof counter of this account, counted on the conversation's side (the account can wait)."""
    from nucleo.conversation_host import proof
    _hand(lambda c: proof.note(c.account, counter))


def device(endpoint: str, **state) -> None:
    """A device's state for the conversation (its voice live, its speaker open), handed over in order."""
    _hand(lambda c: c.device(endpoint, **state))


def voice(sig) -> None:
    """A fact of the ear (a word, an end of turn, the watermark, an edge of his voice): handed over in order."""
    def deliver(c) -> None:
        c.hear(sig)
    deliver.fallback = voice_lost
    _hand(deliver)


def voice_lost() -> None:
    """The conversation never opened while he spoke: he is told, once — the language's «I lost that» through the one
    ledger of what is owed — the voice session goes the old way, and it is said as an alert."""
    from nucleo.conversation_host import switch
    from nucleo.conversation_host.words import PackWords
    from voice import remote_session
    with _lock:
        if _opener.get("lost_told"):             # once until a conversation opens again, however often it failed
            return
        _opener["lost_told"] = True
        _opener["broken_until"] = time.time() + BROKEN_S
    switch.fall_back(remote_session._M.get("session"), "the conversation could not open while he spoke")
    client = remote_session._M.get("client")
    if client is not None:                       # its voice process is in manual mode: the session ends, and the one
        client.post_soon("/voice/close", {"reason": "conversation_unavailable"})   # that reconnects is the old path's
    from nucleo.conversation_host import owed
    owed.set_voice_live(False)                   # before the notice: never claimed for a voice of ours that is ending
    line = PackWords().line("mute_lines")
    if line:
        from nucleo.pulse import notices
        try:
            asyncio.get_running_loop().create_task(notices.notify("zaelar", line, key=f"conv:lost:{int(time.time())}"))
        except RuntimeError:
            asyncio.run(notices.notify("zaelar", line, key=f"conv:lost:{int(time.time())}"))


async def _closed(w: dict, timeout_s: float) -> str:
    """How the line's request closed, once its answer is in `w["said"]`: a request the liveness closed while its run
    was still in course hears the line that run says when it stops — so the door waits for the run's end, inside its
    own deadline. `no_close_yet` past the deadline."""
    deadline = time.monotonic() + timeout_s
    try:
        label = await asyncio.wait_for(asyncio.wrap_future(w["future"]), timeout_s)
    except asyncio.TimeoutError:
        return "no_close_yet"
    if label != "answered" and w.get("run") and not w["said"]:
        await asyncio.to_thread(w["ended"].wait, max(0.0, deadline - time.monotonic()))
    return label


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
        label = await _closed(w, timeout_s)
    finally:
        with _lock:
            _waits.pop(got["cid"], None)
    return {"ok": label == "answered", "reply": " ".join(w["said"]), "channel": "conversation",
            "tool_calls": [r for r in w["reads"] if r["outcome"] == "read"],
            "refused_calls": [r for r in w["reads"] if r["outcome"] == "refused"],
            "trace": w.get("iv") or "", "conv": {"cid": got["cid"], "iv": w.get("iv"), "close": label}}
