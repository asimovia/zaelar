"""V2-900 — the plan a person runs is a VERSION: choosing a program writes v1 with its reason and a snapshot, choosing
the same program again keeps the progress, choosing another opens a new version; a session records the version it ran
on, and it runs on the SNAPSHOT — an update of the program file never changes a plan already in use.
"""
from __future__ import annotations

import copy

from widgets.gym import data as g
from widgets.gym import program as prog

KEY = "functional-hypertrophy"


def test_choosing_writes_v1_and_the_same_choice_keeps_the_progress():
    assert g.view_data()["status"] == "onboarding"
    assert g.apply_action("select_program", {"program": KEY})["version"] == 1
    g.apply_action("start_session", {})
    g.apply_action("finish", {})
    again = g.apply_action("select_program", {"program": KEY})
    assert again.get("preserved") and again["version"] == 1
    v = g.view_data()
    assert v["program"]["version"] == 1 and v["program"]["day_index"] == 1
    assert [x["reason"] for x in v["program"]["versions"]] == ["select"]
    assert v["sessions"][0]["version"] == 1


def test_another_program_opens_a_new_version(monkeypatch):
    other = copy.deepcopy(prog.programs()[KEY])
    other["key"] = "other-program"
    monkeypatch.setattr(prog, "programs", lambda: {KEY: prog._read(f"programs/{KEY}.json"), "other-program": other})
    g.apply_action("select_program", {"program": KEY})
    assert g.apply_action("select_program", {"program": "other-program", "reason": "new gym"})["version"] == 1
    assert g.apply_action("select_program", {"program": KEY})["version"] == 2
    assert [(x["program_key"], x["version"], x["reason"]) for x in g._load()["versions"]] == \
        [(KEY, 1, "select"), ("other-program", 1, "new gym"), (KEY, 2, "select")]


def test_a_session_runs_on_the_snapshot_not_on_the_live_file(monkeypatch):
    g.apply_action("select_program", {"program": KEY})
    changed = copy.deepcopy(prog.programs()[KEY])
    changed["days"]["push"]["blocks"] = [{"type": "exercise", "key": "pushups", "sets": 1, "reps": "5", "rest_sec": 30}]
    monkeypatch.setattr(prog, "programs", lambda: {KEY: changed})
    g.apply_action("start_session", {"day": "push"})
    lv = g.view_data()["live"]
    assert lv["total"] == 15 and lv["block"]["type"] == "stretch"


def test_an_unknown_program_or_day_teaches_the_retry():
    r = g.apply_action("select_program", {"program": "nope"})
    assert not r["ok"] and KEY in r["programs"]
    assert g.apply_action("start_session", {})["error"] == "no_program"
    g.apply_action("select_program", {"program": KEY})
    r = g.apply_action("start_session", {"day": "arms"})
    assert r["error"] == "unknown_day" and "legs" in r["days"]


def test_the_rotation_skips_days_done_and_a_plan_for_today_wins():
    g.apply_action("select_program", {"program": KEY})
    assert g.view_data()["next"]["day_key"] == "push"
    for day in ("push", "legs"):
        g.apply_action("start_session", {"day": day})
        g.apply_action("finish", {})
    assert g.view_data()["next"]["day_key"] == "back"
    db = g._load()
    db["plan"] = [{"date": g._today(), "type": "gym", "day_key": "upper-heavy", "reason": "x"}]
    g._save(db)
    n = g.view_data()["next"]
    assert (n["day_key"], n["source"]) == ("upper-heavy", "plan")


def test_the_phase_comes_from_complete_sessions():
    g.apply_action("select_program", {"program": KEY})
    assert g.view_data()["program"]["phase"]["rpe_target"] == 7
    db = g._load()
    db["sessions"] = [{"id": i, "status": "done", "day_key": "push", "started_at": 1_700_000_000 + i} for i in range(10)]
    g._save(db)
    assert g.view_data()["program"]["phase"]["rpe_target"] == 9
