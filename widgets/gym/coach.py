"""The gym app's ONE model seam (V2-900).

Every model call the app makes — the trainer's 5-day plan, a workout changed from a sentence, a workout logged from a
sentence, today's workout adjusted, an alternative beyond the app's own list — goes through `ask()`. The prompts are
data (`prompts.json`), generalised from the original app. An app has no model of its own: until the core gives apps a seam
(V2-902), `ask()` answers «not available» and every caller keeps its deterministic path working (the schedule's next
day instead of the plan, the static alternatives, the structured `log_workout` / `edit_session` payloads the agent
fills itself). Stdlib only; never raises.
"""
from __future__ import annotations

import json
from pathlib import Path

KINDS = ("plan", "edit_session", "log_workout", "adjust_today", "alternative")
UNAVAILABLE = {"ok": False, "error": "model_unavailable"}


def prompts() -> dict:
    try:
        return json.loads(Path(__file__).with_name("prompts.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — a missing file means no prompts, never a broken card
        return {}


def render(kind: str, fields: dict) -> dict | None:
    """The (system, user) pair for `kind` with its {placeholders} filled — what the seam will send."""
    p = prompts().get(kind)
    if not isinstance(p, dict):
        return None

    def fill(s: str) -> str:
        for k, v in fields.items():
            s = s.replace("{" + k + "}", v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
        return s

    return {"system": fill(p.get("system", "")), "user": fill(p.get("user", "")), "output": p.get("output", "")}


def available() -> bool:
    """Whether a model answers for this app. False until the core seam exists (V2-902)."""
    return False


def ask(kind: str, fields: dict) -> dict:
    """{"ok": True, "json": <parsed answer>} or {"ok": False, "error": ...}. Today always «model_unavailable»."""
    if kind not in KINDS:
        return {"ok": False, "error": "unknown_kind", "kind": kind}
    if not available():
        return dict(UNAVAILABLE)
    return dict(UNAVAILABLE)    # V2-902: send render(kind, fields) through the core's seam and parse its JSON here
