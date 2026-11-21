"""The manager's local acts reach the doors that already do them (node 13.127, INI-078 F2 step 1).

Which acts exist, their arguments and their door are declared data, their class derived from their declared act: a
local act is a write; one whose act were a leaving type of the event vocabulary would be held by the gateway. The
widget an act names is resolved against the CATALOGUE, so a widget nobody wrote code for is covered as soon as its
manifest is installed. The canvas acts cross `nucleo.acts.canvas.apply` with the reservation as their provenance
(`turn:<effect>`); the side panel is the `panel` event, on one of the tabs its schema declares. A close never goes with
an empty id (that closes every card): with nothing to name, it asks which. A message never crosses here.
"""
from __future__ import annotations

import pytest

from conversation.types import EffectClass
from nucleo.conversation_host import acts, tools_read

NEW = "w_new_widget"            # a widget installed with no code of ours: a manifest, nothing else


@pytest.fixture
def doors(monkeypatch):
    from nucleo import canvas_focus
    from nucleo.acts import canvas
    from nucleo.send import turn
    from server import voice_api
    from voice import observer
    from widgets import runtime
    seen: dict = {"canvas": [], "panel": [], "open": []}
    manifests = {NEW: {"id": NEW, "title": "w_title"}, "youtube": {"id": "youtube"}}
    monkeypatch.setattr(runtime, "get", lambda wid: manifests.get(str(wid)))
    monkeypatch.setattr(runtime, "catalog", lambda: list(manifests.values()))
    monkeypatch.setattr(runtime, "identify_named", lambda q, **kw: NEW if q == "w_title" else None)
    monkeypatch.setattr(runtime, "identify", lambda q, **kw: {"match": None, "ambiguous": False, "candidates": []})
    monkeypatch.setattr(voice_api, "open_instances", lambda: list(seen["open"]))
    monkeypatch.setattr(canvas_focus, "last_turn_card", lambda ids: "")
    monkeypatch.setattr(turn, "is_message", lambda wid, action, payload=None: False)
    monkeypatch.setattr(canvas, "apply", lambda op, wid="", *, src, **kw: seen["canvas"].append((op, wid, src, kw)) or True)
    monkeypatch.setattr(observer, "emit", lambda kind, label, **kw: seen["panel"].append((kind, label, kw["extra"])))
    return seen


def test_the_acts_are_declared_data_and_each_class_derived():
    cat = acts.catalog()
    assert [t.name for t in cat] == list(acts.ACTS) and cat
    assert all(t.about for t in cat)
    leaving = {t.name for t in cat if t.effect_class is EffectClass.LEAVES}      # a message to other people: held
    assert leaving == {"cluster_send", "a2a_send"} and all(
        t.effect_class is EffectClass.WRITE for t in cat if t.name not in leaving)
    assert tools_read.derive("messaging.send_new", False) is EffectClass.LEAVES     # a leaving act: held, never here
    reads = [t.name for t in tools_read.catalog()]
    assert [t.name for t in acts.HostTools().catalog()][:len(reads)] == reads


def test_a_widget_with_no_code_of_ours_opens_by_its_name_and_closes_by_its_card(doors):
    assert acts.run("show_widget", {"widget": "w_title"}, "x_1").status == "ok"
    doors["open"] = [f"{NEW}::c1"]
    assert acts.run("close_widget", {"widget": NEW}, "x_2").status == "ok"
    assert [(op, wid, src) for op, wid, src, _kw in doors["canvas"]] == [
        ("show", NEW, "turn:x_1"), ("close", f"{NEW}::c1", "turn:x_2")]   # its reservation is its provenance


def test_a_close_with_nothing_to_name_asks_and_never_closes_every_card(doors):
    doors["open"] = ["youtube", NEW]
    got = acts.run("close_widget", {}, "x_3")
    assert got.status == "failed" and got.data["reason"] == "which_one" and not doors["canvas"]
    missing = acts.run("show_widget", {"widget": "w_nothing"}, "x_4")
    assert missing.data["reason"] == "no_such_widget" and NEW in missing.data["widgets"] and not doors["canvas"]


def test_full_screen_off_leaves_whichever_covers_the_screen(doors, monkeypatch):
    from nucleo.acts import show_target
    monkeypatch.setattr(show_target, "at_full_screen", lambda: "youtube")
    assert acts.run("fullscreen_widget", {"mode": "off"}, "x_5").status == "ok"
    doors["open"] = ["youtube"]
    assert acts.run("fullscreen_widget", {"mode": "on", "widget": "youtube"}, "x_6").status == "ok"
    assert [(op, wid, kw.get("on")) for op, wid, _src, kw in doors["canvas"]] == [
        ("fullscreen", "youtube", False), ("fullscreen", "youtube", True)]


def test_the_side_panel_is_its_own_event_on_a_declared_tab(doors):
    assert acts.run("show_panel", {"panel": "procesos"}, "x_7").status == "ok"
    assert acts.run("show_panel", {"panel": "conectores", "connector": "telegram"}, "x_8").status == "ok"
    assert [(k, lab, x["tab"], x.get("connector")) for k, lab, x in doors["panel"]] == [
        ("panel", "open", "procesos", None), ("panel", "open", "conectores", "telegram")]
    other = acts.run("show_panel", {"panel": "w_tab"}, "x_10")                # no tab of words: only the declared ones
    assert other.data["reason"] == "no_such_tab" and "procesos" in other.data["tabs"] and len(doors["panel"]) == 2
    assert not doors["canvas"]


