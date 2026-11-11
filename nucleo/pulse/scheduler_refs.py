"""nucleo/pulse/scheduler_refs.py — a scheduled job is an OBJECT: one reader, one door by reference (V2-883).

The scheduler's rows had no reader a turn could address them by and one writer that matched a whole name exactly
and whose boolean nobody read. Here they are read as a card's items are (`ref_index`, the V2-026 shape), a reference
resolves through the cards' own resolver (`widgets.refs.match`), and the door answers what is TRUE afterwards. The
journal, `list_jobs` and the `cron.cancel` door live in `scheduler` (`_m`).
"""
from __future__ import annotations

from nucleo import consequence as _consequence

#: What a TURN does with his scheduled jobs, declared once: the escalate question carries it among the acts done on
#: the spot (`nucleo/flash/escalation_guard.declared_turn_acts`), so an order over a job is this door, not an errand.
TURN_ACTS = ("schedule, list or cancel one of his reminders or periodic jobs — the scheduler's own rows, addressed "
             "by the reference the assistant's state lists — is done on the spot, in the turn, never a background "
             "worker.")
#: The payload key a job is named by (`ref_index` rows); a spoken reference resolves to it, never a guessed id.
FIELD = "job"
#: A job's name is often a whole sentence (an order number, a site): the label it is listed and named by is its head.
LABEL_CHARS = 48


def label_of(text) -> str:
    """The short label a job is listed and spoken by: the head of its name, cut at a word."""
    t = " ".join(str(text or "").split())
    if len(t) <= LABEL_CHARS:
        return t
    head = t[:LABEL_CHARS].rsplit(" ", 1)[0].rstrip(" ,.;:-—")
    return f"{head or t[:LABEL_CHARS]}…"


def ref_index() -> list[dict]:
    """The pending jobs as items a reference resolves against — the card shape (V2-026): `{id, label, field, hint}`.
    The one reader the turn's prompt, the worker and the door read."""
    return [{"id": str(j["id"]), "label": label_of(j.get("name") or j.get("prompt") or j["id"]), "field": FIELD,
             "hint": str(j.get("schedule") or "")} for j in _m.list_jobs(active_only=True)]


def find(ref) -> dict:
    """The job a reference names: `{"job": row | None, "needs": "" | "ref" | "no_match" | "ambiguous",
    "candidates": [labels]}`. Its id, its whole name, or its label as he says it, resolved by the cards' own
    resolver (`widgets.refs.match`) — never a guess."""
    idx = ref_index()
    given = str(ref or "").strip().lstrip("#").strip()
    whole = [j for j in _m.list_jobs(active_only=True)
             if given and given.lower() in ((j.get("name") or "").strip().lower(), str(j["id"]))]
    if len(whole) == 1:
        jid = str(whole[0]["id"])
    else:
        from widgets import refs as _refs
        got = _refs.match(given, idx)
        if not got.ok:
            return {"job": None, "needs": got.needs or "no_match", "candidates": list(got.candidates or [])}
        jid = str((got.payload or {}).get("id") or "")
    row = next((i for i in idx if i["id"] == jid), None)
    return {"job": row, "needs": "" if row else "no_match", "candidates": [] if row else [i["label"] for i in idx]}


def any_scheduled() -> bool:
    """A job of his is scheduled — the state that offers the turn's `cancel_scheduled` tool. Unreadable: not offered."""
    try:
        return bool(_m.list_jobs(active_only=True))
    except Exception:  # noqa: BLE001
        return False


def _listed(jid) -> bool:
    return any(str(j["id"]) == str(jid) for j in _m.list_jobs(active_only=True))


def unschedule(ref) -> dict:
    """Cancel the job `ref` names and say what is TRUE afterwards (V2-883). The act's end state is declared here once —
    the job is no longer listed — and `ok` is that reading, never the door's intention. A miss carries the
    candidates and the line he hears, from his language's table: `{ok, id, label, error, candidates, message}`."""
    hit = find(ref)
    job = hit["job"]
    if job is None:
        return {"ok": False, "id": None, "label": "", "error": hit["needs"], "candidates": hit["candidates"],
                "message": _missed_line(hit["candidates"])}
    _m.cancel(job["id"])
    if _consequence.dry():   # a closed door (a dry turn) changes nothing by design: its neutral is the answer
        return {"ok": True, "id": job["id"], "label": job["label"], "error": None, "candidates": [], "dry": True}
    gone = not _listed(job["id"])
    return {"ok": gone, "id": job["id"], "label": job["label"], "error": None if gone else "still_listed",
            "candidates": [] if gone else [job["label"]], "message": "" if gone else _missed_line([])}


def _missed_line(candidates: list) -> str:
    """«I didn't find that job, so nothing was cancelled» + what IS scheduled, in his language."""
    if candidates:
        return _lang_line("cron_no_match").replace("{options}", ", ".join(f"«{c}»" for c in candidates[:6]))
    return _lang_line("cron_none")


def _lang_line(key: str) -> str:
    """A line of his language's table; "" without one (then the mouth's generic «couldn't» stands)."""
    try:
        from i18n import langs as _langs
        return str(getattr(_langs.current_language(), key, "") or "")
    except Exception:  # noqa: BLE001
        return ""




def worker_act(action: str, payload: dict) -> dict:
    """The worker's two doors over the jobs (`act schedules` / `act unschedule`, `nucleo/cli/worker_api_exec.py`)."""
    if action == "schedules":
        return {"ok": True, "result": {"jobs": ref_index()}}
    p = payload or {}
    r = unschedule(str(p.get("job") or p.get("id") or p.get("name") or "").strip())
    if r.get("ok"):
        return {"ok": True, "result": {"cancelled": r.get("id"), "label": r.get("label")}}
    return {"ok": False, "error": f"nothing cancelled ({r.get('error')}): pass one id from `act schedules`",
            "candidates": r.get("candidates") or []}


from nucleo.pulse import scheduler as _m  # noqa: E402 — last: the scheduler imports this module at its end
