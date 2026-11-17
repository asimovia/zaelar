"""An act with a payload is ONE model turn: its declared fields go as arguments of one command, read ONE way.

Measured: every act with a payload cost the worker two model turns — Write `step.json`, then Bash the bridge. The rule
of `cli.widget data <widget> <action> …` (third audit: three rounds of a value read two ways): `field=value` is ALWAYS
literal text (empty, `[ ] milk`, `true`, `{ok}` included), `field:=<json>` is the only typed value, a non-text field
the action declares is converted by the widget door (`widgets.field_types`). A refusal ends the command with rc≠0 and
never falls to another path. Property: every command `first_act.command` renders is accepted and arrives identical,
for every declared action of every widget, through bash.
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


def test_disarmed_without_field_arguments_the_act_needs_a_file_first(monkeypatch):
    """RED proof: with the argument reader disarmed, `name=cena` is not a payload (the two-turn path again)."""
    monkeypatch.setattr(cli_widget, "_field_args", lambda wid, action, args: None)
    sent = []
    monkeypatch.setattr(cli_widget, "_act", lambda action, payload: sent.append(payload) or {"ok": True})
    monkeypatch.setattr(cli_widget, "_report", lambda res: 0)
    cli_widget.main(["widget", "data", "contactos", "create_group", "name=cena"])
    assert not sent or sent[0].get("payload") != {"name": "cena"}


@pytest.mark.parametrize("value", ["", "[ ] comprar leche", "true", "{ok}", "null", "[URGENTE] llama a casa", "34666"])
def test_a_field_value_is_always_literal_text(value):
    """Third audit B1: `relation=` clears, `body='[ ] milk'` is a checkbox line, `text='true'` is the word."""
    assert cli_widget._field_args("contactos", "set_alias", ["contactId=c3", f"relation={value}"]) == {
        "contactId": "c3", "relation": value}


@pytest.mark.parametrize("args", [["name=a", "name=b"], ["colour=red"], ["name=a", "loose words"],
                                  ["name:=not json"]])
def test_a_refusal_ends_the_command_and_never_falls_to_another_path(args, monkeypatch, capsys):
    sent = []
    monkeypatch.setattr(cli_widget, "_act", lambda action, payload: sent.append(payload) or {"ok": True})
    monkeypatch.setattr(cli_widget, "_report", lambda res: 0)
    rc = cli_widget.main(["widget", "data", "agenda", "add_list", *args] if args == ["name:=not json"]
                         else ["widget", "data", "contactos", "create_group", *args])
    assert rc != 0 and sent == [], (rc, sent)
    assert capsys.readouterr().out.strip(), "the refusal says how to write it"


def _bash_argv(cmd: str) -> list[str]:
    head = "python -m nucleo.cli.widget data "
    script = 'f(){ for a in "$@"; do printf "%s\\0" "$a"; done; }; f ' + cmd[len(head):]
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True).stdout.split("\0")[:-1]


_ADVERSE = ["", "[ ] x", "true", "{ok}", "Ana's $50 `x` \\ \"q\"", "null", "a=b"]


def _actions():
    from widgets import runtime
    for w in runtime.catalog():
        wid = str(w.get("id") or "")
        for act, spec in ((runtime.get(wid) or {}).get("actions") or {}).items():
            if isinstance(spec, dict) and isinstance(spec.get("payload"), dict) and spec["payload"]:
                yield wid, act, spec["payload"]


def test_every_rendered_command_is_accepted_and_arrives_identical_for_every_action():
    """Property (third audit): what the brief renders, the bridge reads back unchanged — all widgets, all actions."""
    n = 0
    for wid, act, spec in _actions():
        for i, v in enumerate(_ADVERSE):
            payload = {k: (v if (j + i) % 3 else ["x", v]) for j, k in enumerate(spec)}   # text and typed lists
            argv = _bash_argv(first_act.command(wid, act, payload))
            assert argv[:2] == [wid, act]
            assert cli_widget._field_args(wid, act, argv[2:]) == payload, (wid, act, payload)
        n += 1
    assert n > 150, n


# ── a typed field that arrives null or empty is ABSENT (third audit B2) ──────────────────────────────────────────
@pytest.mark.parametrize("value", [None, "", "  "])
def test_a_null_or_empty_typed_field_is_absent_and_the_handler_decides(value):
    from widgets import field_types
    assert "favorite" not in field_types.coerce("contactos", "set_favorite", {"contactId": "c1", "favorite": value})
    assert field_types.coerce("contactos", "set_favorite", {"contactId": "c1", "favorite": "false"})["favorite"] is False


@pytest.mark.parametrize("value", [None, ""])
def test_set_favorite_with_null_still_stars_through_the_real_door(value):
    """`set_favorite {favorite: null}` once UNSTARRED (null read as false); omitted means star, so null does too."""
    a = _brain("contactos", "add_contact", {"name": f"Estrella {value!r}"})
    from widgets.contactos import data as ct
    cid = next(c["id"] for c in ct.store.load(ct.WIDGET_ID).get("contacts", []) if c.get("name") == f"Estrella {value!r}")
    _brain("contactos", "set_favorite", {"contactId": cid, "favorite": value})
    c = next(c for c in ct.store.load(ct.WIDGET_ID).get("contacts", []) if c["id"] == cid)
    assert c.get("favorite") is True, (a, c)


def test_the_all_day_alias_false_is_false_through_the_real_door():
    from widgets.agenda import data as agenda
    _brain("agenda", "add_meeting", {"title": "Alias false", "date": "2031-05-06", "startTime": "11:00",
                                     "all_day": "false"})
    m = next(m for m in agenda.load_db().get("meetings", []) if m.get("title") == "Alias false")
    assert not m.get("allDay") and m.get("startTime") == "11:00", m


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




def test_update_meeting_declares_the_field_it_types():
    from widgets import field_types, runtime
    for wid in ("agenda", "contactos", "mensajeria", "musica", "youtube"):
        for act, spec in (runtime.get(wid).get("actions") or {}).items():
            undeclared = [k for k in field_types.declared(wid, act) if k not in (spec.get("payload") or {})
                          and k != "all_day"]                       # `all_day` is a typed ALIAS of `allDay`
            assert not undeclared, (wid, act, undeclared)
