"""The turn as a unit, as the old turn's readers count it (V2-941, plan v3.2 C16): a `trace` «turno» per entry of his,
a `flow end` when its request closes, a `trace` «merge» when it is absorbed.

The Master and the viewer count a turn by its root `trace` event (its title is his words, its initiator `user`), and
call it finished by its `flow end`; an absorbed turn is folded by its `merge` marker (`observability/flows.py`). The
manager's own events keep their intervention traces; this listener only adds the old turn's units on top of them:

  · an entry of his the inbox accepted (spoken or typed) opens a turn: `voice/trace.begin` — one per intervention;
  · an entry attached to a request already open is absorbed into that request's turn (`merge`);
  · a request's close ends its turn (`flow end`, `ok` unless it failed or stalled) — except the second and later
    requests one run answered together, which are absorbed into the first's (`merge`), never ended twice.

Our rows and the voice's `bot_speech` carry the turn's id (`corr`), so the Master never glues them to the nearest
flow by time.
"""
from __future__ import annotations

import threading

KEPT = 512
ENTRIES = frozenset({"user.utterance", "user.text"})
NOT_OK = frozenset({"failed", "stalled"})

_lock = threading.Lock()
_corr: dict[str, str] = {}            # intervention → its turn's trace id
_env_iv: dict[str, str] = {}          # envelope → its intervention (an attached entry is named by its envelope)
_run_first: dict[str, str] = {}       # run → the turn its first close ended


def _keep(d: dict, k: str, v: str) -> None:
    d[k] = v
    while len(d) > KEPT:
        d.pop(next(iter(d)))


def corr(iv: str, text: str = "") -> str:
    """The turn of intervention `iv`, opened now if it has none (`text`: his words, the turn's title)."""
    iv = str(iv or "")
    if not iv:
        return ""
    with _lock:
        tid = _corr.get(iv)
    if tid:
        return tid
    from voice import trace
    tid = trace.begin(text, origin="turno")
    with _lock:
        _keep(_corr, iv, tid)
    return tid


def known(iv: str) -> str:
    """The turn of `iv` if one was opened, else "" (a line owed by a notice has none)."""
    with _lock:
        return _corr.get(str(iv or ""), "")


def iv_of(req: str) -> str:
    req = str(req or "")
    return req[2:] if req.startswith("r_") else req


def listen(kind: str, label: str, p: dict) -> None:
    """The conversation's telemetry, in its thread."""
    refs = p.get("refs") or {}
    if kind == "conv_inbox" and label == "accepted" and p.get("kind") in ENTRIES and refs.get("iv"):
        with _lock:
            _keep(_env_iv, str(refs.get("env") or ""), str(refs["iv"]))
        corr(refs["iv"], str(p.get("text") or ""))
    elif kind == "conv_ledger" and label == "attached":
        with _lock:
            iv = _env_iv.get(str(p.get("ref") or ""), "")
        if iv and iv != iv_of(refs.get("req")):
            _merge(known(iv_of(refs.get("req"))), known(iv))
    elif kind == "conv_close":
        _closed(label, iv_of(refs.get("req")), str(refs.get("run") or ""))


def _closed(label: str, iv: str, run: str) -> None:
    tid = known(iv)
    if not tid:
        return
    with _lock:
        first = _run_first.get(run, "") if run else ""
        if run and not first:
            _keep(_run_first, run, tid)
    if first and first != tid:
        _merge(first, tid)                      # one run answered both: the later turn is folded into the first
        return
    if first == tid:
        return                                  # this turn already ended
    from voice import trace
    from voice.observer import emit
    ok = label not in NOT_OK
    with trace.scope(tid):
        emit("flow", "end", role="system", extra={"ok": ok, "reason": "turn_complete" if ok else label,
                                                  "closed": label})


def _merge(into: str, tid: str) -> None:
    if into and tid and into != tid:
        from voice import trace
        trace.merge(into, tid)


def _reset_for_tests() -> None:
    with _lock:
        _corr.clear()
        _env_iv.clear()
        _run_first.clear()
