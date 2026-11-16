"""The worker's brief hands over the act the turn identified as its first step — to ITS errand, once, under the ceiling.

Measured: a «create a group» errand reached its worker as a paraphrase with no card and no action; the worker ran
~20 chained searches for more than 15 minutes and never created the group. The turn's `screen_action` verdict had
named the card's action and the reading travelled on the row. Now the handoff carries, when the verdict is sure and
the card declares the action, its declared fields and the one command that runs it — only to the errand the act
belongs to (the turn's ONE errand: `heard`), never when the turn already ran it, and his sentence once (not when the
recent conversation carries it). The live brief (`first_act.live`, what the dispatcher sends) stays under
`PROMPT_CEILING_CHARS` whatever the turn carried: a block that does not fit is dropped, lowest priority first.
Variants: two cards, es and en, the three sample briefs.
"""
from __future__ import annotations

import asyncio
import shlex

import pytest

from nucleo.workers import state_now
from nucleo.workers.prompts import first_act
from nucleo.workers.prompts.catalog import PROMPT_CEILING_CHARS

SAID = {"es": "crea un grupo con Ana y Luis que se llame cena", "en": "make a group called dinner with Ana and Luis"}


def _reading(choice: str, confidence: float, turn_id: str = "t1") -> dict:
    return {"result": {"screen_action": {"choice": choice, "confidence": confidence}}, "open_ids": [],
            "turn_id": turn_id, "judged": "x"}


def _one(said: str) -> dict:
    return {"said": said, "heard": said}          # the turn's ONE errand


@pytest.fixture(params=["es", "en"])
def lang(request, monkeypatch):
    from i18n import langs
    monkeypatch.setattr(langs, "current_code", lambda: request.param)
    monkeypatch.setattr(langs, "current_language", lambda: langs.LANGUAGES[request.param])
    from nucleo.workers.prompts import build, context, web
    for mod in (context, build, web):
        monkeypatch.setattr(mod, "_recent_conversation_block", lambda *a, **k: "")
    return request.param


@pytest.mark.parametrize("choice,fields", [("contactos:create_group", ("name",)),            # contactIds is optional
                                           ("contactos:rename_group", ("groupId", "name"))])
def test_a_sure_identified_act_is_the_first_step_with_its_declared_fields(lang, choice, fields):
    out = first_act.block("", _one(SAID[lang]), _reading(choice, 0.95))
    assert f"«{SAID[lang]}»" in out, "his words ride verbatim"
    wid, act = choice.split(":")
    cmd = shlex.split(out.split("`python -m nucleo.cli.widget data ")[1].split("`")[0])
    assert cmd == [wid, act, *(f"{f}=<…>" for f in fields)], "ONE command, the REQUIRED fields as arguments"
    for f in fields:
        assert f"· {f}:" in out
    if act == "create_group":
        assert "· contactIds:" in out, "an optional field is listed, never a placeholder"


def test_a_doubtful_verdict_or_an_undeclared_action_hands_over_no_act(lang, monkeypatch):
    monkeypatch.setattr(state_now, "block", lambda own="": "")
    assert first_act.act_block(_reading("contactos:create_group", 0.2), _one("x")) == ""
    assert first_act.act_block(_reading("contactos:no_such_action", 0.99), _one("x")) == ""
    assert first_act.act_block({}, _one("x")) == ""
    assert first_act.block("", {}, {}) == "", "nothing to hand over is no block at all"


@pytest.mark.parametrize("ctx", [{"said": "crea el grupo cena y búscame un restaurante", "heard": "", "part": 0},
                                 {"said": "crea el grupo cena y búscame un restaurante", "heard": ""}])
def test_an_errand_that_is_one_of_several_gets_no_act(lang, ctx):
    """Audit #5: «crea un grupo … y búscame un restaurante» — the restaurant's worker is never told to create it."""
    assert first_act.act_block(_reading("contactos:create_group", 0.97), ctx) == ""


