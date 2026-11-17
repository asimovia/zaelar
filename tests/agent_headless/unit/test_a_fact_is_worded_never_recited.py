"""V2-933 · What the engine tells him is a FACT worded by a model — never a fixed sentence.

His rule (2026-11-18): nothing he hears is hardcoded; every reply is natural and different, and it speaks about what
he asked for (the message to her, the coffee study, the car), never about tasks, processes or flows. The engine
decides the FACT («sent and confirmed», «could not be sent: no connection»); `nucleo/wording.word` hands it to a
small model with the voice's rules and the language's own line as an EXAMPLE, and says what comes back. The plain
line is only the last resort when no model answers in time.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo import wording


@pytest.fixture
def model(monkeypatch):
    seen = []

    def _ask(system, user, seat):
        seen.append({"system": system, "user": user, "seat": seat})
        return _ask.answers.pop(0) if _ask.answers else ""
    _ask.answers = []
    monkeypatch.setattr(wording, "_ask", _ask)
    _ask.seen = seen
    return _ask


def test_the_fact_goes_to_the_model_and_its_sentence_is_what_is_said(model):
    model.answers = ['«Listo, ya le ha llegado tu mensaje.»']
    line = wording.word(wording.FACTS["send_done"], examples=("Mensaje enviado.",), about="dile buenas noches a Quinn",
                        fallback="Mensaje enviado.")
    assert line == "Listo, ya le ha llegado tu mensaje.", "the model's sentence, unwrapped, is the line"
    asked = model.seen[0]
    assert wording.FACTS["send_done"] in asked["user"] and "dile buenas noches a Quinn" in asked["user"]
    assert "«Mensaje enviado.»" in asked["user"] and "do not copy" in asked["user"], "the old line rides as an EXAMPLE"


def test_two_tellings_of_one_fact_are_two_sentences(model):
    model.answers = ["Hecho, ya está enviado.", "Ya le ha llegado."]
    a = wording.word(wording.FACTS["send_done"], fallback="Mensaje enviado.")
    b = wording.word(wording.FACTS["send_done"], fallback="Mensaje enviado.")
    assert a != b and "Mensaje enviado." not in (a, b)


def test_the_model_is_asked_warm_and_inside_the_lines_budget(monkeypatch):
    from nucleo.memory_agent.processor import llm
    got = {}
    monkeypatch.setattr(llm, "chat_sync", lambda seat, system, user, **kw: got.update(seat=seat, **kw) or "Vale.")
    assert wording._model("s", "u", wording.SEAT) == "Vale."
    assert got["seat"] == "wording" and got["temperature"] >= 0.7 and got["timeout"] <= wording.WORD_S


def test_the_voices_rules_name_his_request_and_never_the_machinery():
    rules = wording.SYSTEM
    assert "differently every time" in rules and "never copy" in rules
    assert "WHAT HE ASKED FOR" in rules and all(w in rules for w in ("tasks", "processes", "flows"))
    assert "nothing else" in rules, "the model words the fact; it never adds an outcome"


@pytest.mark.parametrize("answer", ["", "   ", None])
def test_with_no_sentence_back_the_plain_line_is_said(model, answer):
    model.answers = [answer or ""]
    assert wording.word(wording.FACTS["send_going"], fallback="Vale, lo mando.") == "Vale, lo mando."


def test_a_model_that_fails_or_is_late_never_leaves_him_in_silence(monkeypatch):
    monkeypatch.setattr(wording, "_ask", lambda *a: (_ for _ in ()).throw(TimeoutError("slow")))
    assert wording.word("anything", fallback="plain") == "plain"
    assert asyncio.run(wording.word_soon("anything", fallback="plain")) == "plain"


def test_every_line_of_a_send_has_its_fact():
    for key in ("send_preparing", "send_going", "send_not_sent", "send_done", "send_failed", "send_unconfirmed",
                "stopped_now", "answer_taken", "work_started", "confirm_cancelled"):
        assert wording.FACTS.get(key), f"{key} would be said as a fixed sentence"
    assert "{why}" in wording.FACTS["send_failed"] and "NOT" in wording.FACTS["send_failed"]


def test_the_receipts_line_and_the_switchboards_line_are_the_models(model, monkeypatch):
    from nucleo.pulse import notices
    from nucleo.request import send_receipt
    from nucleo.switchboard import act
    said = []

    async def _notify(title, text, **kw):
        said.append(text)
        return {"id": 1}
    monkeypatch.setattr(notices, "notify", _notify)
    model.answers = ["No ha salido: el teléfono no tiene conexión.", "Venga, se lo mando ahora mismo."]
    asyncio.run(send_receipt._say("u1", "failed", "send_failed", why="no connection"))
    assert said == ["No ha salido: el teléfono no tiene conexión."] and "no connection" in model.seen[0]["user"]
    assert act._line("send_going", "dile buenas noches a Quinn") == "Venga, se lo mando ahora mismo."


def test_disarm_with_the_model_silent_the_sends_lines_are_the_languages_own(monkeypatch):
    """The suite's own state: no model → the plain lines, which is what every other test of a send asserts."""
    from i18n import langs
    from nucleo.switchboard import act
    assert act._line("send_going") == str(langs.current_language().send_going)
