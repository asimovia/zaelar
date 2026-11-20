"""The blocks of the state the model sees, each thing ONCE (§«Cómo ve el modelo el estado»):

  NOW           the time, the screen, the device with the voice
  OPEN          what is open in the ledger (the person's requests, a reserved effect), newest first, under a budget
  CONVERSATION  the last turns, literal; ours cut to what was heard (unknown is said, never assumed heard)
  INPUT         the batch, each entry with its id, channel and state

Pure functions of plain data. No word of a language is chosen here: titles are the contract's names, contents come
from the ledger, the turns and the batch. What the host keeps — its tasks, what it owes the person — reaches the state
as the blocks the host reads (`Memory.state_blocks`), never as a copy in this ledger.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum

from conversation import envelopes as E
from conversation.ledger.items import final
from conversation.ports import Turn
from conversation.types import Coverage, EnvelopeKind, ItemKind


class Title(Enum):
    NOW, OPEN, CONVERSATION, INPUT, VOICE_LOST = "NOW", "OPEN", "CONVERSATION", "INPUT", "VOICE LOST"


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


def _line(row: dict) -> str:
    d = row.get("data") or {}
    bits = [f"[{row['id']}] {row['kind']} · {row['state']}"]
    if d.get("summary"):
        bits.append(str(d["summary"]))
    if row.get("owner", "conversation") != "conversation":
        bits.append(f"owner {row['owner']}")
    if row.get("waiting_on"):
        bits.append(f"waiting on {row['waiting_on']}")
    return " · ".join(bits)


def open_items(items: list[dict]) -> list[dict]:
    return [r for r in items if not final(ItemKind(r["kind"]), r["state"])]


def open_block(items: list[dict], budget: int) -> str:
    """The open items, newest first, at most `budget`, and how many more there are."""
    rows = sorted(open_items(items), key=lambda r: (-r.get("updated_ms", 0), r["id"]))[:budget]
    hidden = len(open_items(items)) - len(rows)
    lines = [_line(r) for r in rows] + ([f"(+{hidden} more open)"] if hidden > 0 else [])
    return "\n".join([Title.OPEN.value, *lines])


def lost_block(now_ms: int, lost: list[tuple[int, str, str]]) -> str:
    """His voice that reached nothing whole before this text: when, which, and why (a fact, never a reading)."""
    return "\n".join([Title.VOICE_LOST.value] + [f"[{iv} · {max(0, now_ms - at) // 1000} s ago · {why}]"
                                                  for at, iv, why in lost])


def _age(ms: int) -> str:
    m = max(0, ms) // 60_000
    return f"{m} min" if m < 120 else f"{m // 60} h" if m < 48 * 60 else f"{m // 1440} days"


def cut_to_heard(turns: list[dict], keep: int, now_ms: int | None = None, gap_ms: int = 0) -> tuple[Turn, ...]:
    """The last turns, ours cut to what was heard. A turn of an EARLIER session — before the last silence longer than
    `gap_ms` — says so, with its age: what was asked then is history, never what is being answered now (a question
    asked again on another day was taken for one already answered)."""
    turns = turns[-keep:]
    edge = -1
    if now_ms is not None and gap_ms > 0:
        ats = [t.get("at") for t in turns] + [now_ms]
        edge = max((i for i in range(len(turns)) if ats[i] is not None and ats[i + 1] is not None
                    and ats[i + 1] - ats[i] > gap_ms), default=-1)
    out = []
    for i, t in enumerate(turns):
        text = t["text"]
        if t["role"] == "agent":
            heard = t.get("heard_chars")
            text = f"{text} [heard: unknown]" if heard is None else text[:heard]
            if not text:
                continue
        if i <= edge and t.get("at") is not None:
            text = f"[earlier session · {_age(now_ms - t['at'])} ago] {text}"
        out.append(Turn(t["role"], t.get("channel", ""), text, t.get("ref", "")))
    return tuple(out)


def input_block(batch: tuple[E.Envelope, ...], tz_offset_min: int = 0) -> str:
    """Each entry with its id, channel and time — facts, never our protocol's words: an entry «closed» read to the
    model as «already answered». Only an entry the ear could not hear whole says so («cut off»)."""
    lines = [Title.INPUT.value]
    tz = timezone(timedelta(minutes=tz_offset_min))
    for env in batch:
        b = env.body
        if env.kind in (EnvelopeKind.USER_UTTERANCE, EnvelopeKind.USER_TEXT):
            at = datetime.fromtimestamp(env.sealed_ms / 1000, tz=tz).strftime("%H:%M:%S")
            tag = f"{b.intervention_id} · {env.channel} · {at}"
            if env.kind is EnvelopeKind.USER_UTTERANCE and b.coverage is not Coverage.FULL:
                tag += " · cut off"
            if b.amends:
                tag += f" · amends {b.amends}"
            lines.append(f"[{tag}] «{b.text}»")
    return "\n".join(lines)
