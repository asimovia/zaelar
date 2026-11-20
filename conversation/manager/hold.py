"""R3 (plan v3.2 §4): our voice never starts while his voice is open — ONE predicate before any line by voice.

Before a line starts by voice on a device — a reply, a fixed line, a line owed, the rest of a cut line — the ear is
asked whether an intervention of his is open there (`open_on`): one with no word yet counts; a noise is discarded by
the ear on its own within `close_cap_ms` and stops holding then. There is no time bound: the resume window and the
hold's bound no longer let a line out over his voice.

A reply that is READY while his voice is open is parked (`park`), never dropped and never made again; its requests
are not swept as stalled while it waits. What he says meanwhile is another batch, run with that reply in view
(`note`): a reply to it replaces the waiting one (`absorb`: its requests and its batch go out with the new answer); a
`no_reply` marks that chunk not his — it never enters a run again — and the waiting reply still stands.

Two ways out, neither over his voice: (a) everything closed on that device since the reply was ready was not his — a
guard's discard, the ear's `no_words`, a chunk the model closed with no reply — and `not_his_ms` passed with no chunk
of his waiting: it is said; (b) `monologue_max_ms` passed: it goes to the wall as text, never by voice.
"""
from __future__ import annotations

#: what the model of a later batch is told about the reply that waits (the prompt's own words)
NOTE = ("[a reply of yours waits to be said, ready for his {said} before these entries: «{text}» — a reply answers "
        "all of it and replaces it; no_reply if these entries are not his or add nothing]")


def open_on(conv, *endpoints: str | None) -> str | None:
    """An intervention of his open where a line would sound or where he spoke for it: on any of `endpoints`, or
    anywhere when one of them is no device with a live voice (the line goes to the voice that is live). Its id, or
    None."""
    anywhere = not endpoints or any(e is None or not getattr(conv.devices.get(e), "voice_live", False)
                                    for e in endpoints)
    return next((iv for iv, _onset, ep in conv.ear.open_interventions() if anywhere or ep in endpoints), None)


def devices_of(r) -> tuple:
    """Where a run's line would sound, and every device his entries in it came from."""
    return tuple(dict.fromkeys([r.ctx.endpoint] + [e.endpoint for e in r.ctx.batch.values() if e.is_user]))


def park(conv, r, batch, text: str, steps: int) -> None:
    """A ready reply waits for his voice to close, as the run in wait (`conv.waiting`). One waits at a time: a newer
    answer takes the older one's requests and batch with it."""
    from conversation.manager.run import _emit
    from conversation.types import MgrState
    absorb(conv, r)
    r.parked, r.waits_voice = (text, steps, batch, "voice"), True
    r.voice_parked_at = r.voice_parked_at or conv.clock.now_ms()
    conv.waiting = r
    if conv.current is r:
        conv.current = None
        if conv.state is MgrState.RUNNING:
            conv.state = MgrState.IDLE
    _emit(conv, "held", r, waits_for="voice_open")


def absorb(conv, r) -> None:
    """The run that answers now takes the waiting one's requests and batch: they are answered with it."""
    w = conv.waiting
    if w is None or w is r:
        return
    from conversation.manager.run import _emit
    _emit(conv, "command", r, command="absorbed", run_absorbed=w.run_id, batch_envs=list(w.batch_ids))
    r.before = w.before + _his(w)
    r.requests = tuple(dict.fromkeys(w.requests + r.requests))
    r.batch_ids = tuple(dict.fromkeys(w.batch_ids + r.batch_ids))
    r.voice_parked_at = w.voice_parked_at
    r.not_his = w.not_his
    conv.waiting = None


def not_his(conv, endpoint: str | None) -> None:
    """Something closed on the waiting reply's device and it was not his."""
    w = conv.waiting
    if w is not None and (endpoint is None or w.ctx.endpoint in (None, endpoint)):
        w.not_his += 1


def due(conv, now: int) -> str | None:
    """Why the waiting reply goes out now — `voice` (his voice closed), `not_his`, `wall` — or None while it waits."""
    w = conv.waiting
    if w is None or conv.current is not None:
        return None
    if not _open_requests(conv, w):             # the sweep closed them (he is owed the line): nothing to say
        conv.waiting = None
        return None
    if now - w.voice_parked_at >= conv.cfg.monologue_max_ms:
        return "wall"
    if w.publish_at is not None and now < w.publish_at:
        return None                             # its grace first, as any reply
    if conv.inbox.pending():
        return None                             # a chunk of his still to run: it runs first, with this reply in view
    if open_on(conv, *devices_of(w)) is None:
        return "voice"
    if now - w.voice_parked_at >= conv.cfg.not_his_ms and w.not_his:
        return "not_his"
    return None


