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
_painted: dict = {}      # draft id → the text its box last held by the owner's hand or his: anything else was his own
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
    if (his := str(res.get("replaced") or "")) and his != _painted.get(d.id):   # his own half-written text: said
        from nucleo.send import owner, receipt
        owner._emit("his text in the box written over", d, his=his[:200])
        await receipt._say(d, "send_box_had", his=his[:160])
    _painted[d.id] = d.text


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
    from nucleo.send import draft, steps
    draft.on_end(ended)
    draft.on_end(steps.ended)
    install_claim()


# ── C2 A3 · his hand on the box of the open draft is the owner's ───────────────────────────────────────────────────
def claim(wid: str, act: str, payload: dict) -> dict | None:
    """His own hand on the box of the open draft (the card's buttons, never the model nor the owner): what he typed
    is the draft's text, his Send is his go-ahead by gesture, his Discard drops it. The card does the act as always
    (None); an act on another box, by another lane or with no draft open is not the owner's."""
    from connectors import exit as door
    from nucleo.events import vocabulary
    from nucleo.send import draft, owner, receipt
    from widgets import effects
    d = draft.current()
    key = str(payload.get("key") or payload.get("box_key") or "")
    if door.stamped(payload.get("_lane")) != door.HAND or d is None or not d.box_key or key != d.box_key:
        return None
    event = effects.event_of(wid, act)
    if event == WRITE:
        d.text, d.heard, d.confirm_line = str(payload.get("text") or ""), False, ""   # his words: asked about anew
        _painted[d.id] = d.text
        draft.touch(d)
        owner._emit("edited by hand", d)
    elif event == DISCARD:
        d.box_key = ""                           # his hand takes the box away itself
        draft.close(d, draft.CANCELLED)
        owner._emit("dropped by hand", d)
    elif (t := vocabulary.of(event)) is not None and t.owner == "send" and t.direction == vocabulary.OUT \
            and str(payload.get("ref") or ""):
        d.text, d.ref, d.box_key = str(payload.get("text") or d.text), str(payload["ref"]), ""   # the card sends it
        draft.close(d, draft.SENDING)
        owner._emit("go-ahead by gesture", d, ref=d.ref)
        receipt.follow_soon(d)
    return None


def install_claim() -> None:
    from widgets import owners
    owners.register("send", claim)