def test_an_act_the_turn_already_ran_is_not_handed_over(lang, monkeypatch):
    from nucleo import done_ops
    monkeypatch.setattr(done_ops, "recent", lambda *a, **k: [
        {"wid": "contactos", "action": "create_group", "trace": "turn-9"}])
    assert first_act.act_block(_reading("contactos:create_group", 0.97, "turn-9"), _one("x")) == ""
    assert first_act.act_block(_reading("contactos:create_group", 0.97, "turn-10"), _one("x")), "another turn's"


def test_his_words_ride_once(lang, monkeypatch):
    from nucleo.workers.prompts import context
    monkeypatch.setattr(context, "_recent_conversation_block", lambda *a, **k: f"he: {SAID[lang]}")
    assert f"«{SAID[lang]}»" not in first_act.block("", _one(SAID[lang]), {}), "already in the recent conversation"


def _worst(monkeypatch):
    monkeypatch.setattr(state_now, "channels", lambda: {"whatsapp": "connected", "telegram": "connected", "email": "off"})
    monkeypatch.setattr(state_now, "widgets", lambda: [f"widget{i}" for i in range(12)])
    monkeypatch.setattr(state_now, "tasks", lambda own="": [{"id": str(i), "title": "x" * 40, "state": "running"}
                                                            for i in range(9)])
    monkeypatch.setattr(state_now, "clusters", lambda: [{"name": f"cluster{i}", "connected": True} for i in range(9)])
    return {"said": "y" * 600, "heard": "y" * 600}, _reading("agenda:update_task", 0.97)


@pytest.mark.parametrize("name", ["hotel", "document", "message"])
def test_the_live_brief_stays_under_the_ceiling(lang, monkeypatch, name):
    """Audit #3/4: the ceiling is measured on what the dispatcher SENDS (`first_act.live`), worst case."""
    from tests.agent_headless.unit.workers import test_a_worker_brief_is_its_playbook_and_headlines as T
    ctx, rd = _worst(monkeypatch)
    _pb, base = T._compose(name, T.SAMPLES[name][lang])
    out = first_act.live(base, "", "", ctx, rd)
    assert len(out) <= PROMPT_CEILING_CHARS, (name, len(out))
    if name != "hotel":
        assert "agenda update_task" in out, "a brief with room keeps the act"
    assert len(state_now.block()) <= state_now.BLOCK_CAP


def test_disarmed_without_the_budget_the_live_brief_goes_over(lang, monkeypatch):
    """RED proof: the handoff appended whole puts the worst-case hotel over the ceiling."""
    from tests.agent_headless.unit.workers import test_a_worker_brief_is_its_playbook_and_headlines as T
    ctx, rd = _worst(monkeypatch)
    _pb, base = T._compose("hotel", T.SAMPLES["hotel"][lang])
    assert len(base) + 2 + len(first_act.block("", ctx, rd)) > PROMPT_CEILING_CHARS


def test_the_dispatch_door_sends_the_handoff(monkeypatch):
    """Audit #12: the real door (`dispatch._run_session`) composes it — only the delivery is stubbed."""
    from nucleo import dispatch
    from nucleo.dispatch import confirm, session_steps
    from nucleo.workers.session_record import SessionRecord
    seen = {}

    async def _deliver(**kw):
        seen["prompt"] = kw["prompt"]
        return {}

    async def _no_gate(*a, **k):
        return False
    monkeypatch.setattr(session_steps, "run_it_to_its_delivery", _deliver)
    monkeypatch.setattr(confirm, "unlicensed_gate", _no_gate)
    monkeypatch.setattr(dispatch, "_task_row", lambda *a, **k: None)
    monkeypatch.setattr(dispatch, "sync_state", lambda *a, **k: None)
    task = dispatch.Task(id="d1", request="crea el grupo cena", kind="generic", trusted=True,
                         context={"errand_kind": {"choice": "generic", "confidence": 0.95},
                                  "errand_class": {"choice": "none", "confidence": 0.95}, **_one("crea el grupo cena"),
                                  "reading": _reading("contactos:create_group", 0.97)})
    dispatch._SESSIONS["d1"] = SessionRecord(task_id="d1", goal="crea el grupo cena", kind="generic")
    try:
        asyncio.run(dispatch._run_session(task))
    finally:
        dispatch._SESSIONS.pop("d1", None)
    assert "cli.widget data contactos create_group" in seen.get("prompt", "")
