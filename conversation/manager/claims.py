"""A numeric claim about data is published only if it matches its evidence — whole, not just the number.

The model states each numeric claim of its reply as structure: who (entity), when (period), what (metric), which way
(direction) and how much (value), naming the evidence it rests on. The evidence is what a tool of this run — or of an
earlier run, still valid — returned. A claim that does not match ALL of it blocks the publication: the run repairs it
once or stays silent. The checker never chooses a tool and never reads the reply's prose.

Three classes of claim (v3.1 §1.10 bis):
  · against STRUCTURED evidence (it carries a value): the whole match, as always;
  · against TEXT evidence (a read with no structure): its value is among the figures of that text, which the host's
    adapter read from the tool's output — this package reads no text. A KNOWN LIMIT: against a text, the entity,
    the period and the metric are not compared — a true figure said of the wrong thing passes; only structured
    evidence gives that;
  · DERIVED (the model counted or computed it from what it read): it cites evidence of THIS run, names its operation
    and its operands — each one a figure of that evidence — and its value is what the operation gives from them. A
    value this run already refused cannot come back as derived. With the door closed, a derived claim matches nothing.
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
    op: str = ""                              # a derived figure's operation (OPS)
    operands: tuple[float, ...] = ()          # …and what it was computed from, each a figure of its evidence

    @classmethod
    def from_args(cls, d: dict) -> "Claim":
        """Never raises: a value that is absent or not a number is NaN — and NaN never matches."""
        try:
            value = float(d.get("value"))
        except (TypeError, ValueError):
            value = math.nan
        return cls(str(d.get("entity", "")), str(d.get("period", "")), str(d.get("metric", "")),
                   str(d.get("direction", "")), value, str(d.get("evidence_id", "")), d.get("derived") is True,
                   str(d.get("op", "")), _numbers(d.get("operands")))


def _numbers(v) -> tuple[float, ...]:
    out = []
    for x in v if isinstance(v, (list, tuple)) else ():
        try:
            out.append(float(x))
        except (TypeError, ValueError):
            out.append(math.nan)             # an operand that is not a number matches no figure
    return tuple(out)


def _count(a: tuple) -> float:
    return float(len(a))


def _sum(a: tuple) -> float:
    return math.fsum(a)


def _difference(a: tuple) -> float:
    return a[0] - a[1] if len(a) == 2 else math.nan


def _mean(a: tuple) -> float:
    return math.fsum(a) / len(a)


def _ratio(a: tuple) -> float:
    return a[0] / a[1] if len(a) == 2 and a[1] else math.nan


def _percent(a: tuple) -> float:
    return 100 * _ratio(a)


#: the operations a derived figure may declare, each from its operands, named by its function
OPS = {f.__name__[1:]: f for f in (_count, _sum, _difference, _mean, _ratio, _percent)}


def _same(a: str, b: str) -> bool:
    return a.strip().casefold() == b.strip().casefold()


def _near(a: float, b: float) -> bool:
    return abs(a - b) <= 0.005 * max(1.0, abs(b))


def _in_text(x: float, figures: tuple) -> bool:
    """A figure of a TEXT, whatever its sign: a text writes a fall as «down 4.98» and the claim states it as -4.98 —
    which way it went is the claim's `direction`, not a figure the text has to spell with a minus."""
    return math.isfinite(x) and any(_near(abs(x), abs(f)) for f in figures)


def _derived(claim: Claim, ev: Evidence, refused: tuple) -> str | None:
    figures = ev.numbers + ((ev.value,) if ev.value is not None else ())
    if not figures:
        return "no_figures"
    if any(_near(claim.value, v) for v in refused):
        return "was_refused"                              # a value refused in this run does not come back derived
    if claim.op not in OPS or not claim.operands:
        return "no_operation"
    if not all(_in_text(x, figures) for x in claim.operands):
        return "operand"
    got = OPS[claim.op](claim.operands)
    return None if math.isfinite(got) and math.isfinite(claim.value) and _near(claim.value, got) else "derived_value"


def mismatch(claim: Claim, ev: Evidence | None, this_run: frozenset = frozenset(), derived_open: bool = True,
             refused: tuple = ()) -> str | None:
    """Why the claim does not match its evidence, or None when it does. `refused`: values this run already refused."""
    if claim.derived:
        if not derived_open:
            return "derived_closed"
        if claim.evidence_id not in this_run:
            return "not_this_run"
        return "no_evidence" if ev is None else _derived(claim, ev, refused)
    if ev is None:
        return "no_evidence"
    if ev.value is None and ev.numbers:                   # a text: the value is one of its figures
        return None if _in_text(claim.value, ev.numbers) else "value"
    for field_name in ("entity", "period", "metric", "direction"):
        if not _same(getattr(claim, field_name), getattr(ev, field_name)):
            return field_name
    if ev.value is None or not math.isfinite(claim.value) or not _near(claim.value, ev.value):
        return "value"
    return None


def detail(claim: Claim, why: str, ev: Evidence | None) -> dict:
    """What a refused claim said and what its evidence holds nearest to it — so a refusal can be judged afterwards
    (a figure the checker missed, or one the model made up). Bounded: three figures, six operands."""
    figures = (ev.numbers + ((ev.value,) if ev.value is not None else ())) if ev is not None else ()
    near = sorted(figures, key=lambda f: abs(abs(f) - abs(claim.value)) if math.isfinite(claim.value) else 0)[:3]
    return dict(why=why, value=claim.value if math.isfinite(claim.value) else None, evidence_id=claim.evidence_id,
                derived=claim.derived, op=claim.op, operands=list(claim.operands[:6]), near=near,
                figures=len(figures))


def check(claims: list[Claim], evidence: dict[str, Evidence], this_run: frozenset = frozenset(),
          derived_open: bool = True, refused: tuple = ()) -> list[tuple[Claim, str]]:
    """The claims that do not match, each with why. `this_run`: the evidence ids a read of this run returned."""
    return [(c, why) for c in claims
            if (why := mismatch(c, evidence.get(c.evidence_id), this_run, derived_open, refused)) is not None]


def remember(tx, items: tuple[Evidence, ...], now: int, ttl_ms: int) -> None:
    for ev in items:
        tx.put(TABLE, ev.id, {**ev.to_json(), "expires_ms": now + ttl_ms})


#: how many of the newest evidence rows a check reads: what a few runs returned, never the account's history
KEEP = 256


def valid(snapshot, now: int) -> dict[str, Evidence]:
    return {k: Evidence.from_json(r) for k, r in snapshot.recent(TABLE, KEEP) if r.get("expires_ms", 0) > now}
