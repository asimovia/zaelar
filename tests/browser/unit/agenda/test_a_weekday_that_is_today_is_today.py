"""V2-886 0c — a named weekday that is TODAY is today while its hour is still ahead (or none is said); otherwise the
next one. Measured 2026-11-11: «football game wednesday 12:00» said at 11:58 on a Wednesday was written a week later,
the agent said «Done» and he did not see it: the resolver and the prompt's day list both started at TOMORROW.

Disarm: `coming_offset` back to `delta or 7` → red."""
import time

import pytest

from widgets.agenda import when

WED = 2   # Monday = 0


@pytest.mark.parametrize("weekday,at,now,offset", [
    (WED, "12:00", "11:58", 0),      # the measured case: today, the hour still ahead
    (WED, "", "11:58", 0),           # no hour said: today
    (WED, "09:00", "11:58", 7),      # the hour already passed: next week's
    (WED + 1, "09:00", "11:58", 1),  # another weekday: the coming one
    (WED - 1, "", "11:58", 6),
])
def test_one_rule_for_a_named_weekday(weekday, at, now, offset):
    assert when.coming_offset(weekday, WED, at, now) == offset


@pytest.mark.parametrize("said", ["miércoles", "wednesday", "el miércoles por la tarde", "on Wednesday"])
def test_the_widget_resolver_reads_today_as_today(said, monkeypatch):
    wed_morning = time.struct_time((2026, 11, 11, 9, 0, 0, WED, 315, 0))
    real = time.localtime
    monkeypatch.setattr(time, "localtime", lambda *a: wed_morning if not a else real(*a))
    monkeypatch.setattr(when, "_today", lambda: "2026-11-11")
    assert when._resolve_date(said, at="20:00") == "2026-11-11"


def test_the_prompts_day_list_starts_today_and_marks_it():
    from nucleo.turn.prompt.live_state import live_state
    text = live_state()
    today = time.strftime("%Y-%m-%d")
    assert f"{today} (hoy)" in text and text.count(time.strftime("%A").lower() + " ") >= 2   # today and next week
