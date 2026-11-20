"""A numeric claim about data is published only if it matches its evidence — whole, not just the number.

The model states each numeric claim of its reply as structure: who (entity), when (period), what (metric), which way
(direction) and how much (value), naming the evidence it rests on. The evidence is what a tool of this run — or of an
earlier run, still valid — returned. A claim that does not match ALL of it blocks the publication: the run repairs it
once or stays silent. The checker never chooses a tool and never reads the reply's prose.

Three classes of claim (v3.1 §1.10 bis):
  · against STRUCTURED evidence (it carries a value): the whole match, as always;
  · against TEXT evidence (a read with no structure): its value is among the figures of that text, which the host's
    adapter read from the tool's output — this package reads no text;
  · DERIVED (the model counted or averaged what it read): it cites at least one evidence of THIS run that carries
    figures; its value is not matched. With the door for derived figures closed, a derived claim matches nothing.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from conversation.types import Evidence

TABLE = "evidence"


@dataclass(frozen=True)
class Claim:
    entity: str
    period: str
    metric: str
    direction: str
    value: float
    evidence_id: str
    derived: bool = False

    @classmethod
    def from_args(cls, d: dict) -> "Claim":
        """Never raises: a value that is absent or not a number is NaN — and NaN never matches."""
        try:
            value = float(d.get("value"))
        except (TypeError, ValueError):
            value = math.nan
        return cls(str(d.get("entity", "")), str(d.get("period", "")), str(d.get("metric", "")),
                   str(d.get("direction", "")), value, str(d.get("evidence_id", "")), d.get("derived") is True)


def _same(a: str, b: str) -> bool:
    return a.strip().casefold() == b.strip().casefold()


def _near(a: float, b: float) -> bool:
    return abs(a - b) <= 0.005 * max(1.0, abs(b))


def mismatch(claim: Claim, ev: Evidence | None, this_run: frozenset = frozenset(), derived_open: bool = True) -> str | None:
    """Why the claim does not match its evidence, or None when it does."""
    if claim.derived:
        if not derived_open:
            return "derived_closed"
        if claim.evidence_id not in this_run:
            return "not_this_run"
        if ev is None:
            return "no_evidence"
        return None if (ev.numbers or ev.value is not None) else "no_figures"
    if ev is None:
        return "no_evidence"
    if ev.value is None and ev.numbers:                   # a text: the value is one of its figures
        return None if math.isfinite(claim.value) and any(_near(claim.value, n) for n in ev.numbers) else "value"
    for field_name in ("entity", "period", "metric", "direction"):
        if not _same(getattr(claim, field_name), getattr(ev, field_name)):
            return field_name
    if ev.value is None or not math.isfinite(claim.value) or not _near(claim.value, ev.value):
        return "value"
    return None


def check(claims: list[Claim], evidence: dict[str, Evidence], this_run: frozenset = frozenset(),
          derived_open: bool = True) -> list[tuple[Claim, str]]:
    """The claims that do not match, each with why. `this_run`: the evidence ids a read of this run returned."""
    return [(c, why) for c in claims
            if (why := mismatch(c, evidence.get(c.evidence_id), this_run, derived_open)) is not None]


def remember(tx, items: tuple[Evidence, ...], now: int, ttl_ms: int) -> None:
    for ev in items:
        tx.put(TABLE, ev.id, {**ev.to_json(), "expires_ms": now + ttl_ms})


def valid(snapshot, now: int) -> dict[str, Evidence]:
    return {k: Evidence.from_json(r) for k, r in snapshot.scan(TABLE) if r.get("expires_ms", 0) > now}
