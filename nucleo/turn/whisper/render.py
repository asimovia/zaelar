"""The slot as the lines it WOULD add to the next turn's state message (V2-889 F2) — templated, bounded, not wired.

At most `MAX_LINES` lines and `MAX_CHARS` characters, whatever the slot holds: facts, a correction, what is missing,
which task is in play. Each line says what it is and where it came from; none tells the model what to do. In shadow
nothing reads this but the `whisper` event (`rendered`), so its size can be measured before it costs prompt.
"""
from __future__ import annotations

from nucleo.turn.whisper.slot import Slot

MAX_LINES = 4
MAX_CHARS = 600


def lines(slot: Slot | None) -> list[str]:
    if slot is None or slot.empty():
        return []
    out = []
    if slot.facts:
        out.append("Facts: " + " · ".join(f"{f['text']} [{f['source']}]" for f in slot.facts))
    if slot.correction:
        c = slot.correction
        out.append(f"Heard «{c['heard']}», likely meant «{c['meant']}» ({c['confidence']:.2f})")
    if slot.missing:
        out.append("Still missing: " + " · ".join(f"{m['slot']}" + (f" ({m['why']})" if m["why"] else "")
                                                  for m in slot.missing))
    if slot.task_certainty:
        t = slot.task_certainty
        out.append(f"Task {t['thread_id'] or '—'}: {t['state']}" + (f" — {t['why']}" if t["why"] else ""))
    return out[:MAX_LINES]


def render(slot: Slot | None) -> str:
    """The lines joined, cut to `MAX_CHARS` (a cut line ends in «…»)."""
    text = "\n".join(lines(slot))
    return text if len(text) <= MAX_CHARS else text[: MAX_CHARS - 1].rstrip() + "…"
