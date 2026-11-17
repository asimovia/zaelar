"""widgets/agenda/notice.py — the CONSEQUENCE bounds of a standalone notice (refactor2710-06 T-06).

The model fills the notice's slots when it asks for one; this module never reads his words. The slots:

  · `notice_at` — the absolute instant it rings, `YYYY-MM-DD HH:MM` or ISO 8601;
  · `before`    — or an ISO 8601 offset from the thing it announces (`-PT30M`, `-P1D`), which needs `commitment_at`;
  · `commitment_at` — when the thing itself happens (optional);
  · `commitment` — what it is, in his words (optional; it is what the notice says).

What it bounds, and only that:
  · a notice that would ring AFTER the thing it announces is not scheduled there (V2-167: «remind me on Wednesday»
    asked on a Wednesday landed six days after the Thursday deadline) — it is `asked`, never moved by a guess;
  · an instant already gone TODAY rings soon (`SOON_S`); a day already gone schedules nothing (`cannot`);
  · the job carries an instruction to NOTIFY, never his first-person sentence (V2-214: «I have to renew…» fired
    as «file this»).
No slot to place it → `asked`. Pure; `now` is injectable.
"""
from __future__ import annotations

import datetime as _dt

from loguru import logger

#: How soon a notice rings when the instant he gave already passed today.
SOON_S = 300
#: The head of the instruction a notice's job carries (the agent reads it when it fires).
_NOTIFY = "AVISA al operador"
_UNITS = {"D": 86400, "H": 3600, "M": 60, "S": 1}


def _instant(value) -> _dt.datetime | None:
    try:
        return _dt.datetime.fromisoformat(str(value or "").strip()).replace(tzinfo=None, second=0, microsecond=0)
    except ValueError:
        logger.debug(f"agenda.notice: {value!r} is not an instant")
        return None


def offset_s(value) -> int | None:
    """An ISO 8601 duration with an optional sign (`-PT30M`, `-P1DT2H`, `PT45S`) in seconds, or None."""
    s = str(value or "").strip().upper()
    sign = -1 if s.startswith("-") else 1
    s = s.lstrip("+-")
    if not s.startswith("P") or len(s) < 3:
        return None
    total, num, in_time = 0, "", False
    for ch in s[1:]:
        if ch == "T":
            in_time = True
        elif ch.isdigit():
            num += ch
        elif ch in _UNITS and num and (in_time or ch == "D"):
            total, num = total + int(num) * _UNITS[ch], ""
        else:
            return None
    return None if num else sign * total


def bound(payload: dict, now: _dt.datetime | None = None) -> dict:
    """`{"verdict", "at", "why"}` — `met` with the instant to schedule (`YYYY-MM-DD HH:MM`), `asked` when a slot it
    needs is missing or would ring after the thing, `cannot` when the day is already gone."""
    p = payload if isinstance(payload, dict) else {}
    now = now or _dt.datetime.now()
    thing = _instant(p.get("commitment_at"))
    at = _instant(p.get("notice_at"))
    if at is None and p.get("before"):
        off = offset_s(p.get("before"))
        if thing is None or off is None:
            return {"verdict": "asked", "at": "", "why": "an offset needs the moment of the thing it precedes"}
        at = thing + _dt.timedelta(seconds=off)
    if at is None:
        return {"verdict": "asked", "at": "", "why": "no moment to ring at"}
    if thing is not None and at >= thing:
        return {"verdict": "asked", "at": "", "why": "it would ring after the thing it announces"}
    if at <= now:
        if at.date() != now.date():
            return {"verdict": "cannot", "at": "", "why": "that day is already gone"}
        at = now + _dt.timedelta(seconds=SOON_S)
        if thing is not None and at >= thing:
            return {"verdict": "cannot", "at": "", "why": "the thing is about to happen"}
    return {"verdict": "met", "at": at.strftime("%Y-%m-%d %H:%M"), "why": ""}


def prompt_for(payload: dict) -> str:
    """What the job hands the agent when it fires: an instruction to NOTIFY, carrying what he asked to be told."""
    what = str((payload or {}).get("commitment") or "").strip()
    if not what or what.startswith(_NOTIFY):
        return what                                  # already our own instruction: never wrapped twice
    return f"{_NOTIFY}, es el recordatorio que te pidió: {what}"[:300]


def schedule(create, data: dict) -> tuple[dict, str]:
    """Put the model's notice on the scheduler through `create(prompt, when, name=, repeat=)`: `(result, verdict)`.
    A ONE-OFF instant (the slots, or a `schedule` that is an ISO instant) is bounded here and always tells the agent
    to NOTIFY; a cadence («every 30m», a cron line) is the model's own and goes as it is."""
    d = data if isinstance(data, dict) else {}
    when = str(d.get("schedule") or d.get("when") or "").strip()
    raw = str(d.get("prompt") or d.get("task") or "").strip()
    name = str(d.get("name") or "").strip()
    if not any(d.get(k) for k in ("notice_at", "before")) and _instant(when) is None:
        return create(raw, when, name=name, repeat=str(d.get("repeat") or "")), "started"
    slots = {"notice_at": when, **d} if when and not d.get("notice_at") else d
    b = bound(slots)
    if b["verdict"] != "met":
        return {"ok": False, "error": b["why"]}, b["verdict"]
    return create(prompt_for({"commitment": d.get("commitment") or raw}), b["at"], name=name), b["verdict"]


