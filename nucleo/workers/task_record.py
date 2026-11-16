"""What a task's row keeps of its worker: what HE said while it ran, and the worker's own transcript.

Measured gaps: what the operator said mid-task lived only in RAM (`rec.injects`) — a restart or a resumed session lost
it, and nothing showed later what he had added; and the worker's transcript was kept nowhere, so a task that went
wrong could only be read from scattered panel rows. Both now live on the row, in its artefacts (`task_artifacts`,
reached through the ledger like every task artefact):

  · `said_mid_task` — each line he added, `{at, text, source, delivered}`; the bridge's piggyback marks them delivered,
    and a line still pending after a restart is served to the next worker of the same row.
  · `transcript`    — the worker's events in order, `{at, type, text}` cut short, the newest `TRANSCRIPT_KEPT`;
    buffered on the record and written every `FLUSH_EVERY` events and when the session closes or parks.

And how a close is TOLD, once: `owes_death_notice` decides whether the death's question owns it.
"""
from __future__ import annotations

import time

from loguru import logger

SAID_SLOT = "said_mid_task"
TRANSCRIPT_SLOT = "transcript"
#: How many of his mid-task lines a row keeps, and how many transcript events (the newest win).
SAID_KEPT = 50
TRANSCRIPT_KEPT = 400
#: Events buffered before they are written; a close or a park writes the rest.
FLUSH_EVERY = 20
#: How much of one event's text the transcript keeps.
EVENT_CHARS = 400
#: How long one of his lines waits on the row for a worker: older, it is his past, not an instruction (marked expired).
SAID_MAX_AGE_S = 1800


def _store():
    from nucleo.circuit import ledger
    return ledger.store()


def _note(what: str, e: Exception) -> None:
    logger.debug(f"task_record: {what} not written ({type(e).__name__}: {e})")


def said(uid: str, text: str, source: str = "operator") -> None:
    """His line, on the row, as he sent it to a running (or queued) worker."""
    if not (uid and str(text or "").strip()):
        return
    try:
        ts = _store()
        rows = list(ts.artifact_get(uid, SAID_SLOT) or [])
        rows.append({"at": time.time(), "text": str(text).strip(), "source": source, "delivered": False})
        ts.artifact_put(uid, SAID_SLOT, rows[-SAID_KEPT:])
    except Exception as e:  # noqa: BLE001 — the line still reaches the worker through RAM
        _note("his line", e)


def take(uid: str, served: list[dict], *, now: float | None = None) -> list[dict]:
    """Mark his pending lines delivered; return those the RAM queue did not serve (they outlived a restart) and that
    are younger than `SAID_MAX_AGE_S` — an older one is marked delivered unserved, never handed to a later worker."""
    if not uid:
        return []
    try:
        ts = _store()
        rows = list(ts.artifact_get(uid, SAID_SLOT) or [])
        texts = {str(s.get("text") or "") for s in served}
        cut = (time.time() if now is None else now) - SAID_MAX_AGE_S
        extra = [{"text": r["text"], "source": r.get("source", "operator")} for r in rows
                 if not r.get("delivered") and str(r.get("text") or "") not in texts and float(r.get("at") or 0) >= cut]
        if any(not r.get("delivered") for r in rows):
            ts.artifact_put(uid, SAID_SLOT, [{**r, "delivered": True} for r in rows])
        return extra
    except Exception as e:  # noqa: BLE001
        _note("delivery mark", e)
        return []


def heard(rec, ev) -> None:
    """One worker event into the record's transcript buffer; written every `FLUSH_EVERY`."""
    try:
        d = getattr(ev, "data", None) or {}
        text = str(d.get("text") or d.get("label") or " ".join(
            str(d.get(k) or "") for k in ("action", "target") if d.get(k)) or "")
        if not text.strip():
            return                      # usage, progress, spawned: nothing to read, and they would spend the bound
        rec.transcript.append({"at": time.time(), "type": str(getattr(ev, "type", "") or ""),
                               "text": text[:EVENT_CHARS]})
        if len(rec.transcript) >= FLUSH_EVERY:
            flush(rec)
    except Exception as e:  # noqa: BLE001 — the transcript never breaks the worker it records
        _note("event", e)


def flush(rec) -> None:
    """Write the buffered events onto the row (appended, bounded) and empty the buffer."""
    uid = str(getattr(rec, "uid", "") or "")
    buf = list(getattr(rec, "transcript", None) or [])
    if not (uid and buf):
        return
    try:
        ts = _store()
        rows = list(ts.artifact_get(uid, TRANSCRIPT_SLOT) or [])
        ts.artifact_put(uid, TRANSCRIPT_SLOT, (rows + buf)[-TRANSCRIPT_KEPT:])
        if (ts.artifact_get(uid, TRANSCRIPT_SLOT) or [None])[-1] != buf[-1]:
            raise OSError("the row did not take the events")   # the store swallows its own failure: read it back
        del rec.transcript[:len(buf)]                           # only what reached the row leaves the buffer
    except Exception as e:  # noqa: BLE001
        _note("transcript", e)


def owes_death_notice(rec) -> bool:
    """A close whose ONE notice is the death's question (retry / another way / leave it, `ended._remember_ended`): a
    failure that was not his cancel, not a relay and not parked for a quota's reset. The delivery line
    (`session_finish._deliver`) stays silent for it, so a failure is told once (`notice:<row>` and `death:<id>` both
    spoke before)."""
    from nucleo.workers.quota_wait import is_parked
    return (str(getattr(rec, "status", "") or "") != "cancelled" and not bool(getattr(rec, "ok", False))
            and not str(getattr(rec, "handoff", "") or "")       # V2-238: a relayed errand has not died
            and not is_parked(getattr(rec, "goal", "")))         # …nor one parked for the quota's reset


def tell_death(rec) -> None:
    """The death's question, the ONE notice of a failed close (V2-222: a real death is PUSHED). Called by the ending's
    snapshot (`ended._remember_ended`) for every close that does not continue, before any fence of its own."""
    if not owes_death_notice(rec):
        return
    try:
        from nucleo.events import task_event      # a task matter, on its row (V2-851 F4)
        from nucleo.workers.handoff import operator_safe_summary
        goal = (getattr(rec, "goal", "") or "the background task").strip()[:70]
        why = operator_safe_summary(str(getattr(rec, "result_summary", "") or ""))[:200]
        task_event.told(f"The background task «{goal}» died without a result" + (f" ({why})" if why else "")
                        + " and will not retry by itself. Retry it, try another way, or leave it?",
                        task_id=str(getattr(rec, "uid", "") or ""), key=f"death:{rec.task_id}", goal=goal, ok=False,
                        ask=True)
    except Exception as e:  # noqa: BLE001 — the row still holds the failure
        _note("the death's notice", e)
