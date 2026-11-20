"""An EAGER end of turn — the ear announcing a sentence it has not confirmed — writes nothing and sends nothing.

The ear's preflight fires the turn's brief early (`eager_brief.on_preflight` → `brief_turn.fire_early`): two reads of
his words, kept in memory for the turn that admits the same sentence. The sentence may still grow, so nothing may ACT
on it: no draft opened or answered, no question, no task, no row, no order to a connector.

Held here, one row per road a message can take, with the state that road would act on already in place — an open
draft waiting for his yes, a task waiting for his answer, an order scheduled for later:
  · the picture of every store (`harness/store_snapshot`) is the same bytes before and after the preflight;
  · no outbound order reaches the bus, and no consequence door is asked;
  · by construction: a preflight is read in ONE place, and the two functions it runs call nothing but the two reads.

Not held here: a turn that the session itself STARTS on a preflight (the transport's preemptive generation, off by
default — pinned below). That turn runs every road for real; making it harmless needs the turn to know it is not yet
confirmed, which is a design of its own.
"""
from __future__ import annotations

import ast
import time
from pathlib import Path

import bus
import pytest

from connectors import exit as door
from connectors.messaging import group_leave, ingest
from tests.agent_headless.harness import store_snapshot

ENGINE = Path(__file__).resolve().parents[4]
_OUT = (ingest.TOPIC_SEND, ingest.TOPIC_REPLY, ingest.TOPIC_GROUP, group_leave.TOPIC_GROUP_LEAVE)

#: One sentence per road, as the ear would announce it: the words that road acts on when a turn admits them.
ROADS = {
    "L1 the owner's draft, his yes": "Yes, send it",
    "L1 a message order": "Send Rowan a message saying I am on my way",
    "L2 an act that leaves and is not a message": "Invite Rowan to Friday's meeting",
    "L3 an order nothing served": "Write to the plumber we called last week",
    "L4 his answer to a waiting row": "The second one",
    "L5 a worker under a mandate": "Go on, answer her whatever she asks",
    "L6 an errand that wakes": "Tell me when she answers",
    "L7 a promise with no call": "Send it to her right now",
    "L8 a message and an errand in one sentence": "Find a table for two and send it to Rowan",
    "a card act that leaves": "Create a group with Rowan called Friday dinner",
}


@pytest.fixture
def world(tmp_path, monkeypatch):
    """Isolated stores with something to act on in each: a draft awaiting his yes, a waiting task, a held order."""
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    from memory import db
    db.reset_db()
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path / "widgets"))
    monkeypatch.delenv(door.ENV, raising=False)
    from widgets.mensajeria import data as md, outbound
    mdb = md.load_db()
    outbound.enqueue(mdb, {"platform": "telegram", "to": "987", "chatId": "987"}, "see you at six", lane=door.OWNER,
                     not_before=time.time() + 3600, scheduled=True)
    store.save("mensajeria", mdb)
    from nucleo.circuit import ledger
    now = int(time.time())
    ledger.store().task_put({"id": "t-wait", "title": "which one", "goal": "ask him which", "kind": "generic",
                             "mode": "once", "state": "waiting", "visible": True, "origin": "turn",
                             "created_at": now, "updated_at": now})
    from nucleo.send import draft
    draft.reset()
    d = draft.start("send Rowan a message")
    d.who, d.text, d.asked = "Rowan", "On my way", draft.CONFIRM
    d.target = {"name": "Rowan Pike", "contact_id": "c1", "platform": "telegram"}
    d.confirm_line, d.heard = "The message for Rowan Pike is ready: «On my way». Shall I send it?", True
    reads = []
    from nucleo.turn import brief
    from voice import attention
    monkeypatch.setattr(brief, "ask_for_turn", lambda text: reads.append(("brief", text)) or {"text": text})
    monkeypatch.setattr(attention, "prefire", lambda text: reads.append(("attention", text)))
    from nucleo.turn import brief_turn
    brief_turn._PREFIRED.clear()
    subs = [bus.subscribe(t) for t in _OUT]
    yield {"reads": reads, "subs": subs}
    for s in subs:
        s.close()
    draft.reset()
    brief_turn._PREFIRED.clear()
    db.reset_db()


