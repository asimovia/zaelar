"""nucleo/turn/thread_event.py — ONE event per thread decision (V2-878 §6).

Which errand a request belongs to was decided in four places and seen in one: `flow_of` emitted only its hit, the model
judge (`append.about_a_live_errand`) emitted nothing, and a turn that opened a NEW errand, that was only conversation or
that named several errands left no trace of the decision at all. «Why did this become a second errand?» had no answer
on the timeline, and «how often does the judge run out of time?» had no number.

Every such decision is now one event of kind `thread` (family `worker`, beside `flow`), written here and nowhere else:

  · `decided`      — the route of a request: `verb` (new · continue · correct · close · evict · pick_pending · undecided
                     · conversation · list), `as` (the route's own value, unchanged), `by` (containment · model ·
                     verdict · handed_back · none), the `menu` of open flows it was weighed against, `heard` (his words,
                     cut) and `window_had_commission` (a LIVE errand was open when he spoke).
  · `judged`       — the model judge's menu and its answer, with who asked (`caller`) and how long it took.
  · `judge_timeout`— the turn's budget ran out before the judge answered (the answer may still land later, `judged`).
  · `recall`       — the recall / recent-conversation shortcuts fired, and in which language.
  · `would_split`  — clauses of his sentence that carry words of their own and today ride with the errand before them
                     (measured, never acted on here).

Emit-only and fail-open: a decision that cannot be emitted never changes how a turn goes. `counts()` is the process's
tally of the same events, for a test or a status probe.
"""
from __future__ import annotations

import contextvars
from collections import Counter

from loguru import logger

KIND = "thread"
#: The verbs a decision can carry. `as` keeps the route's own value; the verb is its reading as a thread move.
NEW, CONTINUE, CORRECT, CLOSE, EVICT = "new", "continue", "correct", "close", "evict"
PICK_PENDING, UNDECIDED, CONVERSATION, LIST = "pick_pending", "undecided", "conversation", "list"
VERBS = (NEW, CONTINUE, CORRECT, CLOSE, EVICT, PICK_PENDING, UNDECIDED, CONVERSATION, LIST)
#: How each `flow_of.route()["as"]` reads as a thread move — the route's values are not changed, only named.
_VERB_OF = {"new": NEW, "conversation": CONVERSATION, "list": LIST, "undecided": UNDECIDED,
            "inject": CONTINUE, "absorb": CONTINUE, "reopen": CONTINUE, "join": CONTINUE,
            "steer": CORRECT, "replace": CORRECT, "stop": CLOSE}
HEARD_MAX = 80

#: Who is asking the model judge right now — set by the door that asks (`flow_of`), read inside the judge's thread
#: (a context variable crosses `asyncio.to_thread`). Unset = the dispatcher's own dedup.
_CALLER: contextvars.ContextVar[str] = contextvars.ContextVar("thread_judge_caller", default="dispatch")
_COUNTS: Counter = Counter()


def verb_of(route_as: str) -> str:
    return _VERB_OF.get(str(route_as or ""), str(route_as or ""))


def counts() -> dict:
    return dict(_COUNTS)


def reset() -> None:
    _COUNTS.clear()


def _send(event: str, label: str, text: str, extra: dict) -> dict | None:
    try:
        _COUNTS[event] += 1
        if extra.get("verb"):
            _COUNTS[f"{event}:{extra['verb']}"] += 1
        from voice import observer
        payload = {"cat": "worker", "event": event, **extra}
        observer.emit(KIND, label, text=str(text or "")[:200], role="system", extra=payload)
        return payload
    except Exception as e:  # noqa: BLE001 — evidence that cannot be emitted never changes how a turn goes
        logger.debug(f"thread_event: {event} not emitted — {type(e).__name__}: {e}")
        return None


def _menu(pool) -> list[str]:
    return [str((c or {}).get("id") or "") for c in pool or ()][:12]


def _live(pool) -> bool:
    """A LIVE errand was open when he spoke — one still running or starting, not one parked, ended or delivered."""
    return any(not (c or {}).get("parked") and not (c or {}).get("ended") and not (c or {}).get("delivered")
               for c in pool or ())


