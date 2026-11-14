"""V2-900 — the widget paints every screen of the real view data (onboarding, today, preview, calendar, muscles, my
gym, trainer, program, a summary, an exercise's history, the log, and the session in a timed block, a set, a rest,
with an alternative and at its end), in both languages, and says what it shows after every paint. ONE screen drives
the session: a desktop that did not start it never claims it, the phone app does; only the driving screen reads the
strap and beeps, and not with the agent stopped; a timer that runs out is reported once. The widget's half is the .mjs.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from widgets.gym import data as g


def _snap(label, out):
    out[label] = g.view_data()


def _views() -> dict:
    out = {}
    _snap("onboarding", out)
    g.apply_action("select_program", {"program": "functional-hypertrophy"})
    g.apply_action("log_workout", {"date": g._today(), "day_key": "legs", "exercises": [
        {"name": "Goblet squat", "sets": 3, "reps": 12, "weight_kg": 20}]})
    g.apply_action("configure", {"equipment": ["dumbbells"], "preferences": "no barbell", "age": 40})
    _snap("ready", out)
    g.apply_action("start_session", {"day": "push"})
    _snap("timed", out)
    db = g._load()
    db["live"]["timer"]["ends_at"] = int((time.time() - 2) * 1000)
    g._save(db)
    _snap("timed_expired", out)
    while g.view_data()["live"]["block"]["type"] != "exercise":
        g.apply_action("next", {})
    _snap("exercise", out)
    g.apply_action("suggest_alternative", {})
    _snap("alternative", out)
    g.apply_action("close_alternatives", {})
    g.apply_action("set_done", {})
    db = g._load()
    db["live"]["hr"] = {"bpm": 150, "at": time.time()}
    g._save(db)
    _snap("rest", out)
    db = g._load()
    db["live"]["i"] = len(db["live"]["blocks"])
    g._save(db)
    _snap("finished", out)
    return out


def test_the_card_paints_every_screen_and_drives_from_one_screen(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required")
    fixture = tmp_path / "views.json"
    fixture.write_text(json.dumps(_views()), encoding="utf-8")
    script = Path(__file__).with_name("test_the_card_paints_every_screen.mjs")
    r = subprocess.run([node, str(script), "screens", str(fixture)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