@pytest.mark.parametrize("road", sorted(ROADS))
def test_a_preflight_reads_his_words_twice_and_changes_nothing(world, road):
    from nucleo import consequence
    from voice.engine.pipeline import eager_brief
    from widgets.mensajeria.owner.handle import _Handle
    _Handle()._flush_queues()                    # the owner's own beat settles first: its bookkeeping is not the preflight's
    before = store_snapshot.take()
    with consequence.dry_turn() as would:
        eager_brief.on_preflight(ROADS[road])
    after = store_snapshot.take()
    assert store_snapshot.diff(before, after) == [] and before == after
    _Handle()._flush_queues()                    # …and the beat after it finds nothing new to send
    assert all(s.queue.empty() for s in world["subs"]), "no order reached a connector"
    assert not list(would or []), f"a consequence door was asked on an unconfirmed sentence: {would}"
    assert world["reads"] == [("attention", ROADS[road]), ("brief", ROADS[road])], "the two reads, and only them"


def test_the_picture_sees_a_write_in_each_of_its_three_parts(world):
    """The instrument bites: a row, a queued order and an answered draft each change the picture, by name."""
    from nucleo.circuit import ledger
    from nucleo.send import draft
    from widgets import store
    from widgets.mensajeria import data as md, outbound
    before = store_snapshot.take()
    ledger.store().task_patch("t-wait", state="running")
    assert store_snapshot.diff(before, store_snapshot.take()) == ["database/tasks"]
    mid = store_snapshot.take()
    mdb = md.load_db()
    outbound.enqueue_reply(mdb, {"platform": "telegram", "chatId": "987"}, "hello", lane=door.OWNER)
    store.save("mensajeria", mdb)
    assert all(k.startswith("widgets/") for k in store_snapshot.diff(mid, store_snapshot.take()))
    assert store_snapshot.diff(mid, store_snapshot.take())
    last = store_snapshot.take()
    draft._open["draft"].state = draft.SENDING
    assert store_snapshot.diff(last, store_snapshot.take()) == ["memory/draft"]


# ── by construction ────────────────────────────────────────────────────────────────────────────────────────────────
def _calls(path: str, fn: str) -> set[str]:
    tree = ast.parse((ENGINE / path).read_text(encoding="utf-8"))
    node = next(n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == fn)
    out = set()
    for c in ast.walk(node):
        if isinstance(c, ast.Call):
            f = c.func
            out.add(f"{getattr(f.value, 'id', '?')}.{f.attr}" if isinstance(f, ast.Attribute) else getattr(f, "id", "?"))
    return out


def test_the_two_functions_a_preflight_runs_call_only_the_two_reads():
    """A call added to either function is a new thing an unconfirmed sentence does: it is added here, on purpose."""
    assert _calls("voice/engine/pipeline/eager_brief.py", "on_preflight") == {
        "_switch.holds_the_voice", "emit", "_bt.fire_early", "logger.debug"}   # a read: does the manager hold the voice?
    assert _calls("nucleo/turn/brief_turn.py", "fire_early") == {
        "_key", "_attention.prefire", "_PREFIRED.get", "time.time", "brief.ask_for_turn", "_remember_prefired",
        "logger.debug"}


def test_a_preflight_is_read_in_one_place():
    hits = []
    for p in ENGINE.rglob("*.py"):
        rel = p.relative_to(ENGINE).as_posix()
        if rel.startswith(("tests/", ".")) or "/." in rel or ".venv" in rel or "node_modules" in rel:
            continue
        tree = ast.parse(p.read_text(encoding="utf-8"))
        if any(isinstance(n, ast.Attribute) and n.attr == "PREFLIGHT_TRANSCRIPT" for n in ast.walk(tree)):
            hits.append(rel)
    assert hits == ["voice/engine/pipeline/eager_brief.py"]


def test_the_session_does_not_start_a_turn_on_a_preflight_unless_asked_to():
    """The transport's preemptive generation is OFF unless the install turns it on: its default is read off the source."""
    src = (ENGINE / "voice/engine/core/config.py").read_text(encoding="utf-8")
    line = next(ln for ln in src.splitlines() if "preemptive_generation" in ln and "env(" in ln)
    assert 'env("ZAELAR_PREEMPTIVE", "0") == "1"' in line
