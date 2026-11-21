"""A message is a task of the queue, in the send lane, and the model acts on it by its #number (INI-078 step 6 + S4).

Each message he asks for is ONE row with owner `send` and its `#n`; the draft (who, what it says, what it asked him)
travels in the row, so it outlives a restart. One message at a time: a second one waits, pending, behind the first and
opens when the first leaves. Asking him is `wait`, the connector's receipt archives it (`done`), his no cancels it.
Nothing reads his sentence before the model any more: the model is the one decider, with `draft_edit`, `draft_send`
and `draft_drop` by number — and the owner still decides who a name is and whether a go-ahead counts.
"""
from __future__ import annotations

import asyncio

import pytest

from memory import tasks_store as ts
from nucleo import queue
from nucleo.send import by_number, draft, owner, receipt, row
from tests.agent_headless.unit.send.test_one_owner_holds_a_send_from_his_words_to_the_receipt import World, _read


@pytest.fixture
def world(monkeypatch):
    w = World(monkeypatch)
    yield w
    draft.reset()


def _sends(state: str) -> list[dict]:
    return queue.view()["send"][state]


def _open(world, who="Odile Marsh", text: str | None = "I'm late") -> tuple[draft.Draft, int]:
    world.reads = [_read(who=who, text=text)]
    asyncio.run(owner.intake(f"Tell {who} {text or ''}", {}))
    d = draft.current()
    return d, ts.task_get(d.row)["num"]


def _act(op, n, **args):
    return asyncio.run(by_number.act(op, f"#{n}", args, "w_his words", draft.current().confirm_line
                                     if draft.current() else ""))


def test_a_message_is_one_task_that_waits_for_his_answer_with_the_draft_in_it(world):
    d, n = _open(world)
    (r,) = _sends(queue.WAITING)
    assert r["num"] == n and r["ask"] == d.confirm_line and "I'm late" in r["ask"]
    kept = r["progress"]["draft"]
    assert kept["text"] == "I'm late" and kept["target"]["contact_id"] == "c1" and kept["asked"] == draft.CONFIRM


def test_a_second_message_waits_for_the_first_and_opens_when_it_leaves(world):
    d1, n1 = _open(world, text=None)            # the first still asks him what to say
    assert d1.asked == draft.TEXT
    world.reads = [_read(who="Odile Brandt", text="see you")]
    asyncio.run(owner.intake("and tell Odile Brandt see you", {"contact": "Odile Brandt", "text": "see you"}))
    assert draft.current() is d1 and [r["title"] for r in _sends(queue.PENDING)] == ["✉ Odile Brandt · «see you»"]
    (pending,) = _sends(queue.PENDING)

    async def drop_then_next():
        found, _line = await by_number.act("drop", f"#{n1}", {}, "w_no", "")
        await asyncio.sleep(0)
        for _ in range(100):                    # the next one is opened and asked out of turn
            d = draft.current()
            if d is not None and (ts.task_get(d.row) or {}).get("state") == queue.WAITING:
                break
            await asyncio.sleep(0.01)
        return found
    world.reads = [_read(who="Odile Brandt", text="see you")]
    assert asyncio.run(drop_then_next())
    assert ts.task_get(d1.row) is None, "the first left the queue"
    d2 = draft.current()
    assert d2 is not None and d2.row == pending["id"] and d2.target["contact_id"] == "c2"
    assert ts.task_get(d2.row)["state"] == queue.WAITING


def test_a_restart_with_a_draft_open_leaves_it_waiting_for_his_yes(world):
    d, n = _open(world)
    owner.heard(d.confirm_line)
    draft._open["draft"] = None                 # the process ended: what was in RAM is gone, the row is not
    assert row.restore() == [d.row]
    back = draft.current()
    assert back is not d and back.text == "I'm late" and back.target["contact_id"] == "c1" and back.row == d.row
    assert ts.task_get(d.row)["state"] == queue.WAITING and back.heard is False
    found, line = _act("go", n)
    assert found and not world.sent and "I'm late" in line, "his yes after a restart: the confirmation read again"


def test_the_receipt_archives_the_message(world):
    d, n = _open(world)
    owner.heard(d.confirm_line)
    world.receipt = ("queued", "")

    async def yes_and_receipt():
        found, _line = await by_number.act("go", f"#{n}", {}, "w_yes, send it", d.confirm_line)
        assert ts.task_get(d.row)["phase"] == "sending" and ts.task_get(d.row)["state"] == queue.RUNNING
        world.receipt = ("sent", "")             # the connector's own receipt lands
        await asyncio.gather(*list(receipt.tasks))
        return found
    assert asyncio.run(yes_and_receipt()) and len(world.sent) == 1
    assert ts.task_get(d.row) is None and not any(queue.view()["send"].values())


def test_the_draft_acts_by_number_change_send_or_drop_only_the_open_draft(world):
    d, n = _open(world)
    found, line = _act("edit", n, text="I'm very late")
    assert found and d.text == "I'm very late" and "I'm very late" in line and not world.sent
    assert ts.task_get(d.row)["progress"]["draft"]["text"] == "I'm very late"
    assert _act("go", n)[0] and not world.sent, "a confirmation he has not heard is never answered"
    assert _act("go", n + 7) == (False, "") and _act("drop", 999) == (False, "")
    assert _act("drop", n)[0] and draft.current() is None and ts.task_get(d.row) is None and not world.sent


def test_nothing_reads_his_words_before_the_model_with_a_draft_open(world, monkeypatch):
    from nucleo.conversation_host import routing
    from nucleo.send import read
    _open(world)
    called = []
    monkeypatch.setattr(read, "read", lambda *a, **k: called.append(a) or dict(read.NOTHING))
    monkeypatch.setattr(owner, "take", lambda *a, **k: called.append(a))
    assert asyncio.run(routing.HostRoute().take("acct", "w_yes send it")) is None and called == []
    assert routing.said() == "w_yes send it", "his words are kept for the model's act"
