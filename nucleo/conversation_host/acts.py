"""The `Tools` port's local ACTS (INI-078 F2 step 1): an act the gateway reserved, carried to the door that already does
it — never rebuilt here.

Which acts exist, what each is for, its arguments and the door it goes to are declared data (`declared.json`, `acts`),
as the reads are; its class is DERIVED from its declared `act` (`tools_read.derive`): a local act is a write, and one
whose act is a leaving type of the event vocabulary would be refused by the gateway as held. Nine doors:

  canvas  `nucleo.acts.canvas.apply` — show, close, minimize, full screen, arrange — with the provenance `turn:<effect>`
          (the arbiter's «turn-owned» branch: the model's order on his sealed entry is the decision, no licence ladder)
  panel   the `panel` event the side panel obeys, on one of the tabs its schema declares (the panel is no widget)
  widget  ONE generic act (D-2, `acts_widget.py`): one of a widget's DECLARED actions, checked against its manifest, by the door
          every tap takes (`data_ops.dispatch_and_report`) on the engine's loop, by the mode the act declares — a
          `confirm` act asks his yes on its row through the one asker; a message act goes to the send owner; music and
          video are widgets like any other,
          their play, pause and load their cards' own actions. An act whose output lives in its card brings the card
  task    his errands: start, resume, reopen, stop, unschedule, sign in (`acts_tasks.py`)
  send    a message: handed to the send owner with his words (`routing.send`), who asks and sends only on his yes
  self    its name, how it listens, his rules and style, its own controls (`acts_self.py`)
  life    a widget built, deleted, restored or named, and pictures shown (`acts_life.py`)
  network his clusters and his friends' agents: join (asked), write, a collaboration's goal, share (`acts_network.py`)
  memory  a pill of his memory forgotten or corrected by its id (`acts_memory.py`)

The widget an act names is resolved against the CATALOGUE — every manifest, by id, name or declared alias
(`widgets.runtime`) — and narrowed to the card open on screen (`widgets.instances`): a widget nobody wrote code for is
covered as soon as it is installed. What cannot be resolved is a `failed` result naming what there is, never a guess;
two cards of one widget open is a question. A message never crosses here (`nucleo.send.turn.is_message`): its owner is
the send door.
"""
from __future__ import annotations

import asyncio

from conversation.ports import ToolResult, ToolSpec
from nucleo.conversation_host import tools_read
from nucleo.conversation_host.declared import declared

ACTS: dict[str, dict] = dict(declared()["acts"])      # declared data, read once


def _owned_choices(path: str) -> list[str]:
    """The values an argument's OWNER declares (`module:attribute[.key]`): a tuple of `(value, meaning)` pairs, or a
    dict's keys — read from the owner, never copied into this file's data."""
    import importlib
    mod, _sep, attr = path.partition(":")
    obj = importlib.import_module(mod)
    for part in attr.split("."):
        obj = obj[part] if isinstance(obj, dict) else getattr(obj, part)
    return [str(v[0]) if isinstance(v, (tuple, list)) else str(v) for v in obj]


def _schema(a: dict) -> dict:
    """An act's schema, its arguments' `choices` filled from the modules that own them (`enum`)."""
    if not a.get("choices"):
        return a["schema"]
    import copy
    schema = copy.deepcopy(a["schema"])
    for arg, path in a["choices"].items():
        schema["properties"][arg]["enum"] = _owned_choices(path)
    return schema


def catalog() -> list[ToolSpec]:
    return [ToolSpec(name, _schema(a), act=a["act"], effect_class=tools_read.derive(a["act"], False), about=a["about"])
            for name, a in ACTS.items()]


def _open() -> list[str]:
    from server.voice_api import open_instances
    return [str(i) for i in open_instances() if str(i)]


def _resolve(name: str, open_ids: list[str], *, named_only: bool) -> dict:
    """The widget a name means: `{"id"}`, `{"system"}` (a surface of the side panel), `{"ask": [ids]}` or `{}`."""
    from widgets import runtime
    n = str(name or "").strip()
    if not n:
        return {}
    if runtime.get(n.split("::", 1)[0].lower()) is not None:
        return {"id": n if "::" in n else n.lower()}
    if named_only:
        wid = runtime.identify_named(n, open_ids=open_ids)
        if wid:
            return {"id": wid}
    got = runtime.identify(n, open_ids=open_ids) or {}
    if got.get("match") and not named_only:
        return {"id": str(got["match"])}
    if got.get("system"):
        return {"system": str(got["system"])}
    asks = [str(c.get("id") if isinstance(c, dict) else c) for c in got.get("candidates") or []] \
        if got.get("ambiguous") else []
    return {"ask": [a for a in asks if a]} if any(asks) else {}


