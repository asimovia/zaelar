"""nucleo/pulse/notice_ask.py — a scheduled notice that ASKS him something waits on a row (V2-878 §4).

A reminder he set as a question («¿has tomado la pastilla?») used to be delivered and forgotten: its answer reached the
turn as conversation, it was no open question for the brief's binding verdict, no thread for the flow judge, and a
restart lost it. Now its question goes through the one asker (`nucleo/circuit/asker`): a `waiting_for=user_answer` row
with its `ask_id`, answered like every durable question, ended by its own `deadline` (CRIT-T4), never by a wall clock.
"""
from __future__ import annotations

import logging
import unicodedata

logger = logging.getLogger("zaelar.notices")


def asks(text: str, kind: str) -> bool:
    """A scheduled notice (`reminder`) whose last sentence is a QUESTION — in any script: the character's Unicode name
    says so (?, ？, ؟, the Greek question mark…), never a word list."""
    if kind != "reminder":
        return False
    for ch in reversed(str(text or "")):          # past spaces and closing quotes or brackets
        if ch.isspace() or unicodedata.category(ch) in ("Pe", "Pf") or ch in "\"'":
            continue
        return "QUESTION MARK" in unicodedata.name(ch, "")
    return False


def open_question(title: str, text: str, detail: dict | None) -> str:
    """The notice's question on its own row through the one asker. Returns its `ask_id` ("" when no row could be
    written: the notice is still delivered)."""
    try:
        from nucleo.circuit import asker
        from nucleo.runtime_ids import next_seq
        uid = asker.open_row(text, kind="notice", origin=str((detail or {}).get("origin") or "cron"), visible=False)
        if not uid:
            return ""
        ask_id = f"{uid}-n{next_seq('notice.ask')}"
        return asker.ask(uid, {"ask_id": ask_id, "corr_id": ask_id, "uid": uid, "task_id": "", "inline": True,
                               "question": text[:600], "title": title[:80], "answer": "", "result": None,
                               "said": True,     # the notice itself says it: the pulse never relays it again
                               "retained": {"kind": "notice"}})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"notice_ask: the notice's question is not on a row ({e!r})")
        return ""


def opened(title: str, text: str, kind: str, detail: dict | None, asks_: bool | None) -> str:
    """The `ask_id` of the notice's question when it asks (`asks_`, or by default `asks`), else ""."""
    return open_question(title, text, detail) if (asks(text, kind) if asks_ is None else asks_) else ""


def answered(uid: str, entry: dict, text: str) -> dict:
    """His answer, bound to the notice's question (`inline_ask.rerun`): the row ends with it, once."""
    from nucleo.request.inline_ask import take
    if take(str(entry.get("ask_id") or "")):
        from nucleo import circuit
        circuit.settle(row=uid, state="done", outcome=f"he answered: {' '.join(str(text or '').split())[:200]}")
    return {"ok": True, "row": uid, "answered": True}


def closed_answered(row: dict) -> bool:
    """A question notice whose ask is no longer open is closed `answered`: never pushed nor painted later. Unreadable
    asks: delivered, as before. (Moved from `notices.py` beside the rest of a notice's question.)"""
    ask = str((row.get("detail") or {}).get("ask_id") or "")
    try:
        from nucleo.cli import worker_api_asks as _asks
        if not ask or any(a.get("ask_id") == ask for a in _asks.pending_asks()):
            return False
    except Exception as e:  # noqa: BLE001
        return bool(logger.debug(f"notices: open asks unreadable: {e!r}"))
    from nucleo.pulse import notices
    notices._set(row["id"], state="answered", next_try_at=None)
    notices._observe(row, "answered", "")
    return True
