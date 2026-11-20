"""The `Memory` port of a switched session (V2-941, the F1 plan §4.7, v3.1 B4): it reads the state the way the rest of
the engine reads it, and writes nothing.

  state_blocks   what is OPEN first (the TASKS running or waiting, the message DRAFT), the next DAYS by date beside NOW,
                 the widget in FRONT (at full screen, in front on a phone, the only one open, else the newest opened)
                 with its actions, their fields and what it holds, STATE (what the memory knows that is not the
                 conversation, as facts with plain labels) and the WIDGETS' short index (id and mission from each
                 manifest, which are open, used lately). Everything else is READ when the model names it: another
                 widget by `read_widget`, the rest by `read_state(topic)` over the topics `declared.json` declares
                 (`state_topics`). No copy of the conversation. The notices owed are NOT here: the manager says them
                 itself, as they are, and a line in the state too would be told twice
  screen         what is on screen now
  recall         his memory for a query, with no reinforcement

Every read runs in a thread: a slow store delays this run's state, never the loop. A reader that fails leaves its
block out and says nothing else — the state goes without it this time.
"""
from __future__ import annotations

import asyncio
import logging

from conversation.ports import Block

logger = logging.getLogger("zaelar.conversation_host.memory_read")
CHARS_PER_TOKEN = 4


def _state() -> str:
    """What the memory knows that is not the conversation, as FACTS with plain labels: how he likes to be treated,
    where he is, the critical facts, the salient things and the errands (the agent's own identity is the prefix's, never
    a fact of his). Never the old turn's composed block — its headings, its instructions to the model and its copy of the conversation (the manager has its own
    CONVERSATION): its «you are called X» under «who is in front of you» made the model call him by the
    assistant's name, and its words in one language dragged the replies there."""
    from memory import api as memory
    st = memory.state() or {}
    lines = [f"{label}: {str(st[key]).strip()}" for key, label in FIELDS if str(st.get(key) or "").strip()]
    critical = [str(c).strip() for c in memory.critical_facts(limit=6) if str(c).strip()]
    if critical:
        lines.append("critical: " + " · ".join(critical))
    for m in memory.salient_long(limit=5, max_chars=440):
        text = str(m.get("text") or "").strip().replace("\n", " ")[:140]
        if text:
            lines.append(f"{KIND_LABELS.get(str(m.get('kind') or ''), 'known')}: {text}")
    return "\n".join(lines)


#: the memory state's fields this block reads, each with its label
FIELDS = (("treatment", "treatment"), ("location", "location"))
#: a salient memory's kind → its label: an errand is not a fact about him
KIND_LABELS = {"request": "he asked", "result": "delivered"}


#: a widget's mission in the catalogue, cut to this many characters (the manifest's `whenToUse`, `brief.purpose`)
MISSION_CHARS = 70


def _open_ids() -> list[str]:
    from nucleo.turn.prompt import live_state
    return list(live_state._open_widget_ids() or ())


def _widgets() -> str:
    """Every widget of the catalogue by id and mission — what `show_widget` can open, a widget nobody wrote code for
    included —, which are on screen, which one is at full screen, and which were used lately."""
    from nucleo.flash import show_target
    from nucleo.turn.prompt import live_state
    from widgets import brief, runtime
    open_ids, recent = _open_ids(), list(live_state._recent_widget_ids() or ())
    out = []
    for w in runtime.catalog():
        if w.get("id"):
            mission = brief.purpose(str(w.get("whenToUse") or w.get("title") or "").replace("\n", " "), MISSION_CHARS)
            out.append(f"{w['id']} — {mission}" if mission.strip() else str(w["id"]))
    out += [f"on screen: {', '.join(open_ids)}"] if open_ids else ["on screen: none"]
    if full := show_target.at_full_screen():
        out.append(f"at full screen: {full}")
    rest = [w for w in recent if w not in open_ids]
    return "\n".join(out + ([f"used lately: {', '.join(rest)}"] if rest else []))


def front_card() -> str:
    """The card in front of him: the one at full screen, the one in front on a phone, the only one open, else the
    newest opened (the canvas reports its cards in the order they opened). "" with nothing open."""
    from nucleo import canvas_focus
    from nucleo.flash import show_target
    from server.voice_api import open_instances
    open_ids = [str(i) for i in open_instances() if str(i)] or _open_ids()
    return show_target.at_full_screen() or canvas_focus.phone_front() or (open_ids[-1] if open_ids else "")


def widget_facts(wid: str) -> dict:
    """One widget as the model reads it: its declared actions (`brief._offered_action_names`, internal ones never
    named), their fields (`brief._payload_keys`) and what it holds now (`widget_read.read`: the state it reports, its
    digest). The same shape for the widget in front and for one `read_widget` reads."""
    from nucleo.flash import widget_read
    from widgets import brief, runtime
    acts = (runtime.get(wid.split("::", 1)[0]) or {}).get("actions")
    acts = acts if isinstance(acts, dict) else {}
    return {"actions": brief._offered_action_names(acts) if acts else [],
            "fields": brief._payload_keys(acts, every=True) if acts else "", "holds": widget_read.read(wid)}


