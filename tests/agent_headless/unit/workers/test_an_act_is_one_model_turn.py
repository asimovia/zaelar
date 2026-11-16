"""An act with a payload is ONE model turn: its declared fields go as `key=value` arguments of one command.

Measured: every act with a payload cost the worker two model turns — Write `step.json`, then Bash the bridge with
`@step.json` — because the brief forbade JSON on the command line (shell quoting broke it). `cli.widget data <widget>
<action> field=value …` builds the payload from the action's DECLARED fields, and the brief renders that one command
with each value single-quoted (the shell expands nothing). Variants: text with quotes, `$`, backticks and
backslashes; digits and «true» that stay text; a field declared as a list; an undeclared key (the JSON path).
"""
from __future__ import annotations

import subprocess

import pytest

from nucleo.cli import widget as cli_widget
from nucleo.workers.prompts import first_act

PAYLOADS = [   # (widget, action, payload): text stays text, a field DECLARED as a list is its JSON
    ("contactos", "create_group", {"name": 'la "cena" de $HOME `ya` $50 con \\ barra', "contactIds": "c1,Ana's"}),
    ("contactos", "create_group", {"name": "34666123456", "contactIds": "c1"}),
    ("contactos", "create_group", {"name": "true story", "contactIds": ["c1", "c2"]}),     # typed with `:=`
    ("agenda", "add_meeting", {"title": "x", "date": "2026-12-01", "startTime": "10:00", "allDay": False}),
    ("results", "append", {"items": [{"title": "Ana's $50"}]}),
]


@pytest.mark.parametrize("wid,act,payload", PAYLOADS)
def test_the_rendered_command_round_trips_through_bash_to_the_same_payload(wid, act, payload):
    """Audit #7: no value is changed on the way — a phone number, «true», `$50`, backticks stay what they were."""
    cmd = first_act.command(wid, act, payload)
    head = "python -m nucleo.cli.widget data "
    assert cmd.startswith(head)
    script = 'f(){ for a in "$@"; do printf "%s\\0" "$a"; done; }; f ' + cmd[len(head):]   # bash parses it, as the worker's shell
    argv = subprocess.run(["bash", "-c", script], capture_output=True, text=True).stdout.split("\0")[:-1]
    assert argv[:2] == [wid, act]
    assert cli_widget._field_args(wid, act, argv[2:]) == payload


def test_the_bridge_sends_the_fields_in_one_call(monkeypatch):
    sent = []
    monkeypatch.setattr(cli_widget, "_act", lambda action, payload: sent.append((action, payload)) or {"ok": True})
    monkeypatch.setattr(cli_widget, "_report", lambda res: 0)
    rc = cli_widget.main(["widget", "data", "contactos", "create_group", "name=cena", "contactIds=c1,c2"])
    assert rc == 0 and sent == [("widget_data", {"widget_id": "contactos", "action": "create_group",
                                                 "payload": {"name": "cena", "contactIds": "c1,c2"}})]


def test_an_undeclared_key_is_not_read_as_a_field():
    assert cli_widget._field_args("contactos", "create_group", ["colour=red"]) is None
    assert cli_widget._field_args("contactos", "create_group", ["just a sentence"]) is None


def test_the_send_row_block_renders_the_one_command(monkeypatch):
    from nucleo.request import send_task_words
    monkeypatch.setattr(send_task_words, "artefact", lambda uid: {
        "widget": "mensajeria", "action": "send_to", "payload": {"contact": "Ana"},
        "slots": {"recipient": {"key": "contact", "source": "his"}, "text": {"key": "text", "rule": "composed"}}})
    out = send_task_words.brief_block("row-1")
    assert "python -m nucleo.cli.widget data mensajeria send_to contact='Ana' text='<…>'" in out


def test_disarmed_without_field_arguments_the_act_needs_a_file_first(monkeypatch):
    """RED proof: with the argument reader disarmed, `name=cena` is not a payload (the two-turn path again)."""
    monkeypatch.setattr(cli_widget, "_field_args", lambda wid, action, args: None)
    sent = []
    monkeypatch.setattr(cli_widget, "_act", lambda action, payload: sent.append(payload) or {"ok": True})
    monkeypatch.setattr(cli_widget, "_report", lambda res: 0)
    cli_widget.main(["widget", "data", "contactos", "create_group", "name=cena"])
    assert not sent or sent[0].get("payload") != {"name": "cena"}


@pytest.mark.parametrize("args", [["name=a", "name=b"], ["name=a", "contactIds=true"], ["name=a", 'contactIds=["c1"]'],
                                  ["name=a", "contactIds={}"], ["name=a", "contactIds=null"]])
def test_an_ambiguous_or_repeated_argument_is_refused_never_guessed(args, capsys):
    """Second audit B: a repeated field is not «the last one», and an untyped JSON literal is not read as text."""
    assert cli_widget._field_args("contactos", "create_group", args) is None
    said = capsys.readouterr().out
    assert ":=" in said or "twice" in said, said


def _brain(wid, act, payload):
    import asyncio

    from widgets.server_api import brain_action
    return asyncio.run(brain_action(wid, act, payload))


@pytest.mark.parametrize("day,all_day", [(4, "false"), (5, "0"), (6, "no"), (7, ""), (8, False)])
def test_a_false_boolean_through_the_real_door_is_false(day, all_day):
    """Second audit B(1): `allDay=false` stored the meeting all-day and lost its hour. The widget door converts a
    declared boolean once (`widgets.field_types`), whatever spelled it: a `field=` argument, a JSON file, a model."""
    from widgets.agenda import data as agenda
    title = f"Dentista {day}"
    res = _brain("agenda", "add_meeting", {"title": title, "date": f"2031-03-{day:02d}", "startTime": "10:00",
                                           "allDay": all_day})
    assert res.get("ok") is not False, res
    db = agenda.load_db()
    m = next(m for m in db.get("meetings", []) if m.get("title") == title)
    assert not m.get("allDay") and m.get("startTime") == "10:00", m


def test_a_list_through_the_one_command_reaches_the_widget_as_a_list():
    """Second audit B(2): `contactIds='["c1","c2"]'` created a group with nobody in it. `contactIds:=` is the list."""
    a = _brain("contactos", "add_contact", {"name": "Ana Prueba"})
    b = _brain("contactos", "add_contact", {"name": "Luis Prueba"})
    ids = [str((r.get("result") or r).get("id") or (r.get("contact") or {}).get("id") or "") for r in (a, b)]
    if not all(ids):
        from widgets.contactos import data as ct
        db = ct.store.load(ct.WIDGET_ID)
        ids = [c["id"] for c in db.get("contacts", []) if c.get("name") in ("Ana Prueba", "Luis Prueba")]
    import json as _j
    payload = cli_widget._field_args("contactos", "create_group", ["name=cena prueba", f"contactIds:={_j.dumps(ids)}"])
    res = _brain("contactos", "create_group", payload)
    assert len((res.get("result") or res).get("added") or []) == 2, res


def test_disarmed_without_the_door_conversion_false_is_true(monkeypatch):
    """RED proof: with the conversion disarmed, «false» reaches the card as a non-empty string — true."""
    from widgets import field_types
    monkeypatch.setattr(field_types, "coerce", lambda wid, action, payload: payload)
    from widgets.agenda import data as agenda
    _brain("agenda", "add_meeting", {"title": "Disarmed", "date": "2031-04-09", "startTime": "10:00", "allDay": "false"})
    m = next(m for m in agenda.load_db().get("meetings", []) if m.get("title") == "Disarmed")
    assert m.get("allDay")
