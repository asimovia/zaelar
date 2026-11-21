"""The `Tools` port's widget door (INI-078 F2 step 2, D-2): ONE generic act, `widget_action(widget, action, payload)` —
one of a widget's DECLARED actions, checked against its manifest, through the door every tap takes
(`data_ops.dispatch_and_report`) on the engine's loop, by the mode the act declares: a `confirm` act asks his yes on its
row through the one asker; a message act goes to the send owner; an act that leaves and is no message is held; an act
whose output lives in its card brings the card. Music and video are widgets like any other: playing is their cards'
own declared actions.
"""
from __future__ import annotations

import asyncio

from conversation.ports import ToolResult
from nucleo.conversation_host.acts import _apply, _not_found, _open


def _offered(base: str) -> dict:
    """The actions a widget offers, by its manifest: the internal ones (the card fires them itself) are never offered."""
    from widgets import runtime
    acts = (runtime.get(base) or {}).get("actions")
    return {n: (a if isinstance(a, dict) else {}) for n, a in (acts or {}).items()
            if isinstance(acts, dict) and not (isinstance(a, dict) and (a.get("internal") is True
                                                                        or a.get("row_verb") is True))}


def _widget_target(args: dict) -> "tuple[str, str, dict] | ToolResult":
    """`(card, action, payload)` for a widget action, checked against its manifest — or the result that says why not.
    A message is its owner's (`send.turn.is_message`) and an act that leaves is held: neither crosses here."""
    from widgets import read as widget_read
    from widgets import brief, effects, instances
    named, action = str(args.get("widget") or "").strip(), str(args.get("action") or "").strip()
    payload = args.get("payload") if isinstance(args.get("payload"), dict) else {}
    wid = widget_read.resolve(named)
    if wid is None:
        return _not_found(named)
    base = wid.split("::", 1)[0]
    offered = _offered(base)
    if action not in offered:
        return ToolResult("failed", {"reason": "no_such_action", "widget": base, "actions": sorted(offered),
                                     "fields": brief._payload_keys(offered, every=True)})
    card = instances.data_target(wid, _open())
    from nucleo.send import turn
    if turn.is_message(card, action, payload):
        return card, action, {**payload, "_message": True}       # a message is its owner's: handed over, below
    if effects.leaves(base, action):
        return ToolResult("refused", {"reason": "held", "widget": base, "action": action,
                                      "why": "it leaves to someone and is not a message: not from here"})
    return card, action, payload


async def _on_engine_loop(coro):
    """A widget's act runs on the engine's loop, where its cards and their processes live (`dispatch._LOOP`); with
    none (a test, a bare host), here."""
    from nucleo import dispatch
    loop = dispatch._LOOP
    if loop is None or not loop.is_running():
        return await coro
    return await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(coro, loop))


def _ask(card: str, action: str, payload: dict) -> ToolResult:
    """An act its widget asks his yes for: the confirm gate's verdict, and the question waiting on its row through
    the one asker (`consent_ask.ask_consent`) — answered by the card's buttons, or by his answer to the row."""
    from nucleo.request import consent_ask
    from widgets import confirm_gate
    d = confirm_gate.decide(card, action, payload) or {}
    if d.get("kind") != "ask":
        return ToolResult("failed", {"reason": d.get("kind") or "not_asked", "said": d.get("sentence", "")})
    row, _ask_id = consent_ask.ask_consent(card, action, payload, d["question"])
    if not row:
        return ToolResult("failed", {"reason": "no_row_to_ask_on"})
    return ToolResult("ok", {"asked": d["question"], "waits_for": "his yes", "widget": card, "action": action})


def _mount(card: str, action: str, src: str) -> None:
    """An act whose output lives in its card (its manifest declares the mount, or that it produces) brings the card."""
    from widgets import effects, producers
    base = card.split("::", 1)[0]
    if effects.carries(base, action, effects.PRESENT_MOUNT) or producers.starts_production(base, action):
        _apply("show", card, src, action=action)


async def widget_act(args: dict, effect_id: str | None) -> ToolResult:
    target = await asyncio.to_thread(_widget_target, args if isinstance(args, dict) else {})
    if isinstance(target, ToolResult):
        return target
    card, action, payload = target
    if payload.pop("_message", False):                       # the send owner asks, and sends only on his yes
        from nucleo.conversation_host import routing
        return await routing.send(payload, act=action)
    from nucleo.flash import frontend                      # the act policy's one public face (its import order)
    from widgets import actions as wactions
    mode = await asyncio.to_thread(frontend.action_mode_now, card, action, payload)
    if mode == wactions.CONFIRM:
        return await asyncio.to_thread(_ask, card, action, payload)
    if mode != wactions.FAST:
        return ToolResult("failed", {"reason": "an_errand", "widget": card, "action": action})
    from nucleo.flash import data_ops
    res = await _on_engine_loop(data_ops.dispatch_and_report(card, action, payload))
    res = res if isinstance(res, dict) else {}
    ok = res.get("ok") is not False and not res.get("error")
    if ok:
        await asyncio.to_thread(_mount, card, action, f"turn:{effect_id or 'widget_action'}")
    return ToolResult("ok" if ok else "rejected", {"widget": card, "action": action, **receipt(card, res, ok)})


#: how much of a card's answer goes back to the model (a list cut to its first items, a text to its first characters)
RECEIPT_ITEMS, RECEIPT_CHARS = 8, 400


def _bounded(v, depth: int = 0):
    if isinstance(v, str):
        return v[:RECEIPT_CHARS]
    if isinstance(v, (int, float, bool)) or v is None:
        return v
    if depth >= 2:
        return str(v)[:RECEIPT_CHARS]
    if isinstance(v, dict):
        return {str(k): _bounded(x, depth + 1) for k, x in list(v.items())[:RECEIPT_ITEMS]}
    if isinstance(v, (list, tuple)):
        return [_bounded(x, depth + 1) for x in list(v)[:RECEIPT_ITEMS]] + (["…"] if len(v) > RECEIPT_ITEMS else [])
    return str(v)[:RECEIPT_CHARS]


def receipt(card: str, res: dict, ok: bool) -> dict:
    """What the card's door answered, back to the model (C4): what it did (`result`, bounded) and, refused, WHY — the
    card's own sentence when it has one (`refusal_line.speakable`), else its reason as the door gave it. Acting blind,
    the model repeated a refused act to its step cap."""
    out = {"result": _bounded({k: v for k, v in res.items() if k not in ("ok", "say", "say_args")})}
    if not ok:
        from nucleo.request import refusal_line
        out["why"] = (refusal_line.speakable(card, res) or str(res.get("error") or res.get("message") or "refused"))[
            :RECEIPT_CHARS]
    return out


