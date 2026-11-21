"""A draft IS a task of the queue: the send lane (INI-078 orchestrator step 6, segregation S4).

Each message he asks for is ONE row of the queue with owner `send` and its `#n`; the draft (who, what it says, what it
last asked him) travels in the row's `progress`, so it outlives a restart. The owner keeps the draft it is writing in
RAM (`draft.current()`) as the live cache; the row is its truth for everyone else — OPEN, his column, the boot:

  · opened → `add` + `start`; asking him → `wait` with the line he heard; his words to it → `back` + `start`;
  · the connector's receipt → `done` (a message held for later is `done` when the outbox takes it); a send refused,
    a draft dropped, idle or left undone → `failed` / `cancelled`. The row leaves; its pill says how it ended;
  · a message asked for while another is open is a `pending` row behind it, opened when the lane is free (`next`);
  · at boot an open draft comes back from its row, WAITING for his yes (the confirmation is read to him again).
"""
from __future__ import annotations

import json
import time

from loguru import logger

#: the draft's fields its row carries (`progress.draft`): enough to write the same message after a restart
KEPT = ("id", "said", "who", "channel", "text", "target", "candidates", "unmatched", "asked", "act", "kind", "widget",
        "extra", "confirm_line", "by", "trace", "ref")
#: a send whose receipt is not in by then no longer holds the lane (the receipt watcher still tells him when it lands)
SENDING_S = 40.0


def _q():
    from nucleo import queue
    return queue


def _note(e: Exception) -> None:
    logger.debug(f"send.row: {type(e).__name__}: {e}")


def _get(tid: str) -> dict:
    """The draft's task while it is open ({} once archived: it left the queue)."""
    try:
        row = _q()._store().task_get(tid) or {} if tid else {}
        return row if row.get("state") in (_q().PENDING, _q().RUNNING, _q().WAITING) else {}
    except Exception as e:  # noqa: BLE001
        _note(e)
        return {}


def title(d) -> str:
    """What the task DOES, in no language of his: the person and the text (never the sentence that ordered it)."""
    to = (d.target or {}).get("name") or d.who or "?"
    if d.kind == "act":
        return f"✉ {d.act} · {', '.join(d.names_said()) or to}"[:200]
    return f"✉ {to}" + (f" · «{d.text[:120]}»" if d.text else "")


def _snap(d) -> dict:
    out = {k: getattr(d, k) for k in KEPT}
    return {"draft": json.loads(json.dumps(out, ensure_ascii=False, default=str))}


def opened(d, row: str = "") -> None:
    """A draft opened: its row (a queued one it adopts, or a new one) runs now."""
    q = _q()
    tid = row or q.add("send", title(d), goal=d.said, trace=d.trace, origin="voz", progress=_snap(d))
    if tid and (_get(tid).get("state") == q.PENDING):
        q.signal(tid, "start", by="owner")
    d.row = tid or ""


def _running(d) -> bool:
    """Bring the draft's row to `running` (his words reached it while it waited): False when it is gone."""
    q = _q()
    st = _get(d.row).get("state")
    if st == q.WAITING:
        q.signal(d.row, "back", by="owner")
        st = q.PENDING
    if st == q.PENDING:
        q.signal(d.row, "start", by="owner")
        st = q.RUNNING
    return st == q.RUNNING


def resumed(d) -> None:
    if d is not None and getattr(d, "row", ""):
        _running(d)


def asked(line: str, of=None) -> None:
    """The owner's line is said: the open draft's row WAITS for his answer to it, with the draft as it now stands.
    `of`: the draft the line was about — a line about a draft that already left never lands on the next one."""
    from nucleo.send import draft
    d = draft.current()
    if d is None or (of is not None and d is not of):
        return
    if not _get(getattr(d, "row", "")):          # its task left (a new order took its place, then gave it back)
        opened(d)
    q = _q()
    if not d.row or (str(line or "").strip() and not _running(d)):
        return                                   # no line: nothing asked — the task stays where it was
    q.signal(d.row, "progress", by="owner", progress=_snap(d), title=title(d))
    if str(line or "").strip():
        q.signal(d.row, "wait", by="owner", ask=str(line).strip()[:600], waiting_for="user_answer")


def end(d, what: str, outcome: str = "") -> None:
    """The draft's row leaves the queue (`done` · `failed` · `cancelled`), and the next message he asked for opens."""
    if d is None or not getattr(d, "row", "") or not _get(d.row):
        return
    q = _q()
    if what != "cancelled":
        _running(d)
    q.signal(d.row, what, by="owner", outcome=str(outcome or what)[:400])
    _open_next_soon()


def ended(d, state: str) -> None:
    """A draft ended in the owner (`draft._ended`): a sent one waits for its receipt; the rest leave now."""
    from nucleo.send import draft
    if state == draft.SENT:
        return
    end(d, "failed" if state == draft.FAILED else "cancelled", state)


