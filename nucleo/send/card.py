"""The open message's view in its card (C2 A2): ONE draft, the send owner's, and the card's box shows it.

The owner paints its draft into the box of the person it goes to once it has a person and a text, again whenever his
words change either, and takes it away when the draft ends — cancelled, idle, replaced, failed, or sent and its
receipt read. Only doors that already exist: the card's own acts for a message being written (read by their declared
event type, `widgets.effects.acts_of`, never by name), through the one funnel of outside mutations
(`widgets.server_api._dispatch`) on the owner's lane, on the engine's loop. One draft's paints and discards run one
after another, so a discard never runs before the paint it takes away.
"""
from __future__ import annotations

import asyncio

from loguru import logger

WRITE, DISCARD = "messaging.draft_write", "messaging.draft_discard"
#: the owner's steps after which its draft is painted again (`owner._emit`)
PAINTS = frozenset({"opened", "taken", "asked"})

_chain: dict = {}        # draft id → its last view task: the next one waits for it
_tasks: set = set()


def _note(e: Exception) -> None:
    logger.debug(f"send.card: {type(e).__name__}: {e}")


def _base(d) -> str:
    return str(getattr(d, "widget", "") or "").split("::", 1)[0]


def _act(d, event: str) -> str:
    from widgets import effects
    acts = effects.acts_of(_base(d), event)
    return acts[0] if acts else ""


async def _run(d, act: str, payload: dict) -> dict:
    from nucleo.send import deliver
    from widgets import server_api
    res = await server_api._dispatch(_base(d), act, {**payload, **deliver.lane()})      # the owner's own lane
    return res if isinstance(res, dict) else {}


async def paint_now(d) -> None:
    """Write the draft into its person's box (a message with a person and a text); a box of another person it was
    painted in before is taken away."""
    if getattr(d, "kind", "message") != "message" or not (d.target and d.text) or not (act := _act(d, WRITE)):
        return
    from nucleo.send import deliver
    res = await _run(d, act, {**deliver.recipient(d), "text": d.text})
    key = str(res.get("key") or "") if res.get("ok") is not False else ""
    if key and d.box_key and key != d.box_key:
        await discard_now(d)                     # he changed who it goes to: the old person's box is not his draft
    d.box_key = key or d.box_key


async def discard_now(d) -> None:
    if not d.box_key or not (act := _act(d, DISCARD)):
        return
    key, d.box_key = d.box_key, ""
    await _run(d, act, {"key": key})


def _soon(d, make) -> None:
    """Run `make()` after the draft's last view task, on the running loop, else the engine's, else here."""
    prev = _chain.get(d.id)

    async def step():
        if prev is not None:
            try:
                await (prev if isinstance(prev, asyncio.Future) else asyncio.wrap_future(prev))
            except Exception as e:  # noqa: BLE001 — a failed paint never stops the next view
                _note(e)
        try:
            await make()
        except Exception as e:  # noqa: BLE001 — the view never decides the send
            _note(e)
    try:
        t = asyncio.get_running_loop().create_task(step())
        _tasks.add(t)
        t.add_done_callback(_tasks.discard)
    except RuntimeError:
        from nucleo import dispatch
        loop = dispatch._LOOP
        if loop is None or not loop.is_running():
            return asyncio.run(step())
        t = asyncio.run_coroutine_threadsafe(step(), loop)
    _chain[d.id] = t


def paint(d) -> None:
    _soon(d, lambda: paint_now(d))


def discard(d) -> None:
    _soon(d, lambda: discard_now(d))


def ended(d, state: str) -> None:
    """A draft ended: its box is taken away — unless it was SENT, whose box goes once its receipt is read
    (`receipt.follow`), or it is going out later from that very box."""
    from nucleo.send import draft
    if state != draft.SENT and d.box_key:
        discard(d)
    elif state != draft.SENT:
        _chain.pop(d.id, None)


def install() -> None:
    from nucleo.send import draft
    draft.on_end(ended)
