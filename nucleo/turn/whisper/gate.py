"""Does this turn deserve a whisper? A deterministic gate over what the turn ALREADY paid for (V2-889 F2).

No model, no word list: the gate reads the brief's verdicts (Jev's distribution over declared choices), the thread
decisions the turn emitted (`thread_event.of_trace`) and the open errands' cards (`named_errand.known`). Each signal
of doubt adds to a score; the whisper fires at `FIRE_AT`. A sure greeting, comment or answer with no thread in play
never fires — «pon una canción» costs nothing.

A verdict a door asks (`brief_doors`, e.g. `acts_asked` on the first model call) may land after the main brief or not
at all: whatever is not on the handle counts 0, never «unknown, so fire».
"""
from __future__ import annotations

from dataclasses import dataclass, field

#: The score at which the whisper fires.
FIRE_AT = 2
#: The kinds of sentence that never need a whisper when they are sure and no thread is in play.
QUIET_KINDS = ("greeting", "comment", "answer")
#: Card states (`named_errand._STATE` keys) that are open, and the ones that wait on him.
OPEN_STATES = ("running", "starting", "pending", "waiting")
WAITING_STATES = ("waiting",)
#: A live errand silent this long reads as stalled — the dispatcher's own `STUCK_SECS` when it can be read.
STALLED_S_DEFAULT = 180


@dataclass
class Gate:
    score: int = 0
    fired: bool = False
    reasons: list[str] = field(default_factory=list)
    vetoed: bool = False
    thread: dict | None = None

    def as_dict(self) -> dict:
        t = self.thread or {}
        return {"score": self.score, "fired": self.fired, "reasons": list(self.reasons), "vetoed": self.vetoed,
                "thread_id": str(t.get("id") or "")}


def _keys() -> dict:
    """The verdict keys the gate reads, from their owners (never re-spelled here)."""
    from nucleo.acts import errand as _errand
    from nucleo.cli import worker_api_bind as _bind
    from nucleo.flash import unclear_turn as _unclear
    from nucleo.turn import acts_asked as _acts, brief as _brief
    return {"request": _brief.REQUEST_KEY, "escalate": _brief.ESCALATE_KEY, "target": _errand.TARGET_KEY,
            "acts": _acts.KEY, "answers": _bind.KEY, "readable": _unclear.KEY,
            "garbled": _unclear.GARBLED, "several": _acts.SEVERAL}


def verdicts_of(handle) -> dict:
    """`{key: {choice, confidence}}` of a landed brief; {} when there is none, it is still flying or unreadable."""
    try:
        from nucleo import jev
        v = jev.peek(handle) if isinstance(handle, dict) else None
    except Exception:  # noqa: BLE001 — a handle without its event has no verdicts yet
        v = None
    out = {}
    for k, ans in (v or {}).items():
        if isinstance(ans, dict) and ans.get("choice"):
            try:
                out[str(k)] = {"choice": str(ans["choice"]), "confidence": float(ans.get("confidence") or 0.0)}
            except (TypeError, ValueError):
                out[str(k)] = {"choice": str(ans["choice"]), "confidence": 0.0}
    return out


def _sure(verdicts: dict, key: str, choice: str, floor: float) -> bool:
    a = verdicts.get(key) or {}
    return a.get("choice") == choice and float(a.get("confidence") or 0.0) >= floor


def _stalled_s() -> int:
    try:
        from nucleo.dispatch import thresholds as _t
        return int(_t.STUCK_SECS or STALLED_S_DEFAULT)
    except Exception:  # noqa: BLE001
        return STALLED_S_DEFAULT


def thread_in_play(verdicts: dict, threads: list[dict], decisions: list[str], text: str) -> dict | None:
    """The open errand this turn is about: the one his words name, else — when the brief says his words are for a
    running errand or the route continued, corrected or could not decide — the one he named last. None otherwise."""
    from nucleo.turn import named_errand as _ne
    from nucleo.turn import verdicts as _v
    open_ = [t for t in threads or () if str(t.get("state") or "") in OPEN_STATES]
    if not open_:
        return None
    try:
        hits = _ne.named(text, open_) if text else []
    except Exception:  # noqa: BLE001 — the tokenizer unreadable: fall back to the verdicts
        hits = []
    if hits:
        return hits[0]
    k = _keys()
    about = _sure(verdicts, k["target"], "running_errand", _v.LICENCE) or any(
        d in ("decided:continue", "decided:correct", "decided:undecided") for d in decisions)
    return _ne.by_mention(open_, 1)[0] if about else None


def score(verdicts: dict, threads: list[dict], decisions: list[str], text: str = "") -> Gate:
    """The gate for one closed turn. Pure over its inputs; never raises."""
    from nucleo.turn import verdicts as _v
    g = Gate()
    k = _keys()
    try:
        g.thread = thread_in_play(verdicts, threads, decisions, text)
    except Exception:  # noqa: BLE001 — no thread readable reads as no thread
        g.thread = None
    req = verdicts.get(k["request"]) or {}
    if not g.thread and req.get("choice") in QUIET_KINDS and float(req.get("confidence") or 0.0) >= _v.VETO:
        g.vetoed, g.reasons = True, [f"quiet:{req['choice']}"]
        return g
    for name in ("request", "escalate", "target", "acts", "answers"):
        conf = float((verdicts.get(k[name]) or {}).get("confidence") or 0.0)
        if (verdicts.get(k[name]) or {}).get("choice") and _v.LICENCE <= conf < _v.VETO:
            g.score += 1
            g.reasons.append(f"doubt:{k[name]}")
    if _sure(verdicts, k["readable"], k["garbled"], _v.LICENCE):
        g.score += 2
        g.reasons.append("garbled")
    if _sure(verdicts, k["request"], "complaint", _v.LICENCE):
        g.score += 2
        g.reasons.append("complaint")
    if _sure(verdicts, k["acts"], k["several"], _v.LICENCE):
        g.score += 1
        g.reasons.append("several_acts")
    if g.thread:
        g.score += 1
        g.reasons.append("open_thread")
        if str(g.thread.get("state") or "") in WAITING_STATES or g.thread.get("waiting_on"):
            g.score += 1
            g.reasons.append("waiting_thread")
        elif int(g.thread.get("silent_s") or 0) >= _stalled_s():
            g.score += 1
            g.reasons.append("stalled_thread")
    if "decided:undecided" in decisions:
        g.score += 2
        g.reasons.append("route_undecided")
    if "would_split" in decisions:
        g.score += 1
        g.reasons.append("would_split")
    g.fired = g.score >= FIRE_AT
    return g