def _card(base: str, open_ids: list[str]) -> dict:
    """The card on screen for a widget: its one open instance, the base when none; two open is a question."""
    from widgets import instances
    if "::" in base:
        return {"id": base}
    live = instances.instances_of(base, open_ids)
    return {"id": live[0]} if len(live) == 1 else ({"ask": live} if len(live) > 1 else {"id": base})


def _front(open_ids: list[str]) -> str:
    from nucleo import canvas_focus
    return canvas_focus.last_turn_card(open_ids) or (open_ids[0] if len(open_ids) == 1 else "")


def _catalogue_ids() -> list[str]:
    from widgets import runtime
    return sorted(str(w.get("id")) for w in runtime.catalog() if w.get("id"))


def _not_found(name: str) -> ToolResult:
    return ToolResult("failed", {"reason": "no_such_widget", "named": name, "widgets": _catalogue_ids()})


def _which(ids: list[str]) -> ToolResult:
    return ToolResult("failed", {"reason": "which_one", "candidates": ids})


def _apply(op: str, wid: str, src: str, **extra) -> ToolResult:
    from nucleo.acts import canvas
    if canvas.apply(op, wid, src=src, **extra):
        return ToolResult("ok", {"op": op, "widget": wid or None})
    return ToolResult("rejected", {"op": op, "widget": wid or None, "reason": "the canvas door refused it"})


def _panel(action: str, tab: str, src: str, connector: str = "") -> ToolResult:
    from voice.observer import emit
    emit("panel", action, extra={"tab": tab, "src": src, **({"connector": connector} if connector else {})})
    return ToolResult("ok", {"panel": tab, "action": action, **({"connector": connector} if connector else {})})


def _canvas(op: str, args: dict, src: str) -> ToolResult:
    if op == "arrange":
        return _apply("arrange", "", src)
    open_ids = _open()
    name = str(args.get("widget") or "").strip()
    if op == "show":
        got = _resolve(name, open_ids, named_only=True)
        if got.get("system"):
            from nucleo.self import catalogs
            tab = catalogs.wall_tab_for(got["system"], name)
            return _panel("open", tab, src) if tab else _not_found(name)
        if got.get("ask"):
            return _which(got["ask"])
        if not got.get("id"):
            return _not_found(name)
        from widgets import instances
        return _apply("show", instances.show_id(got["id"], open_ids), src)
    if op == "fullscreen" and str(args.get("mode") or "") == "off":
        from nucleo.acts import show_target
        got = _resolve(name, open_ids, named_only=False) if name else {"id": show_target.at_full_screen()}
        if got.get("ask"):
            return _which(got["ask"])
        return _apply("fullscreen", str(got.get("id") or ""), src, on=False)   # no id: whichever covers the screen
    got = _resolve(name, open_ids, named_only=False) if name else {"id": _front(open_ids)}
    if got.get("ask"):
        return _which(got["ask"])
    if not got.get("id"):                    # never an empty id: a close with none closes EVERY card
        return _not_found(name) if name else _which(open_ids)
    card = _card(got["id"], open_ids)
    if card.get("ask"):
        return _which(card["ask"])
    if op == "close":
        return _apply("minimize" if str(args.get("mode") or "") == "minimize" else "close", card["id"], src)
    if card["id"] not in open_ids:
        _apply("show", card["id"], src)      # full screen over a closed widget opens it first, as the old path did
    return _apply("fullscreen", card["id"], src, on=True)


def _choices(spec: dict, arg: str) -> list[str]:
    """The values an act's argument declares (its schema's `enum`)."""
    return list(((spec.get("schema") or {}).get("properties") or {}).get(arg, {}).get("enum") or [])


def _a_message(args: dict, op: str) -> bool:
    from nucleo.send import turn
    return turn.is_message(str(args.get("widget") or ""), op, args)


