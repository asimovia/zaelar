"""«Delete the groups X and "Shopping list"», replayed through the real card (V2-935).

Since V2-938 leaving groups is the message owner's (`nucleo/send/act`): finding them, the one question naming them,
his yes and his no, and the receipt are tested in `tests/agent_headless/unit/send/test_an_act_toward_a_messaging_
platform_has_the_same_owner.py`. What stays here is the card's own resolution and the connector's echo.

What he lived (2026-11-18, 11:19–11:26): no act existed that leaves or deletes a messaging group; the turn's reader
took the nearest one (`dismiss`, which only hides a row here), a generic worker spent six minutes on it, asked him
nothing, verified nothing and never ended. Each station of the path, now:

  · the turn: a sure order whose act LEAVES is handed to ONE worker task with the act's own steps and fields in its
    brief — never a card act run inline, never a generic errand that has to discover how;
  · the exit door: every name is found among HIS groups before anything is asked (a group that is not there is a
    refusal with the candidates, and no question); then ONE question for all of them, naming them as found;
  · his yes: the retained act runs at once — no session resumed — and he hears the one «on it» line of an act
    (never «the message»); the order is queued for each platform's connector;
  · the receipt: only when every chat is gone does the order's row say sent; the engine then says the final line and
    the task's row ends done. Nothing is claimed before it.

The connectors are doubled at the bus (their echo is applied as the card's owner applies it); invented names.
"""
from __future__ import annotations

import json
import queue
from types import SimpleNamespace



UID = "g9-2"
ORDER = "there is a group called Book club and another called Shopping list, delete them"
WA_BOOK, TG_SHOPPING = "120363600112233@g.us", "-100600000311"
CALL = {"widget_id": "mensajeria", "action": "leave_group", "payload": {"groups": ["Book club", "Shopping list"]}}


async def _act(w, action, payload=None):
    out = await w.api.worker_act(task_id="2", token="t", action=action, payload=payload or {})
    return json.loads(out.body)


def _asks(w) -> list:
    return [e for e in w.events if e["kind"] == "ask"]


def _gone(w, platform, chat_id, ref):
    """A connector's echo for one chat, applied as the card's owner applies it."""
    from widgets.mensajeria import owner
    o = owner._Owner()
    o._gone_sub, o._failed_sub = SimpleNamespace(queue=queue.Queue()), SimpleNamespace(queue=queue.Queue())
    o._gone_sub.queue.put({"platform": platform, "ref": ref, "chatIds": [chat_id]})
    o._apply_chats_gone()


def _order_row(w) -> dict:
    return next(r for r in w.md.load_db()["outbox"] if r.get("kind") == "group_leave")


def test_an_end_state_reads_a_call_that_names_several_things():
    """The worker's call names the groups as a LIST; an end state whose blank is that field was unrenderable, so the
    act had no receipt to follow and nothing verified it. Several plain values are told as one, as the row keeps them."""
    from nucleo.circuit import spec
    assert spec._fill({"where": {"said": "{groups}"}}, {"groups": ["Book club", "Shopping list"]}) == \
        {"where": {"said": "Book club, Shopping list"}}
    assert spec._fill({"where": {"said": "{groups}"}}, {"groups": [{"name": "x"}]}) is None, "rows are not plain values"
    assert spec._fill({"where": {"said": "{groups}"}}, {"groups": []}) is None

