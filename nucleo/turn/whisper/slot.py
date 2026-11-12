"""The whisper is a TYPED SLOT, never prose (V2-889 F2, §2: the old Susurro pasted `brain_notes` into the next prompt).

    {turn_id, thread_id, made_at,
     facts ≤3 {text ≤140, source},
     correction {heard, meant, confidence} | None,
     missing ≤2 {slot, why},
     task_certainty {thread_id, state: clear|ambiguous|contradicted, why ≤120} | None}

There is NO instruction field and there cannot be one: `parse` keeps only the declared fields, cuts every string to
its bound and drops whatever else the model wrote — an «advice» or a «say this» key is not read, by construction.
Unparseable JSON is no whisper (`None`), never a guess.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from loguru import logger

MAX_FACTS, FACT_CHARS = 3, 140
MAX_MISSING, MISSING_CHARS = 2, 80
WHY_CHARS = 120
HEARD_CHARS = 80
#: Where a fact came from. A fact with another source is dropped: an unsourced datum is the confabulation the slot
#: exists to keep out of the prompt.
#: Both read from the whisperer's declared names (`schema.json`), the file the gate reads too.
from nucleo.turn.whisper.gate import SCHEMA as _SCHEMA  # noqa: E402
SOURCES = tuple(_SCHEMA["fact_sources"])
CERTAINTY = tuple(_SCHEMA["task_certainty"])


@dataclass
class Slot:
    turn_id: str = ""
    thread_id: str = ""
    made_at: float = 0.0
    facts: list[dict] = field(default_factory=list)
    correction: dict | None = None
    missing: list[dict] = field(default_factory=list)
    task_certainty: dict | None = None

    def as_dict(self) -> dict:
        return asdict(self)

    def empty(self) -> bool:
        return not (self.facts or self.correction or self.missing or self.task_certainty)


def _text(v, n: int) -> str:
    return " ".join(str(v or "").split())[:n]


def _json_object(text: str) -> dict | None:
    s = str(text or "")
    a, b = s.find("{"), s.rfind("}")
    if a < 0 or b <= a:
        return None
    try:
        got = json.loads(s[a:b + 1])
    except (ValueError, TypeError) as e:
        logger.debug(f"whisper.slot: the answer is not JSON — {e!r}")
        got = None
    return got if isinstance(got, dict) else None


def _facts(raw) -> list[dict]:
    out = []
    for f in raw if isinstance(raw, list) else ():
        if not isinstance(f, dict):
            continue
        text, src = _text(f.get("text"), FACT_CHARS), str(f.get("source") or "")
        if text and src in SOURCES:
            out.append({"text": text, "source": src})
        if len(out) == MAX_FACTS:
            break
    return out


def _correction(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    heard, meant = _text(raw.get("heard"), HEARD_CHARS), _text(raw.get("meant"), HEARD_CHARS)
    try:
        conf = max(0.0, min(1.0, float(raw.get("confidence") or 0.0)))
    except (TypeError, ValueError):
        conf = 0.0
    return {"heard": heard, "meant": meant, "confidence": round(conf, 2)} if heard and meant and heard != meant else None


def _missing(raw) -> list[dict]:
    out = []
    for m in raw if isinstance(raw, list) else ():
        if isinstance(m, dict) and _text(m.get("slot"), MISSING_CHARS):
            out.append({"slot": _text(m.get("slot"), MISSING_CHARS), "why": _text(m.get("why"), WHY_CHARS)})
        if len(out) == MAX_MISSING:
            break
    return out


def _certainty(raw, thread_ids: set[str]) -> dict | None:
    """A certainty about a task the gate did not offer is dropped — the slot never names a stranger's row."""
    if not isinstance(raw, dict):
        return None
    tid, state = str(raw.get("thread_id") or ""), str(raw.get("state") or "")
    if state not in CERTAINTY or (thread_ids and tid not in thread_ids) or (not thread_ids and tid):
        return None
    return {"thread_id": tid, "state": state, "why": _text(raw.get("why"), WHY_CHARS)}


def parse(text: str, *, turn_id: str, thread_id: str = "", made_at: float = 0.0,
          thread_ids: set[str] | None = None) -> Slot | None:
    """The model's answer as a slot, or None when it is not a JSON object."""
    raw = _json_object(text)
    if raw is None:
        return None
    return Slot(turn_id=str(turn_id or ""), thread_id=str(thread_id or ""), made_at=float(made_at or 0.0),
                facts=_facts(raw.get("facts")), correction=_correction(raw.get("correction")),
                missing=_missing(raw.get("missing")),
                task_certainty=_certainty(raw.get("task_certainty"), set(thread_ids or ())))
