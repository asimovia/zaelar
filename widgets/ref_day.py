"""widgets/ref_day.py — a reference that names its day keeps the day (agenda-everyday-edits EN, 2026-10-14).

The model names an existing row in `item` the way a person would: «Abril's piano lesson on 2026-10-20». The
resolver (`refs.resolve`) turns that into the row's id — for the agenda, its bare title — and the day went with
the rest of the words. On a series that is the difference between moving ONE day and moving every week: the
re-sent «move the 20th to the 21st» ran undated and moved the whole series to Wednesday (sandbox
20261014-121305-en, turn 12), which is what later left a day of it standing after «delete the whole series».

Narrow on purpose: one ISO day (and, the same way, one HH:MM hour into `currentTime`) in the reference, an action whose manifest declares `date`, and a payload that
carries no day of its own. The day only ever NARROWS which row is meant; it never widens anything.
"""
from __future__ import annotations

import re

_ISO = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_HOUR = re.compile(r"(?<![\d:])(\d{1,2}:\d{2})(?![\d:])")
#: The payload key a row's CURRENT hour travels in (`widgets/agenda/when.CURRENT_TIME`): two rows of one title on one
#: day are told apart by it, so a reference that names its hour keeps it the way it keeps its day.
CURRENT_TIME = "currentTime"


def _declares(widget_id: str, action: str, key: str) -> bool:
    from . import runtime
    spec = (((runtime.get(widget_id) or {}).get("actions") or {}).get(action) or {}).get("payload")
    return isinstance(spec, dict) and key in spec


def _declares_date(widget_id: str, action: str) -> bool:
    return _declares(widget_id, action, "date")


def carried(widget_id: str, action: str, ref: str, payload: dict) -> dict:
    """`payload` with the day `ref` names in `date`, when it names exactly one and nothing else gave a day."""
    payload = _hour_carried(widget_id, action, ref, payload)
    days = set(_ISO.findall(str(ref or "")))
    if len(days) != 1 or str(payload.get("date") or "").strip() or not _declares_date(widget_id, action):
        return payload
    return {**payload, "date": days.pop()}


def _hour_carried(widget_id: str, action: str, ref: str, payload: dict) -> dict:
    """`payload` with the ONE hour `ref` names in `currentTime`, when the action declares it and nothing set it."""
    hours = set(_HOUR.findall(str(ref or "")))
    if len(hours) != 1 or str(payload.get(CURRENT_TIME) or "").strip() or not _declares(widget_id, action, CURRENT_TIME):
        return payload
    return {**payload, CURRENT_TIME: hours.pop()}
