"""nucleo/workers/handoff.py — what the OPERATOR and the NEXT worker are told when a worker fails (V2-276).

Pure text builders over a `SessionRecord` (no I/O, no pool state), moved out of `session.py` and re-exported there.
Sisters on purpose: one incident (2026-08-18) showed an internal text delivered as-is lies both ways — to him
(«API Error: …context window limit.» read aloud) and to the next worker (its predecessor's error as a finding).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:                       # pragma: no cover — solo para el anotador
    from nucleo.workers.session import SessionRecord


#: How a provider (or the CLI relaying it) opens the message when the worker died of it — measured forms only.
_PROVIDER_OPENINGS = ("api error", "error", "request rejected", "there's an issue with the selected model",
                      "you've hit your", "usage limit", "rate limit", "insufficient", "invalid api key",
                      "unauthorized", "authentication", "401", "403", "429", "overloaded", "prompt is too long")


def operator_safe_summary(summary: str) -> str:
    """LAST GATE before a worker's summary is spoken and written to the chat wall (incident 2026-08-18).

    A raw provider error is NEVER a report. The operator asked for a guitar and got
    «API Error: The model has reached its context window limit.» — read aloud, in English, as if it were the answer.
    The 2026-08-10 quota incident closed this for its own error class by classifying it upstream; this closes it for
    the class as a WHOLE, so the next unforeseen provider message does not reach the operator either.

    It lives here, at the delivery point, ON PURPOSE: the specific paths (`provider_down`, `context_full`) each
    already replace the text with something readable, but they only cover the failures we anticipated. This one
    covers the rest, and it is a translation, never a silence — the operator always learns the task did not finish;
    what disappears is the internal wording. The full text stays in the log and in the record."""
    t = (summary or "").strip()
    if not t:
        return ""
    # V2-676 — the three sentences live in the LANGUAGE TABLE: Spanish literals here reached an English session,
    # in the function meant to stop wrong-language errors.
    from i18n import langs as _lg
    sp = _lg.current_language()
    # …but only a text that IS a provider message is classified: «$399.00 (list $429.00)» read as a 429 (demo pass
    # 2026-09-28). Errors open with their own wording; a report never does.
    if not t.lower().lstrip("⚠️ ").startswith(_PROVIDER_OPENINGS):
        return t
    try:
        from nucleo.workers import providers as _prov
        if _prov.is_context_overflow(t):
            return sp.worker_context_full
        if _prov.classify_failure(t):
            return sp.worker_provider_problem
    except Exception:
        pass
    # A bare «API Error…» with no classification is still not a report: it is the CLI talking to us, not to them.
    if t.lower().startswith("api error"):
        return sp.worker_failed
    return t


#: What the next WORKER is told rides here, never in the request: the request is his goal and is rendered (V2-877).
BRIEF_KEY = "worker_brief"


def with_worker_brief(prompt: str, context: dict | None) -> str:
    """The worker's prompt with the relay's brief in front of it — the ONE reader of `BRIEF_KEY` (V2-877)."""
    brief = str((context or {}).get(BRIEF_KEY) or "").strip()
    return f"{brief}\n\n{prompt}" if brief else prompt


def context_handoff(rec: "SessionRecord") -> str:
    """The brief a fresh worker inherits when the previous one ran out of context (incident 2026-08-18).

    WORKER-FACING: it rides in `context[BRIEF_KEY]` beside his ORIGINAL goal (V2-877 — sent as the request it became
    the goal, and «RETOMA esta tarea…» reached his chat). Instruction text for the model like every prompt, so English
    and NOT in i18n: he never sees it, and the goal it continues is his own words. Built only from the record (no LLM
    on the failure path), and never from `result_summary`, which here holds the raw provider error."""
    parts = ["RESUME this errand: the previous worker ran out of context before finishing it. The errand is the "
             f"request below; its words were: {rec.goal}"]
    if rec.plan:
        done = max(0, min(int(rec.done or 0), len(rec.plan)))
        parts.append("Its plan was: " + " · ".join(str(p) for p in rec.plan[:8])
                     + f" ({done} of {len(rec.plan)} steps done).")
    if rec.note:
        parts.append(f"The last thing it said: {str(rec.note)[:300]}")
    if rec.steps:
        seen: list[str] = []
        for s in rec.steps[-8:]:
            bit = " ".join(x for x in (str(s.get("action") or ""), str(s.get("target") or "")) if x).strip()
            if bit and bit not in seen:
                seen.append(bit)
        if seen:
            parts.append("Already looked at: " + " · ".join(seen)[:600] + ".")
    if int(rec.considered or -1) > 0:
        parts.append(f"It had reviewed {rec.considered} candidates and was keeping {max(0, int(rec.kept or 0))}.")
    parts.append("Do NOT repeat what was already looked at: continue from there and DELIVER as soon as you have "
                 "something presentable, even if partial. Be brief — the context is limited.")
    return "\n".join(parts)
