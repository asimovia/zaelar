"""A numeric claim about data is published only if it matches its evidence — whole, not just the number.

The model states each numeric claim of its reply as structure: who (entity), when (period), what (metric), which way
(direction) and how much (value), naming the evidence it rests on. The evidence is what a tool of this run — or of an
earlier run, still valid — returned. A claim that does not match ALL of it blocks the publication: the run repairs it
once or stays silent. The checker never chooses a tool and never reads the reply's prose.
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

    @classmethod
    def from_args(cls, d: dict) -> "Claim":
        """Never raises: a value that is absent or not a number is NaN — and NaN never matches."""
        try:
            value = float(d.get("value"))
        except (TypeError, ValueError):
            value = math.nan
        return cls(str(d.get("entity", "")), str(d.get("period", "")), str(d.get("metric", "")),
                   str(d.get("direction", "")), value, str(d.get("evidence_id", "")))


def _same(a: str, b: str) -> bool:
    return a.strip().casefold() == b.strip().casefold()


def mismatch(claim: Claim, ev: Evidence | None) -> str | None:
    """Why the claim does not match its evidence, or None when it does."""
    if ev is None:
        return "no_evidence"
    for field_name in ("entity", "period", "metric", "direction"):
        if not _same(getattr(claim, field_name), getattr(ev, field_name)):
            return field_name
    if (ev.value is None or not math.isfinite(claim.value)
            or abs(claim.value - ev.value) > 0.005 * max(1.0, abs(ev.value))):
        return "value"
    return None


def check(claims: list[Claim], evidence: dict[str, Evidence]) -> list[tuple[Claim, str]]:
    return [(c, why) for c in claims if (why := mismatch(c, evidence.get(c.evidence_id))) is not None]


def remember(tx, items: tuple[Evidence, ...], now: int, ttl_ms: int) -> None:
    for ev in items:
        tx.put(TABLE, ev.id, {**ev.to_json(), "expires_ms": now + ttl_ms})


def valid(snapshot, now: int) -> dict[str, Evidence]:
    return {k: Evidence.from_json(r) for k, r in snapshot.scan(TABLE) if r.get("expires_ms", 0) > now}
