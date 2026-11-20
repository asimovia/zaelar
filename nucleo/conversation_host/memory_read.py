"""The `Memory` port of a switched session (V2-941, the F1 plan §4.7, v3.1 B4): it reads the state the way the rest of
the engine reads it, and writes nothing.

  state_blocks   STATE (what the memory knows that is not the conversation, as facts with plain labels), the WIDGETS
                 (the catalogue by id and mission, on screen, at full screen, used lately), what is ON SCREEN (each
                 open widget's actions, the state it reports and what it holds), the TASKS running or waiting, the
                 CONNECTORS' state, the message DRAFT open, what was DONE to his data, the BROWSER's errands and the
                 next DAYS by date — each from the reader the old turn used for it (F2 step 1, row 16), each bounded,
                 filled in this order within the run's token budget. No copy of the conversation. The notices owed
                 are NOT here: the manager says them itself, as they are, and a line in the state too would be told
                 twice
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


def _on_screen() -> str:
    """Each open widget's declared actions (`brief._offered_action_names`, the names the old turn offered), the state
    it reports (`state_render`) and what it holds now (`refs.prompt_digest`, else `refs.items_line`)."""
    from widgets import brief, refs, runtime, state_render
    lines = []
    for wid in _open_ids():
        acts = (runtime.get(wid) or {}).get("actions")
        if isinstance(acts, dict) and (names := brief._offered_action_names(acts)):
            lines.append(f"[{wid}] actions: {', '.join(names)}")
        held = refs.prompt_digest(wid) or refs.items_line(wid)
        if held:
            lines.append(f"[{wid}] holds: {held}")
    return "\n".join(lines + state_render.lines(_open_ids()))


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


READERS = (("STATE", _state), ("WIDGETS", _widgets), ("ON SCREEN", _on_screen), ("TASKS", _tasks),
           ("CONNECTORS", _connectors), ("DRAFT", _draft), ("DONE", _done), ("BROWSER", _browser), ("DAYS", _days))
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