def test_a_message_never_crosses_this_door(doors, monkeypatch):
    from nucleo.send import turn
    monkeypatch.setattr(turn, "is_message", lambda wid, action, payload=None: True)
    got = acts.run("show_widget", {"widget": NEW}, "x_9")
    assert got.status == "rejected" and not doors["canvas"] and not doors["panel"]


def test_every_run_carries_what_is_open_the_widget_in_front_and_an_index_and_reads_the_rest(doors, monkeypatch):
    """What is open comes first (the tasks, a draft), the dates beside NOW, the widget in front with its actions and
    what it holds, then the facts and the short index; the connectors, what was done, the browser and every other
    open widget are topics read when named — never in every run."""
    from nucleo import canvas_focus
    from nucleo.conversation_host import memory_read
    from nucleo.acts import show_target
    from widgets import read as widget_read
    assert [t for t, _r in memory_read.READERS] == ["DAYS", "OPEN", "DRAFT", "PRESENT", "FRONT", "STATE", "WIDGETS"]
    monkeypatch.setattr(canvas_focus, "phone_front", lambda: None)
    monkeypatch.setattr(widget_read, "read", lambda wid: f"w_holds of {wid}")
    monkeypatch.setattr(show_target, "at_full_screen", lambda: "")
    doors["open"] = ["youtube", f"{NEW}::c1"]
    assert memory_read.front_card() == f"{NEW}::c1"                        # the newest opened
    assert memory_read._front().splitlines() == [f"{NEW}::c1", f"holds: w_holds of {NEW}::c1"]
    monkeypatch.setattr(show_target, "at_full_screen", lambda: "youtube")
    assert memory_read.front_card() == "youtube"                           # the one at full screen covers the rest
    doors["open"] = []
    monkeypatch.setattr(show_target, "at_full_screen", lambda: "")
    monkeypatch.setattr(memory_read, "_open_ids", lambda: [])
    assert memory_read._front() == ""


@pytest.fixture
def widget_door(doors, monkeypatch):
    """A widget with no code of ours declaring three actions; the data-op door and the one asker recorded."""
    import asyncio

    from nucleo.acts import data_ops


    from nucleo.acts import frontend
    from widgets import read as widget_read
    from nucleo.request import consent_ask
    from widgets import confirm_gate
    from widgets import effects, producers, runtime
    acts_of = {"w_play": {"payload": {"query": "x"}}, "w_wipe": {"confirm": True}, "w_send": {},
               "w_tick": {"internal": True}}
    monkeypatch.setattr(runtime, "get", lambda wid: {"id": NEW, "actions": acts_of} if str(wid) == NEW else None)
    monkeypatch.setattr(widget_read, "resolve", lambda named, text="": NEW if named in (NEW, "w_title") else None)
    monkeypatch.setattr(frontend, "action_mode_now", lambda w, a, p=None: "confirm" if a == "w_wipe" else "fast")
    monkeypatch.setattr(effects, "leaves", lambda w, a: a == "w_send")
    monkeypatch.setattr(effects, "carries", lambda w, a, e: a == "w_play" and e == effects.PRESENT_MOUNT)
    monkeypatch.setattr(producers, "starts_production", lambda w, a: False)
    monkeypatch.setattr(confirm_gate, "decide", lambda w, a, p, order="": {"kind": "ask", "question": "w_sure?"})
    monkeypatch.setattr(consent_ask, "ask_consent", lambda w, a, p, q, **kw: doors.setdefault("asked", []).append(
        (w, a, q)) or ("row1", "ask1"))

    async def dispatch(wid, action, payload, **kw):
        doors.setdefault("ran", []).append((wid, action, payload))
        return {"ok": True, "now_playing": "w_song"}
    monkeypatch.setattr(data_ops, "dispatch_and_report", dispatch)
    from nucleo.conversation_host import acts_widget
    return lambda args: asyncio.run(acts_widget.widget_act(args, "x_w"))


def test_a_declared_action_runs_through_the_data_op_door_and_brings_its_card(widget_door, doors):
    got = widget_door({"widget": "w_title", "action": "w_play", "payload": {"query": "w_q"}})
    assert got.status == "ok" and got.data["now_playing"] == "w_song"
    assert doors["ran"] == [(NEW, "w_play", {"query": "w_q"})]
    assert [(op, wid) for op, wid, _s, _k in doors["canvas"]] == [("show", NEW)]   # its output lives in its card


def test_an_undeclared_action_fails_naming_the_declared_ones(widget_door, doors):
    got = widget_door({"widget": NEW, "action": "w_tick"})                 # internal: the card fires it, never the model
    assert got.status == "failed" and got.data["actions"] == ["w_play", "w_send", "w_wipe"] and "ran" not in doors


def test_an_act_that_asks_waits_on_its_row_and_one_that_leaves_is_held(widget_door, doors):
    asked = widget_door({"widget": NEW, "action": "w_wipe"})
    assert asked.status == "ok" and asked.data["asked"] == "w_sure?" and doors["asked"] == [(NEW, "w_wipe", "w_sure?")]
    held = widget_door({"widget": NEW, "action": "w_send"})
    assert held.status == "refused" and held.data["reason"] == "held" and "ran" not in doors
