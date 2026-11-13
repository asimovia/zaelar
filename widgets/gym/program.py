"""Programs, the exercise catalogue and the alternatives — read from the app's own JSON files (V2-900).

Ported from the original app's client (`_computeNext`, `_estimateDuration`, the phase from completed sessions,
`_defaultReps`, `previewMeta`). A text field of a program may be a plain string or `{"en": …, "es": …}`; `en()`
reads the English one (what the agent's prompt and the digest carry), the card picks its own language.
"""
from __future__ import annotations

import copy
import json
import re
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).parent
BLOCK_TYPES = ("stretch", "cardio", "transition", "exercise")
SET_SECONDS = 30            # the original app's approximation of one set, for the estimate


def _read(rel: str) -> dict:
    try:
        return json.loads((HERE / rel).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — a missing data file is an empty catalogue, never a broken card
        return {}


@lru_cache(maxsize=1)
def programs() -> dict:
    out = {}
    for p in sorted((HERE / "programs").glob("*.json")):
        d = _read(f"programs/{p.name}")
        if d.get("key") and isinstance(d.get("days"), dict):
            out[d["key"]] = d
    return out


@lru_cache(maxsize=1)
def exercises() -> dict:
    return _read("exercises.json").get("exercises") or {}


@lru_cache(maxsize=1)
def alternatives() -> dict:
    return _read("alternatives.json")


def en(v) -> str:
    if isinstance(v, dict):
        return str(v.get("en") or next(iter(v.values()), "") or "")
    return "" if v is None else str(v)


def exercise_name(key, fallback=None):
    """The catalogue's {en, es} name of `key`, else the fallback as given."""
    e = exercises().get(key or "")
    return e["name"] if e else fallback


def block_name(b: dict):
    if b.get("type") == "exercise":
        return b.get("name") or exercise_name(b.get("key"), b.get("key") or "")
    return b.get("name")


def catalogue() -> list[dict]:
    """The program cards of the onboarding screen."""
    return [{"key": k, "name": p.get("name"), "summary": p.get("summary"), "level": p.get("level"),
             "days_per_week": len(p.get("schedule") or [])} for k, p in programs().items()]


def default_reps(block: dict) -> int | None:
    m = re.search(r"(\d+)", en(block.get("reps")))
    return int(m.group(1)) if m else None


def estimate_minutes(blocks: list) -> int:
    s = 0
    for b in blocks or []:
        if b.get("duration_sec"):
            s += int(b["duration_sec"])
        elif b.get("type") == "exercise":
            sets = int(b.get("sets") or 1)
            rest = int(b.get("rest_sec") or 60)
            s += sets * SET_SECONDS + max(0, sets - 1) * rest
    return round(s / 60)


def phase_of(program: dict, done_count: int) -> dict | None:
    """The phase from how many sessions are complete: the first whose days are not used up, else the last."""
    phases = program.get("phases") or []
    if not phases:
        return None
    acc, phase = 0, phases[-1]
    for ph in phases:
        if ph.get("days") is None or done_count < acc + int(ph["days"]):
            phase = ph
            break
        acc += int(ph["days"])
    return phase


def next_day(program: dict, sessions: list, plan_today: dict | None) -> dict:
    """Which day of the program is today's. `sessions` newest first. The trainer's plan for today wins when it
    names a gym day; otherwise the classic rotation: the first schedule day not done in the last N sessions (N =
    days in the schedule), else the oldest of those, else the first."""
    schedule = program.get("schedule") or []
    days = program.get("days") or {}
    n = len(schedule)
    recent = [s.get("day_key") for s in sessions if s.get("status") in ("done", "partial")][:n]
    source = "schedule"
    if plan_today and plan_today.get("type") == "gym" and plan_today.get("day_key"):
        key, source = plan_today["day_key"], "plan"
    else:
        key = next((d for d in schedule if d not in recent), None) or (recent[-1] if recent else None) \
            or (schedule[0] if schedule else None)
    if key not in days:                                  # a plan may name a day the program does not have
        key, source = (schedule[0] if schedule else next(iter(days), None)), "schedule"
    return {"day_key": key, "source": source, "last": recent[0] if recent else None}


def day_blocks(program: dict, day_key: str) -> list:
    return copy.deepcopy(((program.get("days") or {}).get(day_key) or {}).get("blocks") or [])


def alternatives_for(block: dict) -> list:
    """The app's own substitutes for a block: the exercise's list, or the cardio list for a cardio/transition."""
    alts = alternatives()
    if block.get("type") == "exercise":
        return copy.deepcopy((alts.get("exercise") or {}).get(block.get("muscle_key") or block.get("key") or "") or [])
    if block.get("type") in ("cardio", "transition"):
        return copy.deepcopy(alts.get("cardio") or [])
    return []
