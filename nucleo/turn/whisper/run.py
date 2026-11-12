"""The whisperer between two turns (V2-889 F2), in SHADOW: it computes and emits, and writes nothing else.

Fired off `turn.closed` (the end of `pipeline_close.close_the_turn`), on its own thread — never inside the turn, never
on the voice loop. Per closed turn, in order:

  1. `use`   — the previous slot judged against THIS turn as it began: would it have been read? `fresh` · `stale` (its
               thread moved: state or a mention not made by this turn) · `expired` (older than `TTL_S`) · `late` (it
               landed after this turn began, or never) · `empty`. That is the «landed before the next turn» number.
  2. `gate`  — the deterministic score (`gate.py`) over verdicts the turn already paid for; fired or why not
               (`vetoed` · `below` · `in_flight` · `unchanged` · `no_route` · `off`).
  3. `slot`  — when fired: ONE reasoning call (`chat_sync("whisperer")`, metered like every decision call), its
               latency, outcome, the typed slot (`slot.py`) and what it WOULD render (`render.py`, not wired).

One in flight; a refire only when the stale key `(fired_turn_id, thread, last_mention, row.state)` changed past its
turn id, or the last slot expired. Nothing here reaches a prompt, the memory, a task row, a brief or a reply.
"""
from __future__ import annotations

import contextvars
import json
import os
import threading
import time

from loguru import logger

from nucleo.turn.whisper import gate as _gate, render as _render, slot as _slot

KIND = "whisper"
TASK = "whisperer"
SHADOW, OFF = "shadow", "off"
MODES = (SHADOW, OFF)
ENV = "ZAELAR_WHISPER"
TTL_S = 90.0
#: The budget when the table row cannot be read: a reasoner's own (≥ reasoning + 400) — never a bare 900.
DEFAULT_BUDGET, DEFAULT_TIMEOUT_S = 3800, 45.0
MAX_TASKS = 4
#: How long the gate waits, on its own thread, for a brief that had not landed when the turn closed.
BRIEF_WAIT_S = 1.5

SYSTEM = (
    "You read a voice assistant's conversation BETWEEN two turns. You never speak to the operator and never act: you "
    "fill a typed slot the next turn may read. Read his last sentence, the assistant's reply, the classifier verdicts "
    "on his sentence and his open tasks. Return ONLY one JSON object with these fields, each empty or null when "
    "nothing applies: \"facts\": up to 3 {\"text\" (at most 140 characters), \"source\" one of his_words, our_reply, "
    "task, verdict} — data the next reply needs and that the material states, never invented; \"correction\": "
    "{\"heard\", \"meant\", \"confidence\" 0-1} only when a word was plausibly misheard by speech recognition and the "
    "material shows what he meant; \"missing\": up to 2 {\"slot\", \"why\"} — what his request still lacks to be done; "
    "\"task_certainty\": {\"thread_id\" (one of the task ids given), \"state\" clear|ambiguous|contradicted, \"why\" (at "
    "most 120 characters)} — whether it is clear which open task his words are for. No advice, no instructions, no "
    "wording for the reply.")

_LOCK = threading.Lock()
_S: dict = dict(in_flight=False, last=None, threads=[])     # a state record


def mode() -> str:
    """`ZAELAR_WHISPER`, else the row's `mode` (one string, or `{"local", "cloud"}`) for the deployment the budgets
    read, else shadow locally and off on a hosted deployment: a shadow call costs a model call and serves nobody yet."""
    env = (os.getenv(ENV) or "").strip().lower()
    if env in MODES:
        return env
    from nucleo.pulse import budgets
    where, m = budgets.deployment(), _row().get("mode")
    m = str((m.get(where) if isinstance(m, dict) else m) or "").strip().lower()
    return m if m in MODES else (OFF if where == "cloud" else SHADOW)


def _row() -> dict:
    try:
        from config import models as _models
        return _models.service(TASK)
    except Exception as e:  # noqa: BLE001 — no row: defaults, and `no_route` stops the call
        logger.debug(f"whisper: no `{TASK}` row — {e!r}")
        return {}


