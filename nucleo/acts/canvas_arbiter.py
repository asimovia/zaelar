"""nucleo/acts/canvas_arbiter.py — ONE decision for every canvas mutation: WHO ordered it (V2-653; INI-078 L1).

Every show or close crossing the door (`nucleo.acts.canvas.apply`) is judged by its PROVENANCE, a closed set: the
operator's hand, the canvas reporting what it already did, the lifecycle, a task's own card (one sheet per task), the
manager's turn (`turn:<effect>`), a seeded phrase of the action map. Nothing else orders the canvas: an unknown
provenance is refused (`unknown-src`), never judged by reading his words — the word licences of the old turn went
with it. An internal error is the verdict `arbiter-error`, never a crash at a caller. The `arbiter` event records who
asked for what.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ── the verdict ──────────────────────────────────────────────────────────────────────────────────────────

ALLOW = "allow"
VETO = "veto"


@dataclass
class Verdict:
    allow: bool
    rule: str                       # ONE short kebab-case name — the branch that decided
    evidence: dict = field(default_factory=dict)


def _v(allow: bool, rule: str, **evidence) -> Verdict:
    return Verdict(allow=allow, rule=rule, evidence=evidence)


#: Provenance classes (closed set — anything unrecognized is refused).
_SRC_OPERATOR = ("user",)
_SRC_SYSTEM = ("system",)
_SRC_DETERMINISTIC = ("actionmap", "interrupt")
_SRC_TASK = ("wall", "recall", "sheet")

#: The closed op vocabulary: anything else is refused before the provenance is read.
_OPS = ("show", "close", "data", "screen")


def decide(op: str, wid: str, src: str, *, action: str = "") -> Verdict:
    """`op` ∈ show|close|data|screen; `src` the V2-039 provenance string (`user`, `client:<cause>`, `system[:why]`,
    `worker:<tid>`, `wall:<tid>`, `recall:<id>`, `sheet:<id>`, `turn:<effect>`, `actionmap`, `interrupt`). Never
    raises: an unreadable input is refused with `arbiter-error`."""
    try:
        return _decide(op, wid, src, action=action)
    except Exception as e:  # noqa: BLE001
        return _v(False, "arbiter-error", error=str(e)[:120])


def _decide(op: str, wid: str, src: str, *, action: str = "") -> Verdict:
    op = (op or "").strip().lower()
    wid = (wid or "").strip().lower()
    base_src = (src or "").split(":", 1)[0].strip().lower()
    if op not in _OPS:
        return _v(False, "unknown-op", op=op)
    if base_src in _SRC_OPERATOR:
        return _v(True, "operator-hands")
    from voice import canvas_src
    if src == canvas_src.CLIENT:
        return _v(True, "report")           # the canvas telling what it already did: nothing to obey or veto
    if base_src == "client":
        cause = canvas_src.cause_of(src)
        if cause in canvas_src.LIFECYCLE:
            return _v(True, "lifecycle", cause=cause)
        if cause == canvas_src.BY_ENGINE:
            return _v(True, "engine-echo")
    if base_src in _SRC_SYSTEM:
        return _v(True, "lifecycle")
    if base_src in _SRC_TASK or base_src.startswith("worker"):
        # a task's own card (wall, reopened errand, filled sheet, worker); one card per task: a live errand's is its own
        held = op == "show" and __import__("nucleo.acts.card_owner", fromlist=["x"]).held_by_another(wid, src)
        return (_v(False, "non-owner", owner=held) if held else _v(True, "task-owned", tid=(src.split(":", 1) + [""])[1],
                **({} if base_src.startswith("worker") else {"via": base_src})))
    if base_src == "turn":
        return _v(True, "turn-owned", effect=(src.split(":", 1) + [""])[1])   # the manager's act, by its reservation
    if base_src in _SRC_DETERMINISTIC:
        return _v(True, "seeded-grammar")       # the seeded phrase IS the licence (V2-539/V2-567)
    return _v(False, "unknown-src", src=base_src or "")