def _front() -> str:
    wid = front_card()
    if not wid:
        return ""
    f = widget_facts(wid)
    lines = [wid] + ([f"actions: {', '.join(f['actions'])}"] if f["actions"] else [])
    lines += [f"fields: {f['fields']}"] if f["fields"] else []
    return "\n".join(lines + ([f"holds: {f['holds']}"] if f["holds"] else []))


def _screen() -> str:
    """Every widget open now, with its actions and what it holds (a topic: read when the model asks for it)."""
    out = []
    for wid in _open_ids():
        f = widget_facts(wid)
        out.append(f"[{wid}] actions: {', '.join(f['actions']) or 'none'}" + (f"\n{f['holds']}" if f["holds"] else ""))
    return "\n".join(out)


def _connectors() -> str:
    from nucleo.turn.prompt import catalogs
    return catalogs.connector_facts(set(_open_ids()))


def _draft() -> str:
    from nucleo.send import owner
    return owner.status()


def _done() -> str:
    from nucleo.turn.prompt import live_record
    return "\n".join(live_record.done_ops_lines())


def _browser() -> str:
    from nucleo.turn.prompt import live_browser
    return "\n".join(live_browser.navegador_lines())


#: how many days after today the DAYS block dates
DAYS_AHEAD = 7


def _days() -> str:
    """The next days by weekday and date: a named day («on Wednesday») is a lookup, never arithmetic."""
    import time
    now = time.time()
    return "; ".join(time.strftime("%A %Y-%m-%d", time.localtime(now + i * 86400)) for i in range(1, DAYS_AHEAD + 1))


def _tasks() -> str:
    """The background tasks in course and those waiting for his answer, as facts: name, step, progress, note."""
    from nucleo import dispatch
    from nucleo.circuit import ledger
    lines = []
    for t in dispatch.pending_summaries() or ():
        bits = [str(t.get("name") or t.get("title") or t.get("id") or "").strip()]
        bits += ["not started"] if t.get("held") else ([str(t["phase"]).strip()] if t.get("phase") else [])
        if t.get("total"):
            bits.append(f"step {min(t.get('done', 0), t['total'])}/{t['total']}")
        if (t.get("pct") if t.get("pct") is not None else -1) >= 0:
            bits.append(f"{t['pct']}%")
        if t.get("note"):
            bits.append(str(t["note"]).strip()[:160])
        lines.append("running: " + " · ".join(b for b in bits if b))
    for r in ledger.store().tasks_where(states=("waiting",), visible_only=False, limit=20):
        if str(r.get("waiting_for") or "") == ledger.USER_ANSWER:
            goal = str(r.get("title") or r.get("goal") or "").strip().replace("\n", " ")[:90]
            lines.append(f"waiting for his answer: [{r.get('id')}] {goal} — asked: {str(r.get('ask') or '').strip()[:120]}")
    return "\n".join(lines[:12])


#: what every run carries, in this order: what is open first, the dates beside NOW, the widget in front, then the
#: facts and the index
READERS = (("DAYS", _days), ("TASKS", _tasks), ("DRAFT", _draft), ("FRONT", _front), ("STATE", _state),
           ("WIDGETS", _widgets))
#: the readers of the topics `declared.json` declares (`state_topics`): read only when the model asks
TOPICS = {"connectors": _connectors, "done": _done, "browser": _browser, "screen": _screen}


def topic(name: str) -> str:
    """One declared topic of his state, read now ("" when it has nothing)."""
    return (TOPICS[name]() or "").strip()
#: no block takes more than this share of the budget, so one long reader never leaves the next ones out
BLOCK_SHARE = 3


def _blocks(budget_tokens: int) -> list[Block]:
    left = max(1, budget_tokens * CHARS_PER_TOKEN)
    cap = max(1, left // BLOCK_SHARE)
    out = []
    for title, read in READERS:
        try:
            text = (read() or "").strip()
        except Exception as e:  # noqa: BLE001 — a reader that fails leaves its block out, this time
            logger.debug(f"memory_read: {title} unreadable ({e!r})")
            continue
        if text and left > 0:
            out.append(Block(title, text[:min(cap, left)]))
            left -= len(out[-1].text)
    return out


class MemoryRead:
    async def state_blocks(self, account: str, *, budget_tokens: int) -> list[Block]:
        return await asyncio.to_thread(_blocks, budget_tokens)

    async def screen(self, account: str, endpoint: str | None) -> Block:
        from nucleo.turn.prompt import live_state
        return Block("SCREEN", await asyncio.to_thread(live_state.screen_line))

    async def recall(self, account: str, query: str, *, k: int) -> list[Block]:
        from memory import api as memory
        got = await asyncio.to_thread(memory.query, query, limit=k, reinforce_used=False)
        return [Block("RECALL", str(m.get("text") or ""), str(m.get("id") or "")) for m in got.get("memories") or []]
