"""The `Tools` port of a switched session: READS only (V2-941, the F1 plan §4.4).

  web_search(query)              `search.find` with the model's proposal and NO judge: the route is the service's
                                 own reading of the proposal, and the turn's classifier is never asked
  read_widget(widget, question)  the widget its name or alias declares: its own answer (`widget_read.lookup`), else
                                 what it holds — with its actions and their fields
  read_state(topic)              one topic of his state `declared.json` declares (`state_topics`), by its reader
  recall(query)                  his memory through `memory.api.query`, with no reinforcement (a read leaves nothing)
  about_self(topic)              the agent's own catalogue entry and the live facts it names
  find_tool(query)               this catalogue, by name

Each class is DERIVED, never listed: a tool's act is a type of the event vocabulary when it has one (leaving → it
leaves, anything else declared → a local write), and a tool with no type is a read only when all it declares is
reading (§1.9). Every door runs in a thread; a failure is a `failed` result the model sees, never an exception in the
loop. Each result carries ONE text evidence (v3.1 §1.10 bis): its id, where it came from, and the figures of its text
as numbers (`figures.py`), so a claim is checked by value against what the read actually returned.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Callable

from conversation.ports import ToolResult, ToolSpec
from conversation.types import EffectClass, Evidence
from nucleo.conversation_host.declared import declared


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


#: name → (schema, core, reads only, what it is for). The purpose is data the model reads (the prefix's READS line and
#: the tool's own description): what each read reaches, never how to behave.
SPECS: dict[str, tuple[dict, bool, bool, str]] = {
    name: (_obj(**{arg: 1 for arg in r["args"]}), r["core"], r["reads"], r["about"])
    for name, r in declared()["reads"].items()}      # declared data (`declared.json`), read once


def catalog() -> list[ToolSpec]:
    return [ToolSpec(name, schema, act="", effect_class=derive("", reads), core=core, about=about)
            for name, (schema, core, reads, about) in SPECS.items()]


def _text_evidence(source: str, data) -> tuple[Evidence, ...]:
    """One evidence for what a read returned: a fresh id, its source, and the figures of its text."""
    from nucleo.conversation_host.figures import figures, percents
    text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, default=str)
    return (Evidence(f"ev_{uuid.uuid4().hex[:12]}", source, numbers=figures(text), percents=percents(text)),)


def _search(args: dict, find: Callable) -> ToolResult:
    res = find(str(args.get("query") or ""), proposal="web_search", judge=None)
    rows = res.source_rows()
    data = {"answer": res.answer, "candidates": res.rows()[:8], "sources": rows[:8], "route": res.route}
    ev = _text_evidence("search:" + ",".join(str(r.get("url") or r.get("name") or "") for r in rows[:4]),
                        {"answer": res.answer, "candidates": data["candidates"]})
    if res.failure:
        return ToolResult("failed", {**data, "failure": res.failure}, ev)
    return ToolResult("ok", data, ev)


def _widget(args: dict) -> ToolResult:
    """The widget its argument names — the catalogue id, else by the names and aliases each manifest declares
    (`widget_read.resolve`) — answering the question, else what it holds."""
    from nucleo.flash import widget_read
    named, q = str(args.get("widget") or ""), str(args.get("question") or "")
    wid = widget_read.resolve(named)
    if wid is None:
        from widgets import runtime
        return ToolResult("failed", {"reason": "no_such_widget", "named": named,
                                     "widgets": sorted(str(w.get("id")) for w in runtime.catalog() if w.get("id"))})
    from nucleo.conversation_host.memory_read import widget_facts
    facts = widget_facts(wid)
    text = widget_read.lookup(wid, q) or facts["holds"]
    return ToolResult("ok" if text or facts["actions"] else "failed",
                      {"widget": wid, "text": text or "nothing readable", "actions": facts["actions"],
                       "fields": facts["fields"]},
                      _text_evidence(f"widget:{wid}", text or ""))


def _topic(args: dict) -> ToolResult:
    """One topic of his state that `declared.json` declares (`state_topics`), read now by its reader."""
    from nucleo.conversation_host import memory_read
    name = str(args.get("topic") or "").strip().lower()
    topics = list(declared()["state_topics"])
    if name not in topics:
        return ToolResult("failed", {"reason": "no_such_topic", "topic": name, "topics": topics})
    text = memory_read.topic(name)
    return ToolResult("ok", {"topic": name, "text": text or "nothing now"}, _text_evidence(f"state:{name}", text))


def _recall(args: dict) -> ToolResult:
    from memory import api as memory
    got = memory.query(str(args.get("query") or ""), reinforce_used=False)
    pills = [{"id": m.get("id"), "text": m.get("text")} for m in got.get("memories") or []]
    return ToolResult("ok", {"memories": pills}, _text_evidence("memory", " · ".join(str(p["text"]) for p in pills)))


def _about(args: dict) -> ToolResult:
    from nucleo.self import about
    e = about.entry(str(args.get("topic") or ""))
    return ToolResult("ok", {"entry": e}, _text_evidence(f"self:{e.get('id')}", e))


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
        return {"read_widget": _widget, "read_state": _topic, "recall": _recall, "about_self": _about,
                "find_tool": _find}.get(name)

    async def call(self, name: str, args: dict, *, effect_id: str | None, idempotency_key: str | None,
                   deadline_mono_ms: int) -> ToolResult:
        door = self._door(name)
        if door is None:
            return ToolResult("rejected", {"reason": "unknown_tool", "tool": name})
        try:
            return await asyncio.to_thread(door, args if isinstance(args, dict) else {})
        except Exception as e:  # noqa: BLE001 — a read that fails is a result the model sees, never a crash
            return ToolResult("failed", {"tool": name, "error": f"{type(e).__name__}: {str(e)[:160]}"})
