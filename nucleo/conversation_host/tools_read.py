"""The `Tools` port of a switched session: READS only (V2-941, the F1 plan §4.4).

  web_search(query)              `search.find` with the model's proposal and NO judge: the route is the service's
                                 own reading of the proposal, and the turn's classifier is never asked
  read_widget(widget, question)  the widget's own answer (`widget_read.lookup`), else what it holds (`read`)
  recall(query)                  his memory through `memory.api.query`, with no reinforcement (a read leaves nothing)
  about_self(topic)              the agent's own catalogue entry and the live facts it names
  find_tool(query)               this catalogue, by name

Each class is DERIVED, never listed: a tool's act is a type of the event vocabulary when it has one (leaving → it
leaves, anything else declared → a local write), and a tool with no type is a read only when all it declares is
reading (§1.9). Every door runs in a thread; a failure is a `failed` result the model sees, never an exception in the
loop. Each result carries its evidence: one per source, structured (entity, metric, value) only where the door
returned structure — a figure from an unstructured read binds no claim.
"""
from __future__ import annotations

import asyncio
from typing import Callable

from conversation.ports import ToolResult, ToolSpec
from conversation.types import EffectClass, Evidence


def derive(act: str, reads_only: bool) -> EffectClass:
    """The class of a tool from what it declares (§1.9)."""
    if act:
        from nucleo.events import vocabulary
        t = vocabulary.of(act)
        if t is not None:
            return EffectClass.LEAVES if t.direction == vocabulary.OUT else EffectClass.WRITE
    return EffectClass.READ if reads_only else EffectClass.WRITE


def _obj(**props) -> dict:
    return {"type": "object", "required": list(props), "properties": {k: {"type": "string"} for k in props}}


#: name → (schema, core, reads only)
SPECS: dict[str, tuple[dict, bool, bool]] = {
    "web_search": (_obj(query=1), True, True),
    "read_widget": (_obj(widget=1, question=1), False, True),
    "recall": (_obj(query=1), False, True),
    "about_self": (_obj(topic=1), False, True),
    "find_tool": (_obj(query=1), True, True),
}


def catalog() -> list[ToolSpec]:
    return [ToolSpec(name, schema, act="", effect_class=derive("", reads), core=core)
            for name, (schema, core, reads) in SPECS.items()]


def _search(args: dict, find: Callable) -> ToolResult:
    res = find(str(args.get("query") or ""), proposal="web_search", judge=None)
    rows = res.source_rows()
    ev = tuple(Evidence(f"ev_search_{i}", str(r.get("url") or r.get("source") or "")) for i, r in enumerate(rows))
    data = {"answer": res.answer, "sources": rows[:8], "route": res.route}
    if res.failure:
        return ToolResult("failed", {**data, "failure": res.failure}, ev)
    return ToolResult("ok", data, ev)


def _widget(args: dict) -> ToolResult:
    from nucleo.flash import widget_read
    wid, q = str(args.get("widget") or ""), str(args.get("question") or "")
    text = widget_read.lookup(wid, q) or widget_read.read(wid)
    return ToolResult("ok" if text else "failed", {"widget": wid, "text": text or "nothing readable"},
                      (Evidence(f"ev_widget_{wid}", f"widget:{wid}"),))


def _recall(args: dict) -> ToolResult:
    from memory import api as memory
    got = memory.query(str(args.get("query") or ""), reinforce_used=False)
    pills = [{"id": m.get("id"), "text": m.get("text")} for m in got.get("memories") or []]
    return ToolResult("ok", {"memories": pills}, tuple(Evidence(f"ev_mem_{p['id']}", "memory") for p in pills))


def _about(args: dict) -> ToolResult:
    from nucleo.self import about
    e = about.entry(str(args.get("topic") or ""))
    return ToolResult("ok", {"entry": e}, (Evidence(f"ev_self_{e.get('id')}", "self"),))


def _find(args: dict) -> ToolResult:
    q = str(args.get("query") or "").strip().lower()
    return ToolResult("ok", {"tools": [n for n in SPECS if not q or q in n]})


class ReadTools:
    """`find` is the search service's door (injected in tests: nothing here leaves the machine by itself)."""

    def __init__(self, find: Callable | None = None) -> None:
        self._find = find

    def catalog(self) -> list[ToolSpec]:
        return catalog()

    def _door(self, name: str) -> Callable[[dict], ToolResult] | None:
        if name == "web_search":
            find = self._find
            if find is None:
                import search
                find = search.find
            return lambda a: _search(a, find)
        return {"read_widget": _widget, "recall": _recall, "about_self": _about, "find_tool": _find}.get(name)

    async def call(self, name: str, args: dict, *, effect_id: str | None, idempotency_key: str | None,
                   deadline_mono_ms: int) -> ToolResult:
        door = self._door(name)
        if door is None:
            return ToolResult("rejected", {"reason": "unknown_tool", "tool": name})
        try:
            return await asyncio.to_thread(door, args if isinstance(args, dict) else {})
        except Exception as e:  # noqa: BLE001 — a read that fails is a result the model sees, never a crash
            return ToolResult("failed", {"tool": name, "error": f"{type(e).__name__}: {str(e)[:160]}"})
