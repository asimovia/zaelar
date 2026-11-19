"""The blocks of the state the model sees, each thing ONCE (§«Cómo ve el modelo el estado»):

  NOW           the time, the screen, the device with the voice
  OPEN          what is open in the ledger, under a budget; the device's focus is pinned in it and marked
  TO_TELL       what is owed to the person and not told yet — never something already in OPEN
  CONVERSATION  the last turns, literal; ours cut to what was heard (unknown is said, never assumed heard)
  INPUT         the batch, each entry with its id, channel and state

Pure functions of plain data. No word of a language is chosen here: titles are the contract's names, contents come
from the ledger, the turns and the batch.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum

from conversation import envelopes as E
from conversation.ledger.items import final
from conversation.ports import Turn
from conversation.types import EnvelopeKind, ItemKind


class Title(Enum):
    NOW, OPEN, TO_TELL, CONVERSATION, INPUT = "NOW", "OPEN", "TO TELL", "CONVERSATION", "INPUT"


def now_block(now_ms: int, tz_offset_min: int, screen: str | None, voice_endpoint: str | None, lang: str) -> str:
    t = datetime.fromtimestamp(now_ms / 1000, tz=timezone(timedelta(minutes=tz_offset_min)))
    parts = [t.strftime("%a %Y-%m-%d %H:%M")]
    if screen:
        parts.append(f"screen: {screen}")
    if voice_endpoint:
        parts.append(f"voice: {voice_endpoint}")
    if lang:
        parts.append(f"lang: {lang}")
    return f"{Title.NOW.value} " + " · ".join(parts)


def _line(row: dict, focus: str | None) -> str:
    d = row.get("data") or {}
    bits = [f"[{row['id']}] {row['kind']} · {row['state']}"]
    if d.get("summary"):
        bits.append(str(d["summary"]))
    if row.get("owner", "conversation") != "conversation":
        bits.append(f"owner {row['owner']}")
    if row.get("waiting_on"):
        bits.append(f"waiting on {row['waiting_on']}")
    line = " · ".join(bits)
    return line + "  ⟵ focus" if row["id"] == focus else line


def open_items(items: list[dict]) -> list[dict]:
    return [r for r in items if r["kind"] != str(ItemKind.TO_TELL) and not final(ItemKind(r["kind"]), r["state"])]


def open_block(items: list[dict], focus: str | None, budget: int) -> tuple[str, set[str]]:
    """The open items, newest first, at most `budget`; the focus always among them, first."""
    rows = sorted(open_items(items), key=lambda r: (r["id"] != focus, -r.get("updated_ms", 0), r["id"]))[:budget]
    shown = {r["id"] for r in rows}
    hidden = len(open_items(items)) - len(rows)
    lines = [_line(r, focus) for r in rows] + ([f"(+{hidden} more open)"] if hidden > 0 else [])
    return "\n".join([Title.OPEN.value, *lines]), shown


def to_tell_block(items: list[dict], already: set[str], now_ms: int) -> str:
    rows = [r for r in items if r["kind"] == str(ItemKind.TO_TELL) and r["id"] not in already
            and (r["state"] == "pending" or (r["state"] == "deferred" and (r["data"].get("due_ms") or 0) <= now_ms))]
    return "\n".join([Title.TO_TELL.value, *(_line(r, None) for r in sorted(rows, key=lambda r: r["id"]))])


def cut_to_heard(turns: list[dict], keep: int) -> tuple[Turn, ...]:
    out = []
    for t in turns[-keep:]:
        text = t["text"]
        if t["role"] == "agent":
            heard = t.get("heard_chars")
            text = f"{text} [heard: unknown]" if heard is None else text[:heard]
            if not text:
                continue
        out.append(Turn(t["role"], t.get("channel", ""), text, t.get("ref", "")))
    return tuple(out)


def input_block(batch: tuple[E.Envelope, ...]) -> str:
    lines = [Title.INPUT.value]
    for env in batch:
        b = env.body
        if env.kind in (EnvelopeKind.USER_UTTERANCE, EnvelopeKind.USER_TEXT):
            tag = f"{b.intervention_id} · {env.channel} · closed"
            if b.amends:
                tag += f" · amends {b.amends}"
            lines.append(f"[{tag}] «{b.text}»")
        elif env.kind is EnvelopeKind.INTERVENTION_STATE:
            lines.append(f"[{b.intervention_id} · {env.channel} · {b.state}] «{b.text or ''}»")
        elif env.kind is EnvelopeKind.WORKER_UPDATE:
            q = f" · question {b.question_id}" if b.question_id else ""
            lines.append(f"[{env.id} · worker {b.task_id} · {b.type}{q}] «{b.text}»")
        elif env.kind is EnvelopeKind.CONTACT_MESSAGE:
            lines.append(f"[{env.id} · contact {b.sender_ref} · thread {b.thread_id}] «{b.text}»")
        elif env.kind is EnvelopeKind.SYSTEM_REMINDER:
            lines.append(f"[{env.id} · reminder {b.reminder_id}] «{b.text}»")
    return "\n".join(lines)