#: The hour a notice rings when its slots give a day and no hour — the card's own rule for an all-day item.
DAY_HOUR = "09:00"


def _hour_of(text: str) -> tuple[int, str, str] | None:
    """`(hour, minutes or "", "a"/"p"/"")` when the slot holds an HOUR and nothing else — `8`, `08:30`, `17h`, `17h30`,
    `8am`, `5 p.m.` — else None. A format, read by its shape: no word of any language."""
    s, mer = str(text or "").strip().lower(), ""
    for end in ("a.m.", "p.m.", "am", "pm"):
        if s.endswith(end):
            s, mer = s[: -len(end)].strip(), end[0]
            break
    for sep in (":", "h", "."):
        if sep in s:
            h, _sep, mm = s.partition(sep)
            break
    else:
        h, sep, mm = s, "", ""
    if not (h.isdigit() and len(h) <= 2 and int(h) <= 23) or (mm and not (mm.isdigit() and len(mm) == 2 and int(mm) <= 59)):
        return None
    return int(h), mm or ("00" if sep else ""), mer


def instant_of(day: str, hour: str, now: _dt.datetime | None = None) -> str:
    """`YYYY-MM-DD HH:MM` from a day slot and an hour slot, or "" — the door then ASKS. A slot that is not a day or
    not an hour is not read as one (the card's writers default an unread day to today: right for a draft he sees,
    wrong for a notice that rings unseen). A missing slot takes the card's own (today · `DAY_HOUR`) only while the
    instant that leaves is still AHEAD: «at 8» said at 15:00 names no day, and five minutes from now is not it."""
    if not (day or hour):
        return ""
    whole = _instant(day) if len(day) > 10 else None          # the day slot carrying the whole instant
    if whole is not None and not hour:
        return whole.strftime("%Y-%m-%d %H:%M")
    from . import when as _when
    hh = DAY_HOUR
    if hour:
        read = _hour_of(hour)
        if read is None:
            return ""
        h, mm, mer = read
        if not (mm or mer):
            hh = _when._resolve_time(str(h), DAY_HOUR)        # a bare number: the card's own rule for it
        else:
            hh = f"{(h % 12 + 12 if mer == 'p' else h % 12 if mer == 'a' else h):02d}:{mm or '00'}"
    d = _when._read_date(day, hh) if day else _when._today()
    at = _instant(f"{d} {hh}") if d else None
    if at is None or (not (day and hour) and at <= (now or _dt.datetime.now())):
        return ""
    return f"{d} {hh}"


def in_the_cards_shape(payload: dict, now: _dt.datetime | None = None) -> dict:
    """The notice's slots, read from the shape every other write of this card takes (`date` + `time`, `title`).

    Measured 2026-11-16: «Remind me tomorrow at 8am to water the plants» → `add_reminder {title, date, time}` — the
    slots `add_meeting` and `add_task` declare — and the door refused it for a missing `notice_at`. A day and an
    hour ARE the instant; a title IS what to tell him. Slots only: a payload with neither day nor hour still asks,
    and so does one whose day or hour is not one (`instant_of`)."""
    p = dict(payload) if isinstance(payload, dict) else {}
    if not (p.get("notice_at") or p.get("before")):
        at = instant_of(str(p.get("date") or p.get("day") or "").strip(),
                        str(p.get("time") or p.get("startTime") or p.get("at") or "").strip(), now)
        if at:
            p["notice_at"] = at
    if not str(p.get("commitment") or p.get("prompt") or "").strip():
        what = str(p.get("title") or p.get("text") or p.get("what") or "").strip()
        if what:
            p["commitment"] = what
    return p


def _a_add_reminder(action, payload, db, _extra) -> dict:
    """The agenda's `add_reminder`: a notice with no appointment, its moment in `notice_at` (or `before` +
    `commitment_at`, or the card's own `date` + `time`). No moment → `asked`, never guessed from words."""
    p = in_the_cards_shape(payload)
    if not (p.get("notice_at") or p.get("before")):
        return {"ok": False, "verdict": "asked", "say": "widgets.agenda.notice_when",     # the question is the card's
                "error": "no moment to ring at: give notice_at (or a date and a time that are a day and an hour)"}
    from nucleo.pulse import scheduler as _sched
    r, verdict = schedule(_sched.create, {**p, "prompt": p.get("commitment") or p.get("prompt") or ""})
    return {"ok": bool(r.get("ok")), "verdict": verdict, "display": r.get("display") or "",
            **({} if r.get("ok") else {"error": r.get("error") or "not scheduled"})}
