"""A send is said in three lines, all the engine's: the ask, «sending», «sent / failed, and why» (V2-931, 2026-11-17).

Measured on his engine that night: Flash answered the order «I'm on it; it is not done yet»; the worker's question was
said as «Hey, one of the running processes is asking: The message is ready. Shall I send it to <three names>?»; his yes
was acknowledged twice with «I'll pass it to the task»; and the worker narrated the rest in its own words. The lines are
fixed strings of the language pack, said by the door that knows the fact.
"""
from __future__ import annotations

import pytest

from i18n import langs
from nucleo.pulse import workers
from nucleo.workers import exit_gate

LANGS = ("es", "en")


@pytest.mark.parametrize("lang", LANGS)
def test_the_ask_is_one_short_sentence_with_her_name_as_he_says_it(monkeypatch, lang):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    from nucleo import on_his_behalf as ob
    monkeypatch.setattr(ob, "shown_who", lambda wid, act, inner: "Quinn Ferrer Soler")
    q = exit_gate.ready_question("mensajeria", "send_draft", {"contact": "Quinn Ferrer Soler"})
    assert q == langs.spec(lang).send_ready_confirm.format(who="Quinn")
    assert len(q.split()) <= 12 and q.rstrip().endswith("?"), q


@pytest.mark.parametrize("who, said", [("Quinn Ferrer", "Quinn"), ("Quinn", "Quinn"), ("quinn@example.com", "quinn@example.com"),
                                       ("Ana Prat, Luis Mora", "Ana Prat, Luis Mora"), ("+34 600 111 222", "+34 600 111 222")])
def test_only_a_persons_name_is_shortened(who, said):
    assert exit_gate._short(who) == said


def test_a_question_is_said_as_it_is_while_its_process_is_the_only_one_open():
    say = lambda key, **kw: f"{key}:{kw['question']}"            # noqa: E731
    q = "The message for Quinn is ready — shall I send it?"
    assert workers.relay_line(say, q, "Message to Quinn", alone=True) == q
    assert workers.relay_line(say, q, "Message to Quinn", alone=False) == f"worker_ask_named:{q}", "several open: say whose"
    assert workers.relay_line(say, q, "", alone=False) == f"worker_ask_generic:{q}"


def test_the_board_decides_whether_it_is_alone(monkeypatch):
    from nucleo.switchboard import board
    say = lambda key, **kw: key                                  # noqa: E731
    monkeypatch.setattr(board, "open_processes", lambda: [{"key": "a"}])
    assert workers.relay_line(say, "q?", "goal") == "q?"
    monkeypatch.setattr(board, "open_processes", lambda: [{"key": "a"}, {"key": "b"}])
    assert workers.relay_line(say, "q?", "goal") == "worker_ask_named"


@pytest.mark.parametrize("lang", LANGS)
def test_every_line_of_a_send_exists_in_his_language_and_names_no_machinery(lang):
    spec = langs.spec(lang)
    lines = {k: str(getattr(spec, k)) for k in ("send_ready_confirm", "send_going", "send_done", "send_failed",
                                                "send_unconfirmed", "send_not_sent", "send_preparing", "answer_taken")}
    assert all(lines.values()), lines
    for line in lines.values():
        assert not any(w in line.lower() for w in ("proceso", "process", "tarea", "task", "worker", "cola", "queue")), line
    assert "{why}" in lines["send_failed"] and "{who}" in lines["send_ready_confirm"]


@pytest.mark.parametrize("lang", LANGS)
def test_the_workers_method_writes_the_draft_and_never_speaks_for_the_send(lang):
    from nucleo.request import send_errand
    import json
    from pathlib import Path
    pack = json.loads((Path(__file__).resolve().parents[4] / "i18n" / "genesis" / lang / "voice.json").read_text("utf-8"))
    steps = pack["worker_brief"]["send_errand_steps"]
    assert "mensajeria draft contact=" in steps and "mensajeria send_draft contact=" in steps
    assert steps.index("draft contact=") < steps.index("send_draft contact="), "the draft is written before it is sent"
    assert "confirm_send" in steps and "act verify" not in steps, "the receipt is the engine's to follow"
    assert send_errand.PLAYBOOK == "message"
