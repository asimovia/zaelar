"""The `Tools` port's acts on a widget's LIFE and on pictures (INI-078 F2 step 7), each to the door that already does it:

  build     a widget to build or change: an errand of kind `code` through the one errand gateway — the dispatch door
            asks his yes before a card of his is built or rewritten (C4)
  delete    a widget deleted, and `restore` one back to its shipped version: his yes asked on its ROW through the one
            asker (`consent_ask.ask_consent`, kind `delete`/`restore`); his yes runs it — never here
  alias     a name a widget opens by, added or removed (`widgets.aliases`, its collision guard included)
  images    pictures of something, found and shown in their viewer (`flash.image_turn.voice_turn`)

The questions are the language pack's own lines, the widget resolved by its declared names (`widget_read.resolve`).
"""
from __future__ import annotations

from conversation.ports import ToolResult


def _line(key: str, **kw) -> str:
    from i18n import langs
    return str(getattr(langs.current_language(), key, "") or "").format(**kw)


def _named(args: dict) -> str | None:
    from widgets import read as widget_read
    return widget_read.resolve(str(args.get("widget") or ""))


def _build(args: dict) -> ToolResult:
    from nucleo.acts import errand
    from nucleo.request import kind as _kind
    if not (request := str(args.get("request") or "").strip()):
        return ToolResult("failed", {"reason": "no_request"})
    work = _kind.CHANGE if args.get("change") is True or str(args.get("change")).lower() == "true" else _kind.BUILD
    tid = errand.escalate_to_slowbrain(request, context={       # the model's call is his SURE order (C4): no «shall I?»
        "origin": "conversation", "kind": "code", _kind.KEY: {"choice": work, "confidence": 1.0}, _kind.SURE: True,
        "errand_class": {"choice": "none", "confidence": 1.0}})                 # a card built for him: nothing leaves
    return ToolResult("ok" if tid else "rejected", {"task": tid} if tid else {"reason": "not started"})


def _ask(wid: str, kind: str, question: str) -> ToolResult:
    from nucleo.request import consent_ask
    row, _ask_id = consent_ask.ask_consent(wid, kind, {}, question, text=question, kind=kind)
    if not row:
        return ToolResult("failed", {"reason": "no_row_to_ask_on"})
    return ToolResult("ok", {"asked": question, "waits_for": "his yes"})


def _delete(args: dict) -> ToolResult:
    wid = _named(args)
    if not wid:
        return ToolResult("failed", {"reason": "no_such_widget", "named": args.get("widget")})
    return _ask(wid, "delete", _line("widget_delete_confirm_named", wid=wid))


def _restore(args: dict) -> ToolResult:
    from widgets import lifecycle
    wid = lifecycle.restorable_id(str(args.get("widget") or ""))
    if not wid:
        return ToolResult("failed", {"reason": "nothing_to_restore", "say": _line("widget_restore_nothing")})
    return _ask(wid, "restore", _line("widget_restore_confirm", wid=wid))


def _alias(args: dict) -> ToolResult:
    from widgets import aliases
    wid, alias = _named(args), str(args.get("alias") or "").strip()
    if not wid or not alias:
        return ToolResult("failed", {"reason": "which_widget_or_name"})
    res = (aliases.remove if str(args.get("op") or "") == "remove" else aliases.add)(wid, alias)
    return ToolResult("ok" if res.get("ok") else "failed", {"widget": wid, "alias": alias, **{
        k: v for k, v in res.items() if k != "ok" and isinstance(v, (str, int, bool))}})


def _images(args: dict, src: str = "") -> ToolResult:
    import asyncio

    from nucleo.acts import images as image_turn
    req = image_turn.request_from([{"name": "show_images", "args": args}]) | {"src": src}
    if not req["query"]:
        return ToolResult("failed", {"reason": "no_query"})
    parte, line = asyncio.run(image_turn.voice_turn(req, silent=True))
    ok = bool((parte or {}).get("ok", True))
    return ToolResult("ok" if ok else "failed", {"say": line or "", "query": req["query"]})


DOORS = {f.__name__.lstrip("_"): f for f in (_build, _delete, _restore, _alias, _images)}   # each door by its op


def run(op: str, args: dict, effect_id: str | None = None) -> ToolResult:
    door = DOORS.get(op)
    if door is None:
        return ToolResult("rejected", {"reason": "unknown_door", "op": op})
    args = args if isinstance(args, dict) else {}
    if door is _images:                          # it mounts the viewer: signed with the act's reservation
        return _images(args, src=f"turn:{effect_id or 'show_images'}")
    return door(args)