def decided(route: dict, pool=(), by: str = "") -> dict:
    """The route a request got (`flow_of.route`), as ONE `thread` event. Returns the route, unchanged."""
    r = route or {}
    flow = str(r.get("flow") or "")
    extra = {"verb": verb_of(r.get("as")), "as": str(r.get("as") or ""), "id": flow, "by": by or "none",
             "menu": _menu(pool), "heard": str(r.get("text") or r.get("words") or "")[:HEARD_MAX],
             "window_had_commission": _live(pool)}
    if r.get("as") == LIST:
        extra["parts"] = [{"id": str(p.get("flow") or ""), "verb": verb_of(p.get("as")),
                           "heard": str(p.get("words") or "")[:HEARD_MAX]} for p in (r.get("parts") or [])[:6]]
    _send("decided", f"🧵 thread: {extra['verb']}" + (f" → {flow}" if flow else ""), extra["heard"], extra)
    return route


def evicted(words: str, flow: str) -> dict | None:
    """A worker handed his words back: they leave that errand and never fold into it again."""
    extra = {"verb": EVICT, "as": "", "id": str(flow or ""), "by": "handed_back", "menu": [str(flow or "")],
             "heard": str(words or "")[:HEARD_MAX], "window_had_commission": True}
    return _send("decided", f"🧵 thread: evict ← {flow}", extra["heard"], extra)


class judging:
    """`with judging("flow_of"):` — names who asks the model judge for the calls made inside it."""

    def __init__(self, caller: str):
        self._caller, self._token = str(caller or "dispatch"), None

    def __enter__(self):
        self._token = _CALLER.set(self._caller)
        return self

    def __exit__(self, *exc):
        _CALLER.reset(self._token)
        return False


def judged(request: str, menu: list[tuple[str, str]], answer: str, *, ms: float, outcome: str) -> dict | None:
    """The model judge's menu and answer. `outcome`: about · separate · unreadable · error."""
    extra = {"caller": _CALLER.get(), "menu": [{"id": str(t), "goal": str(g or "")[:HEARD_MAX]} for t, g in menu[:12]],
             "answer": str(answer or ""), "outcome": str(outcome or ""), "ms": round(float(ms or 0.0), 1),
             "heard": str(request or "")[:HEARD_MAX]}
    return _send("judged", f"⚖️ thread judge: {outcome}" + (f" → {answer}" if answer else ""), extra["heard"], extra)


def judge_timeout(request: str, pool, *, budget_s: float, caller: str = "flow_of") -> dict | None:
    """The turn's budget for the judge ran out: the door treats the request as having no flow."""
    extra = {"caller": caller, "menu": _menu(pool), "budget_s": float(budget_s),
             "heard": str(request or "")[:HEARD_MAX], "window_had_commission": _live(pool)}
    return _send("judge_timeout", f"⏳ thread judge: no answer within {budget_s:g}s", extra["heard"], extra)


def recall_fired(text: str, *, recall: bool, recent: bool) -> dict | None:
    """The recall / recent-conversation shortcuts that fired this turn, and the turn's language. Nothing fired → nothing."""
    if not (recall or recent):
        return None
    try:
        from i18n import langs as _lg
        lang = _lg.current_code()
    except Exception:  # noqa: BLE001
        lang = ""
    extra = {"needs_recall": bool(recall), "needs_recent": bool(recent), "lang": lang,
             "heard": str(text or "")[:HEARD_MAX]}
    return _send("recall", "🔎 thread: recall fired" + (f" ({lang})" if lang else ""), extra["heard"], extra)


def would_split(text: str, pool) -> dict | None:
    """The clauses of his sentence that name no errand, carry content words of their own, and today ride with the errand
    named before them (`split_by_errand.parts`). Measured only: nothing is split here. None when there are none."""
    try:
        from nucleo import matching
        from nucleo.turn import named_errand as _ne, split_by_errand as _sbe
        riders = []
        for sentence in (s.strip() for s in _sbe._SENTENCE.split(str(text or "").replace("...", "…"))):
            if not sentence or not _ne.named(sentence, pool):
                continue
            last = None
            for clause in (c.strip() for c in _sbe._CLAUSE.split(sentence)):
                hits = _ne.named(clause, pool) if clause else []
                if hits:
                    last = hits[0] if len(hits) == 1 else None
                elif clause and last is not None and matching.content_words(clause):
                    riders.append({"rides_with": str(last.get("id") or ""), "clause": clause[:HEARD_MAX]})
    except Exception as e:  # noqa: BLE001
        logger.debug(f"thread_event: would_split unreadable — {type(e).__name__}: {e}")
        return None
    if not riders:
        return None
    extra = {"clauses": riders[:6], "menu": _menu(pool), "heard": str(text or "")[:HEARD_MAX]}
    return _send("would_split", f"✂️ thread: {len(riders)} clause(s) would stand alone", extra["heard"], extra)
