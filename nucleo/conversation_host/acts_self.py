"""The `Tools` port's acts on the agent ITSELF (INI-078 F2 step 6): its name and how it listens, his standing rules
and style, and its own controls — each to the door that already does it, never rebuilt here.

  rename     `turn.identity.apply_rename_now` + `persist_rename`: the wake word tracks the new name at once
  attention  `turn.identity.persist_attention_mode`, among the modes the attention module declares
  rule       `flash.style_directive.write_rule`: his words shaped ONCE into rows of the one rules table (a style knob,
             a rule for a widget, a channel or a person) — nothing held only in the session
  controls   `acts.self_controls.apply`: the screen's own button door (🔊, volume, mic, ⏻, voice, face, camera) by
             its closed vocabulary of acts; a one-way act's line says the button is the way back

What changes who the agent is or how it speaks reaches the model's prefix at once: the live conversation's prefix is
built again (`prefix.current`), so the next run reads the name and the style as they stand.
"""
from __future__ import annotations

from conversation.ports import ToolResult


def _refresh() -> None:
    """The live conversation's prefix built again: the name, the attention and the style as they stand now."""
    from nucleo.conversation_host import boot, prefix, sessions
    rt = sessions.get(boot.account())
    conv = getattr(rt, "conv", None)
    if conv is not None:
        conv.prefix = prefix.current(conv.tools.catalog())


def _rename(args: dict) -> ToolResult:
    import asyncio

    from nucleo.turn import identity
    name = str(args.get("name") or "").strip()
    if not name:
        return ToolResult("failed", {"reason": "no_name"})
    identity.apply_rename_now(name)
    asyncio.run(identity.persist_rename(name))
    _refresh()
    return ToolResult("ok", {"named": name})


def _attention(args: dict) -> ToolResult:
    import asyncio

    from nucleo.turn import identity
    from voice import attention
    mode = str(args.get("mode") or "").strip().lower()
    modes = list(attention._VALID_MODES)
    if mode not in modes:
        return ToolResult("failed", {"reason": "no_such_mode", "modes": modes})
    asyncio.run(identity.persist_attention_mode(mode))
    _refresh()
    return ToolResult("ok", {"attention": mode})


def _rule(args: dict) -> ToolResult:
    import asyncio

    from nucleo.conversation_host import routing
    from nucleo.flash import style_directive
    from voice.observer import emit
    directive = str(args.get("rule") or "").strip()
    if not directive:
        return ToolResult("failed", {"reason": "no_rule"})
    res = asyncio.run(style_directive.write_rule(directive, routing.said() or directive, emit, speak=False))
    _refresh()
    if not res:
        return ToolResult("failed", {"reason": "the rule could not be written"})
    return ToolResult("ok", {"say": str(res.get("line") or ""), "stored": len(res.get("stored") or []),
                             "removed": len(res.get("removed") or [])})


def _controls(args: dict) -> ToolResult:
    from nucleo.acts import self_controls
    from voice.observer import emit
    act, value = args.get("act"), args.get("value")
    if not self_controls.apply(act, emit, src="conversation", value=value):
        return ToolResult("failed", {"reason": "no_such_control", "acts": list(self_controls.ACTS)})
    return ToolResult("ok", {"done": self_controls.canon(act), "say": self_controls.said(act, value),
                             "one_way": self_controls.one_way(act)})


DOORS = {f.__name__.lstrip("_"): f for f in (_rename, _attention, _rule, _controls)}   # each door by its op


def run(op: str, args: dict) -> ToolResult:
    door = DOORS.get(op)
    if door is None:
        return ToolResult("rejected", {"reason": "unknown_door", "op": op})
    return door(args if isinstance(args, dict) else {})