def _emit(event: str, label: str, extra: dict) -> None:
    try:
        from voice import observer
        observer.emit(KIND, label, role="system", extra={"cat": "flash", "event": event, **extra})
    except Exception as e:  # noqa: BLE001 — an event that cannot be emitted never changes a turn
        logger.debug(f"whisper: {event} not emitted — {e!r}")


def stale_key(turn_id: str, thread: dict | None) -> tuple:
    t = thread or {}
    return (str(turn_id or ""), str(t.get("id") or ""), int(t.get("last_mention_ts") or 0), str(t.get("state") or ""))


def on_turn_closed(payload: dict) -> threading.Thread | None:
    """`turn.closed` → the whisperer's own thread (with the turn's trace). None when off. Never raises, never waits."""
    try:
        if mode() == OFF:
            return None
        ctx = contextvars.copy_context()
        th = threading.Thread(target=ctx.run, args=(evaluate, dict(payload or {})), name="whisper", daemon=True)
        _S["threads"] = [t for t in _S["threads"] if t.is_alive()] + [th]
        th.start()
        return th
    except Exception as e:  # noqa: BLE001
        logger.debug(f"whisper: not started — {e!r}")
        return None


def wait(timeout: float = 5.0) -> bool:
    """For a test or a probe: wait for the whisper threads started so far. True when all ended."""
    end = time.monotonic() + timeout
    for th in list(_S["threads"]):
        th.join(max(0.0, end - time.monotonic()))
    return not any(t.is_alive() for t in _S["threads"])


def reset() -> None:
    wait(2.0)
    with _LOCK:
        _S.update(in_flight=False, last=None, threads=[])


def _known() -> list[dict]:
    try:
        from nucleo.turn import named_errand
        return named_errand.known()
    except Exception as e:  # noqa: BLE001 — no errands readable reads as none
        logger.debug(f"whisper: errands unreadable — {e!r}")
        return []


def _landed(handle) -> None:
    """A brief still flying at the close is waited for here, off the loop and outside the turn, at most `BRIEF_WAIT_S`."""
    ev = handle.get("event") if isinstance(handle, dict) else None
    if ev is not None and hasattr(ev, "wait"):
        ev.wait(BRIEF_WAIT_S)


def evaluate(payload: dict) -> dict:
    """One closed turn, synchronously: judge the last slot, gate this turn, maybe whisper. Returns the gate event."""
    now = time.time()
    tid = str(payload.get("turn_id") or "")
    threads = _known()
    judge_previous(payload, threads)
    _landed(payload.get("brief"))
    from nucleo.turn import thread_event
    verdicts = _gate.verdicts_of(payload.get("brief"))
    g = _gate.score(verdicts, threads, thread_event.of_trace(tid), str(payload.get("text") or ""))
    key = stale_key(tid, g.thread)
    with _LOCK:
        why_not = _why_not(g, key, now)
        if not why_not:
            _S["in_flight"] = True
            _S["last"] = {"key": key, "turn_id": tid, "fired_at": now, "made_at": None, "slot": None, "judged": False}
    ev = {"turn_id": tid, **g.as_dict(), "why_not": why_not, "mode": mode()}
    _emit("gate", f"🤫 whisper gate {g.score}" + (" — fired" if not why_not else f" — {why_not}"), ev)
    if not why_not:
        try:
            _whisper(payload, verdicts, g, key, threads)
        finally:
            with _LOCK:
                _S["in_flight"] = False
    return ev


def _why_not(g, key: tuple, now: float) -> str:
    if not g.fired:
        return "vetoed" if g.vetoed else "below"
    if _S["in_flight"]:
        return "in_flight"
    last = _S["last"]
    if last and key[1] and last["key"][1:] == key[1:] and now - last["fired_at"] < TTL_S:   # a thread that has not moved
        return "unchanged"
    from nucleo.memory_agent.processor import llm_routes
    return "" if TASK in llm_routes._DEFAULTS else "no_route"


