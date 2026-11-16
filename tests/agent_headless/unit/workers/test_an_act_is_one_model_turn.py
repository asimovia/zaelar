"""An act with a payload is ONE model turn: its declared fields go as `key=value` arguments of one command.

Measured: every act with a payload cost the worker two model turns — Write `step.json`, then Bash the bridge with
`@step.json` — because the brief forbade JSON on the command line (shell quoting broke it). `cli.widget data <widget>
<action> field=value …` builds the payload from the action's DECLARED fields, and the brief renders that one command
with each value quoted for the shell. Variants: text with quotes, `$`, backticks and backslashes; a list; a number;
an undeclared key (falls back to the JSON path, never guessed).
"""
from __future__ import annotations

import subprocess

import pytest

from nucleo.cli import widget as cli_widget
from nucleo.workers.prompts import first_act

PAYLOADS = [
    {"name": 'la "cena" de $HOME `ya` con \\ barra', "contactIds": ["c1", "Ana's"]},
    {"name": "Dinner", "contactIds": []},
]


@pytest.mark.parametrize("payload", PAYLOADS)
def test_the_rendered_command_round_trips_through_bash_to_the_same_payload(payload):
    cmd = first_act.command("contactos", "create_group", payload)
    head = "python -m nucleo.cli.widget data "
    assert cmd.startswith(head)
    script = 'f(){ for a in "$@"; do printf "%s\\0" "$a"; done; }; f ' + cmd[len(head):]   # bash parses it, as the worker's shell
    argv = subprocess.run(["bash", "-c", script], capture_output=True, text=True).stdout.split("\0")[:-1]
    assert argv[:2] == ["contactos", "create_group"]
    assert cli_widget._field_args("contactos", "create_group", argv[2:]) == payload


def test_the_bridge_sends_the_fields_in_one_call(monkeypatch):
    sent = []
    monkeypatch.setattr(cli_widget, "_act", lambda action, payload: sent.append((action, payload)) or {"ok": True})
    monkeypatch.setattr(cli_widget, "_report", lambda res: 0)
    rc = cli_widget.main(["widget", "data", "contactos", "create_group", "name=cena", 'contactIds=["c1"]'])
    assert rc == 0 and sent == [("widget_data", {"widget_id": "contactos", "action": "create_group",
                                                 "payload": {"name": "cena", "contactIds": ["c1"]}})]


def test_an_undeclared_key_is_not_read_as_a_field():
    assert cli_widget._field_args("contactos", "create_group", ["colour=red"]) is None
    assert cli_widget._field_args("contactos", "create_group", ["just a sentence"]) is None


def test_the_send_row_block_renders_the_one_command(monkeypatch):
    from nucleo.request import send_task_words
    monkeypatch.setattr(send_task_words, "artefact", lambda uid: {
        "widget": "mensajeria", "action": "send_to", "payload": {"contact": "Ana"},
        "slots": {"recipient": {"key": "contact", "source": "his"}, "text": {"key": "text", "rule": "composed"}}})
    out = send_task_words.brief_block("row-1")
    assert 'python -m nucleo.cli.widget data mensajeria send_to contact="Ana" text="<…>"' in out


def test_disarmed_without_field_arguments_the_act_needs_a_file_first(monkeypatch):
    """RED proof: with the argument reader disarmed, `name=cena` is not a payload (the two-turn path again)."""
    monkeypatch.setattr(cli_widget, "_field_args", lambda wid, action, args: None)
    sent = []
    monkeypatch.setattr(cli_widget, "_act", lambda action, payload: sent.append(payload) or {"ok": True})
    monkeypatch.setattr(cli_widget, "_report", lambda res: 0)
    cli_widget.main(["widget", "data", "contactos", "create_group", "name=cena"])
    assert not sent or sent[0].get("payload") != {"name": "cena"}