def note(conv, r) -> str:
    """The line the model of a later batch reads about the reply that waits, or ""."""
    w = conv.waiting
    if w is None or w is r or not w.parked:
        return ""
    said = " ".join(f"«{t}»" for t in w.before + _his(w))
    return NOTE.format(said=said or "words", text=w.parked[0])


def _open_requests(conv, r) -> bool:
    mine = set(r.requests)
    return any(row["id"] in mine for _k, row in conv.store.view(conv.account).scan("items", ("open",)))


def _his(r) -> tuple:
    return tuple(t for t in (str(getattr(e.body, "text", "") or "").strip() for e in r.ctx.batch.values()
                             if e.is_user) if t)


async def publish_waiting(conv) -> None:
    """A reply that waited for his voice goes out when it is due (`hold.due`): his voice closed, everything since was
    not his, or the monologue's ceiling (to the wall)."""
    from conversation.manager.run import _Stalled, _Stop, _emit, _lost, _publish
    from conversation.types import MgrState
    why = due(conv, conv.clock.now_ms())
    if why is None:
        return
    r = conv.waiting
    text, steps, batch, _reason = r.parked
    conv.waiting, r.parked = None, None
    conv.current, conv.state = r, MgrState.RUNNING
    _emit(conv, "command", r, command="voice_wait_over", why=why)
    try:
        await _publish(conv, r, batch, text, steps, due=why)
    except _Stalled:
        await _lost(conv, r, "stalled")
    except _Stop as stop:
        r.said.append(("stopped", str(stop)))
    finally:
        if conv.current is r:
            conv.current = None
        if conv.state is MgrState.RUNNING:
            conv.state = MgrState.IDLE


# ── a reply waiting for its grace (the parked reply of a run in course) ─────────────────────────────────────────

def _unpark(conv) -> tuple:
    from conversation.types import MgrState
    r = conv.current
    parked, r.parked = r.parked, None
    conv.current = None
    if conv.state is MgrState.RUNNING:
        conv.state = MgrState.IDLE
    return r, parked


def drop_parked(conv) -> None:
    """A reply waiting for its grace meets an interrupt — his voice again, a new entry, a stop, the liveness: it takes
    effect as at any checkpoint, and the reply is never said."""
    from conversation.manager.run import _Stalled, _Stop, _checkpoint, _emit, _owe
    r = conv.current
    if r is None or r.parked is None or r.interrupt is None:
        return
    if r.interrupt == "resumed" and r.parked[0] is not None:     # a READY reply: it waits for his voice, never redone
        text, steps, batch, _reason = r.parked
        r.interrupt, r.resumed_iv = None, None
        park(conv, r, batch, text, steps)
        return
    r, _parked = _unpark(conv)
    try:
        _checkpoint(conv, r)
    except _Stalled:                            # here, off any await: the line is owed, never dropped
        _owe(conv, r, "stalled")
        conv.inbox.account(list(r.batch_ids), "failed", conv.clock.now_ms())
        _emit(conv, "ended", r, outcome="failed", reason="stalled", said=False)
    except _Stop as stop:
        r.said.append(("stopped", str(stop)))   # the checkpoint already accounted the batch and said why


async def publish_parked(conv) -> bool:
    """At the end of its grace a waiting reply is published. False while it still waits."""
    from conversation.manager.run import (_Stalled, _Stop, _hold, _listening, _lost, _publish, _resumed_voice,
                                          _silent)
    from conversation.types import MgrState
    r = conv.current
    if r is None or r.parked is None or conv.clock.now_ms() < r.publish_at:
        return r is None or r.parked is None
    r, (text, steps, batch, reason) = _unpark(conv)
    conv.current, conv.state = r, MgrState.RUNNING          # it publishes as the run in course
    try:
        if text is None:                                    # a silent close that waited its grace looks, as a reply
            waits = _resumed_voice(conv, r)                 # does right before sealing, for his voice open again
            if waits is not None:
                _hold(conv, r, *waits)
                raise _Stop()
            if not (r.reading is False and await _listening(conv, r, batch, steps)):
                _silent(conv, r, reason, conv.clock.now_ms())
        else:
            await _publish(conv, r, batch, text, steps)
    except _Stalled:
        await _lost(conv, r, "stalled")
    except _Stop as stop:
        r.said.append(("stopped", str(stop)))   # held right before sealing: the hold already said why
    finally:
        conv.current = None
        if conv.state is MgrState.RUNNING:
            conv.state = MgrState.IDLE
    return True