def run(name: str, args: dict, effect_id: str | None) -> ToolResult:
    """One reserved act at its door. `effect_id` is its reservation: the act's provenance on the canvas."""
    spec = ACTS.get(name)
    if spec is None:
        return ToolResult("rejected", {"reason": "unknown_tool", "tool": name})
    args = args if isinstance(args, dict) else {}
    if _a_message(args, spec["op"]):
        return ToolResult("rejected", {"reason": "a message is its owner's", "tool": name})
    src = f"turn:{effect_id or name}"
    if spec["door"] in ("widget", "task", "send", "self", "life", "network", "memory"):   # their own doors, awaited by `HostTools.call`
        return ToolResult("rejected", {"reason": "not a canvas or panel act", "tool": name})
    if spec["door"] == "panel":
        from nucleo.self import catalogs
        action = "close" if str(args.get("action") or "") == "close" else "open"
        tab, tabs = str(args.get("panel") or "").strip().lower(), _choices(spec, "panel")
        if tab not in tabs:                      # the declared tabs are the only ones: never a guess at another
            return ToolResult("failed", {"reason": "no_such_tab", "panel": tab, "tabs": tabs})
        cx = catalogs.canon_connector(args.get("connector")) if args.get("connector") and action == "open" else ""
        return _panel(action, tab, src, cx)
    return _canvas(spec["op"], args, src)


class HostTools:
    """The switched session's `Tools`: the reads (`tools_read.ReadTools`) and the local acts, ONE catalogue."""

    def __init__(self, reads: tools_read.ReadTools | None = None) -> None:
        self._reads = reads or tools_read.ReadTools()

    def catalog(self) -> list[ToolSpec]:
        return self._reads.catalog() + catalog()

    async def call(self, name: str, args: dict, *, effect_id: str | None, idempotency_key: str | None,
                   deadline_mono_ms: int) -> ToolResult:
        """Every act runs in the trace of the turn in course (`turns.current`): what it starts — an errand, a send —
        carries the order's flow, never a flow of its own (R-1)."""
        from nucleo.conversation_host import turns
        from voice import trace
        from nucleo.conversation_host import route
        tid = turns.current()
        if not tid:
            got = await self._call(name, args, effect_id=effect_id, idempotency_key=idempotency_key,
                                   deadline_mono_ms=deadline_mono_ms)
        else:
            with trace.scope(tid):
                got = await self._call(name, args, effect_id=effect_id, idempotency_key=idempotency_key,
                                       deadline_mono_ms=deadline_mono_ms)
        route.acted(name, args if isinstance(args, dict) else {}, getattr(got, "status", ""),   # S1: what it did
                    getattr(got, "data", None))
        return got

    async def _call(self, name: str, args: dict, *, effect_id: str | None, idempotency_key: str | None,
                    deadline_mono_ms: int) -> ToolResult:
        if name not in ACTS:
            return await self._reads.call(name, args, effect_id=effect_id, idempotency_key=idempotency_key,
                                          deadline_mono_ms=deadline_mono_ms)
        try:
            if ACTS[name]["door"] == "widget":
                from nucleo.conversation_host.acts_widget import widget_act
                return await widget_act(args, effect_id)
            if ACTS[name]["door"] == "send":
                from nucleo.conversation_host import routing
                a = args if isinstance(args, dict) else {}
                return await (routing.send(a) if ACTS[name]["op"] == "intake" else routing.draft(ACTS[name]["op"], a))
            if ACTS[name]["door"] == "network":
                from nucleo.conversation_host import acts_network
                return await acts_network.run(ACTS[name]["op"], args)
            if ACTS[name]["door"] == "memory":
                from nucleo.conversation_host import acts_memory
                return await asyncio.to_thread(acts_memory.run, ACTS[name]["op"], args)
            if ACTS[name]["door"] == "life":
                from nucleo.conversation_host import acts_life
                return await asyncio.to_thread(acts_life.run, ACTS[name]["op"], args)
            if ACTS[name]["door"] == "self":
                from nucleo.conversation_host import acts_self
                return await asyncio.to_thread(acts_self.run, ACTS[name]["op"], args)
            if ACTS[name]["door"] == "task":
                from nucleo.conversation_host import acts_tasks
                return await asyncio.to_thread(acts_tasks.run, ACTS[name]["op"], args)
            return await asyncio.to_thread(run, name, args, effect_id)
        except Exception as e:  # noqa: BLE001 — an act whose door raised: we do not know it went, the gateway says so
            return ToolResult("unknown", {"tool": name, "error": f"{type(e).__name__}: {str(e)[:160]}"})
