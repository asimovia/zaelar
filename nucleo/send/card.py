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

_chain: dict = {}        # draft id → its last view task: the next one waits for it
_painted: dict = {}      # draft id → the text its box last held by the owner's hand or his: anything else was his own
_shown: dict = {}        # draft id → (whom, text) its box was last painted with: the same again paints nothing
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
    if _shown.get(d.id) == (who := (str(sorted(deliver.recipient(d).items())), d.text)) and d.box_key:
        return                                   # its box already shows this draft, to this person
    res = await _run(d, act, {**deliver.recipient(d), "text": d.text})
    _shown[d.id] = who
    key = str(res.get("key") or "") if res.get("ok") is not False else ""
    if key and d.box_key and key != d.box_key:
        await discard_now(d)                     # he changed who it goes to: the old person's box is not his draft
    d.box_key = key or d.box_key
    if (his := str(res.get("replaced") or "")) and his != _painted.get(d.id):   # his own half-written text: kept to
        from nucleo.send import owner                                            # be said first in the next question
        d.box_had = his[:160]
        owner._emit("his text in the box written over", d, his=his[:200])
    _painted[d.id] = d.text


async def lead(d, lead: str = "") -> str:
    """Before the owner's next question: the box painted, and — when that took the place of a text he had begun there
    himself — that fact said first, inside the question itself (never a line of its own after it)."""
    prev = _chain.get(d.id)
    if isinstance(prev, asyncio.Future) and prev.get_loop() is asyncio.get_running_loop() and not prev.done():
        await asyncio.wait({prev})
    try:
        await paint_now(d)
    except Exception as e:  # noqa: BLE001 — the view never decides the send
        _note(e)
    if not (his := d.box_had):
        return lead
    d.box_had = ""
    from nucleo.send import ask
    fact = ask.FACTS["send_box_had"].format(who=(d.target or {}).get("name") or d.who, his=his)
    return f"{fact} {lead}".strip()


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
    from nucleo.send import draft, owner
    from widgets import effects
    if (d := _his_on_the_box(payload)) is None:
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
    return None


def _his_on_the_box(payload: dict):
    """The open draft when this act is his own hand on its box; None for any other lane, box, or no draft."""
    from connectors import exit as door
    from nucleo.send import draft
    d = draft.current()
    key = str(payload.get("key") or payload.get("box_key") or "")
    return d if door.stamped(payload.get("_lane")) == door.HAND and d is not None and d.box_key and key == d.box_key \
        else None


def settle(wid: str, act: str, payload: dict, res) -> None:
    """His Send on the box, once the card answered it: queued, it is his go-ahead by gesture (the card sends it, once);
    held or refused, nothing left — the draft stays open, and why is said in its record."""
    from nucleo.events import vocabulary
    from nucleo.send import draft, owner, receipt
    from widgets import effects
    t = vocabulary.of(effects.event_of(wid, act))
    if t is None or t.owner != "send" or t.direction != vocabulary.OUT or not str(payload.get("ref") or "") \
            or (d := _his_on_the_box(payload)) is None:
        return
    r = res if isinstance(res, dict) else {}
    if r.get("ok") is False or r.get("held") or r.get("error"):     # his text stays in the box: it is the draft's
        if (typed := str(payload.get("text") or "")) and typed != d.text:
            d.text, d.heard, d.confirm_line, _painted[d.id] = typed, False, "", typed
        owner._emit("his Send refused", d, why=str(r.get("message") or r.get("error") or "held")[:200])
        return
    d.text, d.ref, d.box_key = str(payload.get("text") or d.text), str(payload["ref"]), ""   # the card sent it
    __import__("nucleo.send.row", fromlist=["x"]).sending(d)
    draft.close(d, draft.SENDING)
    owner._emit("go-ahead by gesture", d, ref=d.ref)
    receipt.follow_soon(d)


def install_claim() -> None:
    from widgets import owners
    owners.register("send", claim, settle)
