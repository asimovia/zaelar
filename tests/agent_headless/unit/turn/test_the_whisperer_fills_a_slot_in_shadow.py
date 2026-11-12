"""The whisperer fills a typed slot between turns, in SHADOW (V2-889 F2).

The old Susurro (removed in V2-851) was late, acted on a conversation that had moved on, bore tasks and pasted prose
into the next prompt. These tests pin what replaces it, by mechanism:

  · the gate is deterministic over verdicts the turn already paid for: a sure music order scores 0, a doubtful
    sentence about a task that waits on him fires, a sure greeting with no thread in play never fires, and a door
    verdict that has not landed counts 0;
  · in shadow it writes NOTHING: the database, the workspace and the brief handle are byte-identical after a fired
    whisper, and its only output is `whisper` events;
  · a slot goes stale when its thread moves, expires after `TTL_S`, is late when it lands after the next turn began;
    one call in flight, and no refire while the thread has not moved;
  · the slot has no instruction field and its rendering is bounded (≤ 4 lines, ≤ 600 chars) and wired into no prompt.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from nucleo.turn.whisper import gate, render, run, slot

ENGINE = Path(__file__).resolve().parents[4]


def _handle(**verdicts) -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "judged": "", "result": {k: {"choice": c, "confidence": p, "probabilities": {c: p}}
                                                  for k, (c, p) in verdicts.items()}}


LISBON = {"id": "t-lisbon", "label": "", "title": "", "request": "Book a hotel in Lisbon for the trip", "phase": "",
          "state": "waiting", "waiting_on": "user", "last_mention_ts": 1000, "parked": True}


@pytest.fixture
def events(monkeypatch):
    got: list = []
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda kind, label, text="", role="", extra=None, **_k:
                        got.append({"kind": kind, "label": label, **(extra or {})}))
    monkeypatch.setenv("ZAELAR_WHISPER", "shadow")
    run.reset()
    yield got
    run.reset()


# ── the gate ────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_a_sure_music_order_scores_zero():
    v = gate.verdicts_of(_handle(request_type=("order", 0.96), escalate_or_inline=("handle_inline", 0.97),
                                 readable=("clear", 0.99)))
    g = gate.score(v, [], [], "pon una canción de Shakira")
    assert (g.score, g.fired) == (0, False), g


def test_a_doubtful_sentence_about_a_waiting_task_fires():
    v = gate.verdicts_of(_handle(request_type=("order", 0.68), escalate_or_inline=("escalate", 0.9)))
    g = gate.score(v, [LISBON], [], "and for the Lisbon hotel make it Friday instead if they still have rooms")
    assert g.fired and g.thread["id"] == "t-lisbon", g
    assert {"doubt:request_type", "open_thread", "waiting_thread"} <= set(g.reasons), g


def test_a_sure_greeting_with_no_thread_in_play_never_fires():
    v = gate.verdicts_of(_handle(request_type=("greeting", 0.93), readable=("garbled", 0.9)))
    g = gate.score(v, [LISBON], [], "hola qué tal")
    assert g.vetoed and not g.fired and g.score == 0, g


def test_a_door_verdict_not_on_the_handle_counts_zero():
    """`acts_asked` is asked at the call door (`brief_doors`): absent from the handle it adds nothing."""
    base = gate.score(gate.verdicts_of(_handle(request_type=("order", 0.97))), [], [], "abre el mapa")
    assert base.score == 0
    several = gate.score(gate.verdicts_of(_handle(request_type=("order", 0.97), acts_asked=("several", 0.9))), [], [],
                         "abre el mapa")
    assert several.score == 1 and "several_acts" in several.reasons


def test_an_undecided_route_is_weighed_from_the_turns_own_thread_events():
    g = gate.score({}, [LISBON], ["decided:undecided"], "y lo otro")
    assert g.fired and "route_undecided" in g.reasons and g.thread["id"] == "t-lisbon", g


# ── shadow writes nothing ───────────────────────────────────────────────────────────────────────────────────────────

FULL = json.dumps({"facts": [{"text": "He wants Friday, not Thursday", "source": "his_words"}],
                   "correction": {"heard": "Lisboa hotel", "meant": "Lisbon hotel", "confidence": 0.7},
                   "missing": [{"slot": "check-out date", "why": "only the arrival changed"}],
                   "task_certainty": {"thread_id": "t-lisbon", "state": "clear", "why": "he named the hotel"},
                   "say": "Tell him it is booked", "instructions": "open the calendar"})


def _db_digest() -> str:
    p = os.environ.get("ZAELAR_DB") or ""
    if not p or not os.path.exists(p):
        return "absent"
    rows = []
    with sqlite3.connect(p) as c:    # every ordinary table's rows; a virtual one (vec0) needs its extension, skipped
        for (name,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND sql NOT LIKE 'CREATE VIRTUAL%' "
                                 "ORDER BY name").fetchall():
            try:
                rows.append((name, repr(c.execute(f'SELECT * FROM "{name}"').fetchall())))
            except sqlite3.OperationalError as e:
                rows.append((name, f"unreadable: {e}"))
    return hashlib.sha256(repr(rows).encode()).hexdigest()


def _tree(root: str) -> list:
    if not root or not os.path.isdir(root):
        return []
    return sorted((str(f), f.stat().st_size, f.stat().st_mtime_ns) for f in Path(root).rglob("*") if f.is_file())


def test_shadow_writes_nothing_anywhere(events, monkeypatch):
    from nucleo.memory_agent.processor import llm
    from nucleo.turn import named_errand
    calls = []
    monkeypatch.setattr(named_errand, "known", lambda **_k: [dict(LISBON)])
    monkeypatch.setattr(llm, "chat_sync", lambda *a, **k: calls.append((a, k)) or FULL)
    handle = _handle(request_type=("order", 0.66))
    before = (_db_digest(), _tree(os.environ.get("ZAELAR_WORKSPACE", "")), copy.deepcopy(handle["result"]),
              sorted(handle))
    payload = {"turn_id": "T-1", "brief": handle, "text": "make the Lisbon hotel Friday", "reply": "On it.",
               "started_at": time.time()}
    ev = run.evaluate(payload)
    assert not ev["why_not"] and calls, f"the gate should have fired and called once: {ev}"
    after = (_db_digest(), _tree(os.environ.get("ZAELAR_WORKSPACE", "")), copy.deepcopy(handle["result"]),
             sorted(handle))
    assert after == before, "a shadow whisper wrote something outside its events"
    assert payload["text"] == "make the Lisbon hotel Friday" and "slot" not in payload
    kinds = {(e["kind"], e["event"]) for e in events}
    assert kinds == {("whisper", "gate"), ("whisper", "slot")}, events
    s = next(e for e in events if e["event"] == "slot")
    assert s["outcome"] == "ok" and s["slot"]["facts"] and s["rendered"], s
    assert "say" not in json.dumps(s["slot"]) and "instructions" not in json.dumps(s["slot"]), s["slot"]


def test_the_model_budget_carries_its_reasoning(monkeypatch):
    """The truncated-200 trap: a reasoner whose `max_tokens` is its reasoning returns empty with no error."""
    from config import models
    row = models.service("whisperer")
    assert row["max_tokens"] >= row["reasoning_budget"] + 400, row
    from nucleo.memory_agent.processor import llm_routes
    assert llm_routes._DEFAULTS["whisperer"][2] is False, "the whisperer reasons: thinking must not be disabled"
    assert llm_routes._DEFAULTS["whisperer"][1] == row["titular"]["model"]


def test_off_starts_nothing(monkeypatch):
    monkeypatch.setenv("ZAELAR_WHISPER", "off")
    assert run.on_turn_closed({"turn_id": "T-off"}) is None


# ── stale, TTL, late, one in flight ─────────────────────────────────────────────────────────────────────────────────

def _fired(events, monkeypatch, made_after: float = 0.0):
    from nucleo.memory_agent.processor import llm
    from nucleo.turn import named_errand
    monkeypatch.setattr(named_errand, "known", lambda **_k: [dict(LISBON)])
    monkeypatch.setattr(llm, "chat_sync", lambda *a, **k: FULL)
    t = time.time()
    assert not run.evaluate({"turn_id": "T-1", "brief": _handle(request_type=("order", 0.66)), "text": "the Lisbon hotel",
                  "started_at": t})["why_not"]
    if made_after:
        run._S["last"]["made_at"] = t + made_after
    return t


def _next(threads, started_at):
    return run.judge_previous({"turn_id": "T-2", "started_at": started_at}, threads)


def test_a_slot_whose_thread_did_not_move_is_fresh(events, monkeypatch):
    t = _fired(events, monkeypatch)
    assert _next([dict(LISBON)], t + 20) == "fresh"


def test_a_mention_made_by_the_consuming_turn_itself_keeps_it_fresh(events, monkeypatch):
    t = _fired(events, monkeypatch)
    assert _next([{**LISBON, "last_mention_ts": int(t + 21)}], t + 20) == "fresh"


def test_a_slot_whose_thread_moved_is_stale(events, monkeypatch):
    t = _fired(events, monkeypatch)
    assert _next([{**LISBON, "state": "running", "waiting_on": ""}], t + 20) == "stale"


def test_a_slot_older_than_its_ttl_expires(events, monkeypatch):
    t = _fired(events, monkeypatch)
    assert _next([dict(LISBON)], t + run.TTL_S + 1) == "expired"


def test_a_slot_that_lands_after_the_next_turn_began_is_late(events, monkeypatch):
    t = _fired(events, monkeypatch, made_after=30)
    assert _next([dict(LISBON)], t + 20) == "late"
    use = [e for e in events if e["event"] == "use"]
    assert use and use[-1]["landed_before_next_turn"] is False, use


def test_a_slot_is_judged_once(events, monkeypatch):
    t = _fired(events, monkeypatch)
    assert _next([dict(LISBON)], t + 20) == "fresh"
    assert _next([dict(LISBON)], t + 25) == ""


def test_one_in_flight_and_no_refire_while_the_thread_has_not_moved(events, monkeypatch):
    from nucleo.memory_agent.processor import llm
    from nucleo.turn import named_errand
    monkeypatch.setattr(named_errand, "known", lambda **_k: [dict(LISBON)])
    release, entered = threading.Event(), threading.Event()

    def slow(*_a, **_k):
        entered.set()
        release.wait(5)
        return FULL
    monkeypatch.setattr(llm, "chat_sync", slow)
    p = {"brief": _handle(request_type=("order", 0.66)), "text": "the Lisbon hotel", "started_at": time.time()}
    th = threading.Thread(target=run.evaluate, args=({**p, "turn_id": "T-1"},))
    th.start()
    assert entered.wait(5)
    assert run.evaluate({**p, "turn_id": "T-2"})["why_not"] == "in_flight"
    release.set()
    th.join(5)
    assert run.evaluate({**p, "turn_id": "T-3"})["why_not"] == "unchanged"
    moved = {**LISBON, "last_mention_ts": 2000}
    monkeypatch.setattr(named_errand, "known", lambda **_k: [moved])
    assert run.evaluate({**p, "turn_id": "T-4"})["why_not"] == ""


# ── the slot and its rendering ──────────────────────────────────────────────────────────────────────────────────────

def test_unparseable_json_is_no_whisper():
    assert slot.parse("I think he wants Friday.", turn_id="T") is None
    assert slot.parse('{"facts": [', turn_id="T") is None


def test_the_slot_keeps_only_declared_fields_and_sourced_facts():
    s = slot.parse(json.dumps({"facts": [{"text": "a", "source": "his_words"}, {"text": "b", "source": "a hunch"},
                                         {"text": "c"}], "advice": "say yes",
                               "task_certainty": {"thread_id": "stranger", "state": "clear"}}),
                   turn_id="T", thread_ids={"t-lisbon"})
    assert s.facts == [{"text": "a", "source": "his_words"}] and s.task_certainty is None
    assert set(s.as_dict()) == {"turn_id", "thread_id", "made_at", "facts", "correction", "missing", "task_certainty"}


def test_the_rendering_has_a_ceiling():
    big = "x" * 400
    s = slot.parse(json.dumps({"facts": [{"text": big, "source": "task"}] * 9,
                               "correction": {"heard": big, "meant": "y" + big, "confidence": 3},
                               "missing": [{"slot": big, "why": big}] * 9,
                               "task_certainty": {"thread_id": "t", "state": "ambiguous", "why": big}}),
                   turn_id="T", thread_ids={"t"})
    out = render.render(s)
    assert out and len(out) <= render.MAX_CHARS and len(out.splitlines()) <= render.MAX_LINES, (len(out), out)
    assert len(render.lines(s)) <= render.MAX_LINES, render.lines(s)
    assert render.render(None) == "" and render.render(slot.Slot()) == ""


def test_the_rendering_is_wired_into_no_prompt():
    """Shadow: nothing outside the whisper package imports it (the prompt builder, the brief, the state message)."""
    offenders = []
    for f in (ENGINE / "nucleo").rglob("*.py"):
        if "whisper" in f.parts:
            continue
        src = f.read_text(encoding="utf-8")
        if "whisper import render" in src or "whisper.render" in src or "whisper import slot" in src:
            offenders.append(str(f.relative_to(ENGINE)))
    assert not offenders, offenders


# ── a hosted deployment runs no shadow call by default ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("where, user, expected", [("", "", "shadow"), ("", "u-123", "off"),
                                                    ("cloud", "", "off"), ("local", "u-123", "shadow")])
def test_the_default_mode_follows_the_deployment(monkeypatch, where, user, expected):
    monkeypatch.delenv("ZAELAR_WHISPER", raising=False)
    monkeypatch.setenv("ZAELAR_DEPLOYMENT", where)
    monkeypatch.setenv("ZAELAR_USER_ID", user)
    assert run.mode() == expected


def test_the_env_still_overrides_the_deployment(monkeypatch):
    monkeypatch.setenv("ZAELAR_USER_ID", "u-123")
    monkeypatch.delenv("ZAELAR_DEPLOYMENT", raising=False)
    monkeypatch.setenv("ZAELAR_WHISPER", "shadow")
    assert run.mode() == "shadow"


def test_an_unreadable_row_still_keeps_a_hosted_deployment_off(monkeypatch):
    monkeypatch.delenv("ZAELAR_WHISPER", raising=False)
    monkeypatch.delenv("ZAELAR_DEPLOYMENT", raising=False)
    monkeypatch.setenv("ZAELAR_USER_ID", "u-123")
    monkeypatch.setattr(run, "_row", lambda: {})
    assert run.mode() == "off"
    monkeypatch.setenv("ZAELAR_USER_ID", "")
    assert run.mode() == "shadow"
