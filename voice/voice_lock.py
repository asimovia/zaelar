"""voice_lock.py — «Stick to my voice»: only the enrolled voice reaches the brain (V2-651 F1, behind a switch).

The browser fingerprints every speech segment against the voice it enrolled first (`frontend/app/lib/speaker-id.js`,
which measured in SHADOW until now) and, while the switch is on, sends each verdict here over the room's data channel
(`zaelar-speaker`), plus the switch itself and whether a voice is enrolled at all (`zaelar-voicelock`). The
conversation's ear guard (`nucleo/conversation_host/guards.py`) asks `admit_now()` before anything else: a turn whose
segments were all judged ANOTHER voice (a TV, someone across the room) is dropped there, before any model runs.

SAFE BY CONSTRUCTION. The switch narrows what is heard; it can never make the agent deaf to him by accident:
  · switch off                        → every turn passes (the default);
  · switch on, no voice enrolled yet  → every turn passes, and the button says so;
  · switch on, no verdict for the turn (the browser's segment ended after the transcript, a lost packet)
                                      → it waits a short grace, then passes;
  · any segment of the turn judged his → it passes.
Only a turn whose every verdict says «another voice» is dropped. Verdicts are consumed by the decision that reads them,
so one utterance's verdicts never vote on the next.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque

#: How long a verdict may arrive after the turn's transcript: the browser closes a segment on ~300 ms of silence,
#: which can land just after the STT's final. Paid only while the switch is on and a voice is enrolled.
GRACE_S = 0.6
#: A verdict this much older than the utterance's onset belongs to an earlier one.
_SLACK_S = 0.5
#: With no onset known, how far back a verdict may still speak for this turn.
_FALLBACK_S = 10.0

_state: dict = {"on": False, "enrolled": False, "verdicts": deque(maxlen=64)}


def set_state(on: bool, enrolled: bool) -> None:
    """The browser's switch and whether it holds an enrolled voice (`zaelar-voicelock`)."""
    _state["on"] = bool(on)
    _state["enrolled"] = bool(enrolled)
    if not (_state["on"] and _state["enrolled"]):
        _state["verdicts"].clear()   # off, or a voice being re-learned: what was judged against the old one is void


def note_verdict(label: str, now: float | None = None) -> None:
    """One segment's verdict (`zaelar-speaker`): `operator`, `other`, or `known:<id>` (another known voice)."""
    lab = str(label or "").strip()
    if lab and lab != "enroll":
        _state["verdicts"].append((time.time() if now is None else now, lab))


def decide(*, on: bool, enrolled: bool, labels: list[str]) -> tuple[bool, str]:
    """PURE: `(keep, reason)` for one turn from the switch, the enrolment and its segments' verdicts."""
    if not on:
        return True, "off"
    if not enrolled:
        return True, "no_enrollment"
    if not labels:
        return True, "no_verdict"
    if "operator" in labels:
        return True, "operator"
    return False, "other_voice"


def _labels_since(since: float) -> list[str]:
    return [lab for ts, lab in _state["verdicts"] if ts >= since]


async def admit(onset: float = 0.0, now: float | None = None, grace_s: float = GRACE_S) -> tuple[bool, str]:
    """Does this turn come from the enrolled voice? `onset` = when the utterance began (0 = unknown)."""
    now = time.time() if now is None else now
    since = (onset - _SLACK_S) if onset and onset <= now else (now - _FALLBACK_S)
    labels = _labels_since(since)
    if _state["on"] and _state["enrolled"] and not labels and grace_s > 0:
        waited = 0.0
        while waited < grace_s and not labels:
            await asyncio.sleep(0.1)
            waited += 0.1
            labels = _labels_since(since)
    keep, why = decide(on=_state["on"], enrolled=_state["enrolled"], labels=labels)
    _state["verdicts"].clear()   # consumed: the next utterance is judged by its own segments
    return keep, why


def admit_now(onset: float = 0.0, now: float | None = None) -> tuple[bool, str]:
    """`admit` with no grace, for a judge that runs AFTER the turn closed (the conversation manager's ear closes past
    its provider's end of turn, after the browser's segment): never on a loop, never waits."""
    now = time.time() if now is None else now
    since = (onset - _SLACK_S) if onset and onset <= now else (now - _FALLBACK_S)
    keep, why = decide(on=_state["on"], enrolled=_state["enrolled"], labels=_labels_since(since))
    _state["verdicts"].clear()
    return keep, why


def judged_other(onset: float, now: float | None = None) -> bool:
    """Is the voice that rose at `onset` another person's? READ ONLY — nothing is consumed: the close of that voice
    still judges it by its own verdicts (`admit_now`). True only with the switch on, a voice enrolled, at least one
    verdict since that onset and none of them his; an unknown onset or no verdict yet is False (it may be his)."""
    now = time.time() if now is None else now
    if not (_state["on"] and _state["enrolled"]) or not onset or onset > now:
        return False
    labels = _labels_since(onset - _SLACK_S)
    return bool(labels) and "operator" not in labels


def state() -> dict:
    return {"on": _state["on"], "enrolled": _state["enrolled"], "pending": len(_state["verdicts"])}
