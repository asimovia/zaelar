"""V2-887 step 1 — what observability keeps can be read back.

  · a WORD of a known name is a name only where it is written as one: lowercase it is just a word of the sentence
    («te dije su nombre» with a contact «Nombre Manuel Baeza»), while the whole name and the capitalised word are
    tagged as before;
  · one brief call answers many questions, and its tokens ride the FIRST read only — the events table summed one
    trip once per question.
"""
from __future__ import annotations

from nucleo import jev
from observability import pii


def _with_names(monkeypatch, *names):
    known = {}
    whole = set()
    for n in names:
        k = pii.norm(n)
        known[k] = "[PERSON]"
        whole.add(k)
        known.update({w: "[PERSON]" for w in k.split() if len(w) >= 3})
    monkeypatch.setattr(pii, "_known_cache", {"at": 1e18, "val": known, "words": frozenset(set(known) - whole)})


def test_a_lowercase_word_that_is_part_of_a_name_is_not_tagged(monkeypatch) -> None:
    _with_names(monkeypatch, "Nombre Manuel Baeza", "Ana Que Lopez")
    kept = pii.tag("te dije su nombre y que me conteste con ganas")
    assert kept == "te dije su nombre y que me conteste con ganas"


def test_the_name_written_as_a_name_is_still_tagged(monkeypatch) -> None:
    _with_names(monkeypatch, "Nombre Manuel Baeza", "raquel")
    assert "Baeza" not in pii.tag("hablé con Manuel Baeza ayer")
    assert pii.tag("mándale a raquel un mensaje") == "mándale a [PERSON] un mensaje"     # a whole name in any case
    assert pii.tag("Nombre Manuel llamó").startswith("[PERSON]")                     # capitalised: a name


def test_one_brief_call_bills_its_tokens_once(monkeypatch) -> None:
    jev._BILLED.clear()
    usage = {"prompt_tokens": 8657, "completion_tokens": 1420, "model": "m"}
    first = jev._billed_once("call-1", dict(usage))
    again = jev._billed_once("call-1", dict(usage))
    assert first["prompt_tokens"] == 8657
    assert "prompt_tokens" not in again and again["call_prompt_tokens"] == 8657
    assert jev._billed_once("call-2", dict(usage))["prompt_tokens"] == 8657


def test_the_turn_record_keeps_what_the_model_called_with_its_arguments() -> None:
    from nucleo.turn import commission
    got = commission._args_of({"name": "widget_data", "args": {"id": "mensajeria", "contact": "Raquel Salvador"}})
    assert got["name"] == "widget_data" and "Raquel Salvador" in got["args"]