def sending(d) -> None:
    """His yes went: the row runs until the receipt (`end` by the receipt watcher)."""
    if d is not None and getattr(d, "row", "") and _running(d):
        _q().signal(d.row, "progress", by="owner", progress=_snap(d), phase="sending")


def busy() -> bool:
    """Does a message still hold the send lane (its draft open, or sent and its receipt not in yet)? A send past
    `SENDING_S` with no receipt holds nothing: it leaves as not confirmed."""
    from nucleo.send import draft
    if draft.current() is not None:
        return True
    q = _q()
    for r in q.view()["send"][q.RUNNING]:
        if time.time() - float(r.get("started_at") or 0) < SENDING_S:
            return True
        q.signal(str(r["id"]), "done", by="owner", outcome="sent — its receipt not in yet")
    return False


def sending_to() -> str:
    """Who the message holding the lane goes to, as its task names it."""
    q = _q()
    return next((str(r.get("title") or "").removeprefix("✉ ").split(" · ")[0] for r in q.view()["send"][q.RUNNING]), "")


def queued(said: str, hint: dict, by: str) -> int:
    """A message he asked for while the lane is busy: a pending row behind it. Returns how many wait."""
    h = {k: v for k, v in (hint or {}).items() if not str(k).startswith("_adopted")}
    to = str(h.get("contact") or h.get("to") or "").strip()
    _q().add("send", f"✉ {to or '?'}" + (f" · «{str(h.get('text'))[:120]}»" if h.get("text") else ""), goal=said,
             progress={"said": said, "hint": json.loads(json.dumps(h, default=str)), "by": by, "at": time.time()})
    return len(_q().view()["send"][_q().PENDING])


def next_queued(idle_s: float) -> dict | None:
    """The first message waiting in the lane, in its order; one that waited longer than a draft lives leaves (never
    opened stale)."""
    q = _q()
    for r in q.view()["send"][q.PENDING]:
        p = r.get("progress") or {}
        if time.time() - float(p.get("at") or r.get("created_at") or 0) > idle_s:
            q.signal(str(r["id"]), "cancelled", by="owner", outcome="waited too long")
            continue
        return {"said": str(p.get("said") or r.get("goal") or ""), "hint": dict(p.get("hint") or {}),
                "by": str(p.get("by") or "queued"), "row": str(r["id"])}
    return None


def _open_next_soon() -> None:
    try:
        import asyncio
        from nucleo.send import intake
        asyncio.get_running_loop().create_task(intake.open_the_next())
    except RuntimeError as e:                    # no loop here: the next draft that ends opens it
        _note(e)


def restore() -> list[str]:
    """At boot: the draft that was open comes back from its row, waiting for his yes (read again to him: `heard` is
    False). A message that was sending leaves as not confirmed. Returns the rows restored."""
    from nucleo.send import draft
    q, out = _q(), []
    for r in q.view()["send"][q.RUNNING] + q.view()["send"][q.WAITING]:
        kept = (r.get("progress") or {}).get("draft") or {}
        if r.get("phase") == "sending" or kept.get("ref") or not kept or draft.current() is not None:
            q.signal(str(r["id"]), "done" if r.get("phase") == "sending" else "cancelled", by="pulse",
                     outcome="sent — its receipt not followed after a restart" if r.get("phase") == "sending"
                     else "not restored after a restart")
            continue
        d = draft.Draft(said=str(kept.get("said") or ""))
        for k in KEPT:
            if k in kept and k != "id":
                setattr(d, k, kept[k])
        d.row, d.heard = str(r["id"]), False
        draft._open["draft"] = d
        if r.get("state") == q.RUNNING:
            q.signal(d.row, "wait", by="pulse", ask=str(d.confirm_line or r.get("ask") or ""), waiting_for="user_answer")
        out.append(d.row)
    return out


def status() -> str:
    """The open draft for the conversation's own context ("" when none): its #number, what it is and what it waits for —
    so the model acts on it by number, and a question about it is answered from the truth."""
    from nucleo.send import draft
    d = draft.current()
    if d is None:
        return ""
    n = _get(getattr(d, "row", "")).get("num")
    tag = f"#{n}" if n else "the draft"
    acts = (f"His plain yes to that question is draft_send({tag}); a change of who or what it says is "
            f"draft_edit({tag}, …) with the WHOLE new text; his no is draft_drop({tag}). You never say it is sent: "
            "its owner says so from the receipt.")
    if d.kind == "act":
        about = ", ".join(d.names_said()) or "what he named"
        wait = "which ones (or all)" if d.asked == draft.WHO else "his yes"
        return (f"{tag}: he asked for {d.act} ({about}) through the messaging card; it waits for {wait}: NOTHING is done "
                f"until he answers. {acts}")
    to = d.target.get("name") if d.target else (f"not chosen ({d.who})" if d.who else "nobody yet")
    wait = {"who": "who it is for", "text": "what it should say", "confirm": "his yes to send it"}.get(d.asked, "")
    return f"{tag}: a message being written — to: {to}; text: «{d.text[:160]}»; waiting for {wait}. Not sent. {acts}"
