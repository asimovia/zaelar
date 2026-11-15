"""A pending order wakes every polling connector, and only while its link is up (`connectors/messaging/ingest.nap`).

The email connector's nap was already cut short by an on-demand order (`test_an_on_demand_mail_order_wakes_the_poll`);
WhatsApp and Telegram slept their whole interval with a send queued. Now the three share ONE nap: it returns the
moment one of the inboxes it is handed holds an order, and sleeps the whole interval on an empty tuple. WhatsApp and
Telegram hand it their send/reply/history inboxes only while connected — a queue nothing drains would wake every nap.

Disarm (seen red, in memory): the nap made blind to its inboxes (`pending` never read) → the wake test goes red.
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import time

import pytest

from connectors.messaging import ingest


class _Inbox:
    def __init__(self, has=False):
        self.has = has

    def pending(self):
        return self.has


def _woken_after(total, inboxes, arrive_at=0.2, flip=None):
    async def run():
        async def arrive():
            await asyncio.sleep(arrive_at)
            if flip is not None:
                flip.has = True
        t = time.monotonic()
        await asyncio.gather(ingest.nap(total, inboxes), arrive())
        return time.monotonic() - t
    return asyncio.run(run())


def test_the_shared_nap_wakes_when_an_inbox_holds_an_order():
    send = _Inbox()
    assert _woken_after(20, (None, send, _Inbox()), flip=send) < 2.0


def test_an_order_already_pending_returns_at_once():
    t = time.monotonic()
    asyncio.run(ingest.nap(20, (_Inbox(True),)))
    assert time.monotonic() - t < 0.2


def test_on_an_empty_tuple_it_sleeps_the_whole_interval():
    t = time.monotonic()
    asyncio.run(ingest.nap(1.0, ()))
    assert time.monotonic() - t >= 0.95


def test_with_nothing_pending_it_sleeps_the_whole_interval():
    t = time.monotonic()
    asyncio.run(ingest.nap(1.0, (_Inbox(), None)))
    assert time.monotonic() - t >= 0.95


def _nap_call(module, fn_name):
    tree = ast.parse(inspect.getsource(module))
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == fn_name)
    calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "nap" and getattr(n.func.value, "id", "") == "ingest"]
    sleeps = [ast.unparse(n) for n in ast.walk(fn) if isinstance(n, ast.Call) and ast.unparse(n.func) == "asyncio.sleep"]
    return calls, sleeps


@pytest.mark.parametrize("name,interval,inboxes,gate", [
    ("whatsapp", "config.poll_interval()", {"_send_inbox", "_reply_inbox", "_history_inbox"}, "connected"),
    ("telegram", "config.batch_interval()", {"_send_inbox", "_reply_inbox", "_history_inbox", "_fetch_inbox"},
     "_client.is_connected()"),
])
def test_the_loop_naps_on_its_send_inboxes_only_while_connected(name, interval, inboxes, gate):
    import importlib
    module = importlib.import_module(f"connectors.{name}.service")
    calls, sleeps = _nap_call(module, "_loop")
    assert len(calls) == 1, f"{name}: the loop's tick waits on the shared nap once"
    total, handed = calls[0].args
    assert ast.unparse(total) == interval
    assert isinstance(handed, ast.IfExp), f"{name}: the inboxes are handed only while connected"
    assert ast.unparse(handed.test) == gate
    assert {ast.unparse(e) for e in handed.body.elts} == inboxes
    assert isinstance(handed.orelse, ast.Tuple) and not handed.orelse.elts, "not connected: nothing wakes the nap"
    assert not any(interval in s for s in sleeps), f"{name}: the interval is still slept blind"


def test_the_mail_connector_naps_on_the_shared_seam():
    from connectors.email import service
    src = inspect.getsource(service._nap)
    assert "ingest.nap(total, _on_demand())" in src


def test_disarmed_a_nap_blind_to_its_inboxes_turns_the_wake_red(monkeypatch):
    """Disarm: the nap's inboxes are never read (handed an empty tuple) → it sleeps through the order."""
    real = ingest.nap
    monkeypatch.setattr(ingest, "nap", lambda total, inboxes: real(min(total, 2.5), ()))
    with pytest.raises(AssertionError):
        test_the_shared_nap_wakes_when_an_inbox_holds_an_order()
