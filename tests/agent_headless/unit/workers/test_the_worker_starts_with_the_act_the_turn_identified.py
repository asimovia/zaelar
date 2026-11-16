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


@pytest.mark.parametrize("name", ["document", "message"])
def test_the_live_brief_stays_under_the_ceiling(lang, monkeypatch, name):
    """Audit #3/4: the ceiling is measured on what the dispatcher SENDS (`first_act.live`), worst case."""
    from tests.agent_headless.unit.workers import test_a_worker_brief_is_its_playbook_and_headlines as T
    ctx, rd = _worst(monkeypatch)
    _pb, base = T._compose(name, T.SAMPLES[name][lang])
    out = first_act.fit(first_act.live(base, "", "", ctx, rd))
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


# ── the WHOLE brief as sent, worst case (second audit C) ────────────────────────────────────────────────────────
def _full(monkeypatch, lang, name, *, memory=2000, recent=1200):
    from nucleo.workers.prompts import build, catalog, context, web
    from tests.agent_headless.unit.workers import test_a_worker_brief_is_its_playbook_and_headlines as T
    lines = "\n".join(f"he: línea {i} " + "z" * 60 for i in range(recent // 70))
    for mod in (context, build, web):
        monkeypatch.setattr(mod, "_recent_conversation_block", lambda *a, **k: lines)
    ctx, rd = _worst(monkeypatch)
    req = T.SAMPLES[name][lang]
    mem = "\n".join(f"- dato {i} " + "m" * 60 for i in range(memory // 70))
    if name == "hotel":
        _pb, base = "errand", web._web_prompt(req, mem, T._research_brief(), playbook="errand")
    else:
        _pb, base = "x", build._build_prompt(req, mem, True, None)
    out = first_act.live(base, "", "", ctx, rd)
    if name == "hotel":     # a research errand: the direction note rides (`dispatch.session`, `_brief_bg`)
        return catalog, first_act.fit(out + "\n\nNOTA: la dirección de esta investigación llega en breve; empieza ya "
                                            "y aplícala al llegar.")      # the note as `dispatch.session` writes it
    from nucleo.workers.handoff import with_worker_brief   # a relay: its brief rides in front
    return catalog, first_act.fit(with_worker_brief(out, {"worker_brief": "RESUME this errand: " + "r" * 400}))


@pytest.mark.parametrize("name", ["hotel", "document", "message"])
def test_fit_cuts_only_the_new_blocks_never_his_memory_or_conversation(lang, monkeypatch, name):
    """Third audit C: the brief as sent keeps its memory and conversation WHOLE, as before this batch; only the
    handoff's own blocks yield to the ceiling, each one said as an event. A base over by itself is sent as it was."""
    events = []
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda *a, **k: events.append((a, k)))
    catalog, out = _full(monkeypatch, lang, name)
    mem = "\n".join(f"- dato {i} " + "m" * 60 for i in range(2000 // 70))
    assert mem in out, "the memory context rides whole"
    assert "he: línea 16 " + "z" * 60 in out and "he: línea 0 " + "z" * 60 in out, "the conversation rides whole"
    assert catalog.words("request_head" if name != "hotel" else "goal_head") in out
    if name != "hotel":
        assert "agenda update_task" in out and len(out) <= PROMPT_CEILING_CHARS, "with room, the act stays"
    else:
        assert "agenda update_task" not in out and any("left out" in str(e[0]) for e in events), \
            "no room: the act left out, and SAID"


def test_the_drop_order_is_explicit_not_greedy(lang):
    """Measured: the greedy budget dropped the act and kept his words. Here his words go before the act."""
    words_b = f"{first_act.words('his_words_head')}\n«" + "w" * 50 + "»"
    act_b = f"{first_act.words('first_act_head').format(widget='agenda', action='add')}\n  · title: x\ndo it"
    prompt = "BASE " + "b" * 200 + "\n\n" + words_b + "\n\n" + act_b
    out = first_act.fit(prompt, ceiling=len(prompt) - 10)
    assert act_b in out and words_b not in out and out.startswith("BASE")


def test_his_sentence_rides_once_when_the_request_is_his_sentence(lang):
    base = f"{first_act.words('his_words_head')[:0]}REQUEST:\n{SAID[lang]}"
    assert f"«{SAID[lang]}»" not in first_act.block("", _one(SAID[lang]), {}, seen=base)


def test_disarmed_without_fit_the_document_brief_goes_over(lang, monkeypatch):
    """RED proof: with `fit` disarmed, a full document brief plus a long state and act goes over the ceiling."""
    monkeypatch.setattr(first_act, "fit", lambda prompt, ceiling=None: prompt)
    _c, out = _full(monkeypatch, lang, "document", memory=3200, recent=1200)
    assert len(out) > PROMPT_CEILING_CHARS


def test_an_act_the_turn_ran_is_seen_behind_many_later_ops(lang, monkeypatch):
    """Second audit minor: the ledger was read through its last 8 only."""
    from nucleo import done_ops
    book = [{"wid": "contactos", "action": "create_group", "trace": "turn-9"}] + [
        {"wid": "agenda", "action": "add_task", "trace": "turn-x"} for _ in range(20)]
    monkeypatch.setattr(done_ops, "recent", lambda within_s=0, limit=8: book[-int(limit):])
    assert first_act.ran_in_the_turn("contactos", "create_group", _reading("contactos:create_group", 0.97, "turn-9"))


# ── fourth audit: the send row's block is not new, and is never cut ─────────────────────────────────────────────
_SEND_ART = {"widget": "mensajeria", "action": "send_to", "payload": {"contact": "Ana"},
             "slots": {"recipient": {"key": "contact", "source": "his"}, "text": {"key": "text", "rule": "composed"}}}


def test_the_send_rows_block_rides_through_the_real_door_even_over_the_ceiling(monkeypatch):
    """v3.159 sent it whatever the size; `fit` cut it (measured: memory 3 539 + 8 lines → 16 379 without it)."""
    from nucleo import dispatch
    from nucleo.dispatch import confirm, session_steps
    from nucleo.request import send_task_words
    from nucleo.workers.session_record import SessionRecord
    seen = {}

    async def _deliver(**kw):
        seen["prompt"] = kw["prompt"]
        return {}

    async def _no_gate(*a, **k):
        return False

    async def _memory(req, kind):
        return "\n".join(f"- dato {i} " + "m" * 70 for i in range(120))       # ~9k: the brief goes over
    monkeypatch.setattr(session_steps, "run_it_to_its_delivery", _deliver)
    monkeypatch.setattr(confirm, "unlicensed_gate", _no_gate)
    monkeypatch.setattr(dispatch, "_task_row", lambda *a, **k: None)
    monkeypatch.setattr(dispatch, "sync_state", lambda *a, **k: None)
    monkeypatch.setattr(dispatch, "_compose_context", _memory)
    monkeypatch.setattr(send_task_words, "artefact", lambda uid: _SEND_ART)
    task = dispatch.Task(id="s1", request="text Ana that I'm late", kind="generic", trusted=True,
                         context={"errand_kind": {"choice": "generic", "confidence": 0.95},
                                  "errand_class": {"choice": "none", "confidence": 0.95}, "playbook": "message"})
    rec = SessionRecord(task_id="s1", goal="text Ana that I'm late", kind="generic")
    rec.uid = "row-s1"
    dispatch._SESSIONS["s1"] = rec
    try:
        asyncio.run(dispatch._run_session(task))
    finally:
        dispatch._SESSIONS.pop("s1", None)
    out = seen.get("prompt", "")
    assert len(out) > PROMPT_CEILING_CHARS, "the case is over the ceiling"
    assert first_act.words("send_task_head") in out, "the send row's block is never cut"
    assert "dato 119 " in out, "nor the memory"