def _material(payload: dict, verdicts: dict, g, threads: list[dict]) -> tuple[str, set[str]]:
    from nucleo.turn import named_errand as _ne
    open_ = [t for t in threads if str(t.get("state") or "") in _gate.OPEN_STATES]
    tasks = [{"id": str(t.get("id") or ""), "card": _ne.card_line(t)} for t in _ne.by_mention(open_, MAX_TASKS)]
    user = {"his_sentence": str(payload.get("text") or "")[:600], "our_reply": str(payload.get("reply") or "")[:400],
            "verdicts": dict(list(verdicts.items())[:16]), "tasks": tasks,
            "task_in_play": g.as_dict()["thread_id"], "why_read": list(g.reasons)}
    return json.dumps(user, ensure_ascii=False), {t["id"] for t in tasks if t["id"]}


def _whisper(payload: dict, verdicts: dict, g, key: tuple, threads: list[dict]) -> None:
    from nucleo.memory_agent.processor import llm
    row = _row()
    user, ids = _material(payload, verdicts, g, threads)
    t0 = time.monotonic()
    content, outcome = None, "ok"
    try:
        content = llm.chat_sync(TASK, SYSTEM, user, max_tokens=int(row.get("max_tokens") or DEFAULT_BUDGET),
                                temperature=0.2, timeout=float(row.get("timeout_s") or DEFAULT_TIMEOUT_S))
    except Exception as e:  # noqa: BLE001 — a failed call is no whisper, said in the event
        outcome = f"error:{type(e).__name__}"
    ms = round((time.monotonic() - t0) * 1000.0, 1)
    made = time.time()
    s = _slot.parse(content or "", turn_id=key[0], thread_id=key[1], made_at=made, thread_ids=ids) if content else None
    if outcome == "ok":
        outcome = "no_answer" if not content else ("unparseable" if s is None else ("empty" if s.empty() else "ok"))
    with _LOCK:
        last = _S["last"]
        if last and last["key"] == key:
            last.update(made_at=made if s is not None else None, slot=s)
    text = _render.render(s)
    _emit("slot", f"🤫 whisper slot — {outcome} in {ms:.0f} ms",
          {"turn_id": key[0], "thread_id": key[1], "outcome": outcome, "latency_ms": ms,
           "slot": s.as_dict() if s else None, "rendered": text, "rendered_chars": len(text), "usage": llm.last_usage()})


def judge_previous(payload: dict, threads: list[dict]) -> str:
    """Would the last slot have been read by THIS turn? Emits `use` once per slot; returns the verdict ("" = none)."""
    started = float(payload.get("started_at") or 0.0) or time.time()
    with _LOCK:
        last = _S["last"]
        if not last or last["judged"] or last["turn_id"] == str(payload.get("turn_id") or ""):
            return ""
        last["judged"] = True
        made, s, key = last["made_at"], last["slot"], last["key"]
    landed = made is not None and made <= started
    if not landed:
        verdict = "late"
    elif s is None or s.empty():
        verdict = "empty"
    elif started - last["fired_at"] > TTL_S:
        verdict = "expired"
    else:
        verdict = "fresh" if _still(key, threads, started) else "stale"
    _emit("use", f"🤫 whisper use — {verdict}",
          {"turn_id": key[0], "next_turn_id": str(payload.get("turn_id") or ""), "verdict": verdict,
           "landed_before_next_turn": landed, "age_s": round(started - last["fired_at"], 1),
           "would_render_chars": len(_render.render(s)) if landed else 0})
    return verdict


def _still(key: tuple, threads: list[dict], started: float) -> bool:
    """The slot's thread as THIS turn began: same state, and no mention since the slot but the one this turn made."""
    if not key[1]:
        return True
    t = next((x for x in threads if str(x.get("id") or "") == key[1]), None)
    if t is None:
        return False
    mention = int(t.get("last_mention_ts") or 0)
    return str(t.get("state") or "") == key[3] and (mention <= key[2] or mention >= int(started))
