"""nucleo/circuit/reported.py — an end state read from what the app REPORTS it shows (V2-884 C4, A6).

A clause may name `report.<field>` (`{"widget": "youtube", "field": "report.playing", "is": "true"}`): the value is
the one the app's live surface reported through the state door (`widgets/state_render.read`), never the order its
store holds — the order said «play» the moment the op ran, and a «done» read from it was said over a player that
never moved. Read on the screen the app lives on (a `single` app), or on the clause's `dev`.

Three marks, each deciding one thing in the circuit:
  · known   — judged like any scalar (agrees → met; contrary → unmet once `INLINE_GRACE_S` is reached);
  · pending — the order changed and the surface has not acked it yet: the act WAITS (never unverifiable, never unmet);
  · unknown — no ack within `PENDING_S`, or no surface reports the app: the act settles `unverifiable` with the
    reason `no_ack` — said as asked, never as done. A late ack still resolves the field, not the act's verdict.

`expect: changed` takes its base from the valid report at the act's birth, and from the order key when there is none.
"""
from __future__ import annotations

from loguru import logger

PREFIX = "report."
KNOWN, PENDING, UNKNOWN, UNDECLARED = "known", "pending", "unknown", "undeclared"
#: The reason an act whose app never confirmed it settles with (`verdict.REASONS`).
NO_ACK = "no_ack"


def field_of(clause) -> str:
    """The reported field a clause names, "" when it names a store field (or nothing)."""
    f = str((clause or {}).get("field") or "") if isinstance(clause, dict) else ""
    return f[len(PREFIX):] if f.startswith(PREFIX) else ""


def read(clause: dict) -> tuple[str, object]:
    """`(mark, value)` of a reported field on the screen the app lives on; the value only when `known`."""
    name = field_of(clause)
    try:
        from widgets import state_decl, state_render
        wid = str(clause.get("widget") or "").strip().lower()
        if name not in state_decl.report_fields(state_decl.of(wid)):
            return UNDECLARED, None
        got = state_render.read(wid, wid if "::" in wid else None, str(clause.get("dev") or "") or None)
    except Exception as e:  # noqa: BLE001 — a report that cannot be read is not one the app made
        logger.debug(f"reported: {clause.get('widget')}.{name} unreadable ({e!r})")
        return UNDECLARED, None
    surfaces = got.get("surfaces") or []
    if not surfaces:
        return UNKNOWN, None                 # no screen reports the app: nothing confirms the order
    s = surfaces[0]                          # where it lives (a single app), this turn's screen first
    if name in s.get("pending", []):
        return PENDING, None
    if name in (s.get("fields") or {}):
        return KNOWN, s["fields"][name]
    return UNKNOWN, None


def value(clause: dict):
    """The known value, or None — the scalar `verify` judges."""
    mark, v = read(clause)
    return v if mark == KNOWN else None


def baseline(clause: dict):
    """What a `changed` clause compares against: the report at birth, else the order key the field follows."""
    mark, v = read(clause)
    if mark == KNOWN:
        return v
    try:
        from widgets import state_decl, store
        wid = str(clause.get("widget") or "").strip().lower()
        st = state_decl.of(wid)
        key, inverted = state_decl.follows(state_decl.report_fields(st).get(field_of(clause)))
        path = state_decl.declared_order(wid).get(key) if key else None
        if not path:
            return None
        got = state_decl.order_value(store.load(wid, {}) or {}, path)
        return (not got) if inverted else got
    except Exception as e:  # noqa: BLE001
        logger.debug(f"reported: no baseline for {clause.get('widget')} ({e!r})")
        return None


def awaiting(done_when) -> str:
    """`wait` over a whole condition."""
    from nucleo.circuit import verify
    return wait(verify._clauses(done_when)[1])


def mark(e: dict, out) -> str:
    """Mark an open spec `awaiting` when its condition reads None for want of the app's ack (said once on its
    timeline): `circuit.tick` settles a `no_ack` and the op's own ending leaves both to the pulse."""
    e["awaiting"] = "" if out is not None or e.get("met_at_birth") else awaiting(e.get("done_when"))
    if e["awaiting"] and e.get("last_seen") != e["awaiting"]:
        from nucleo.circuit import spec
        spec._emit("⏳ spec: ordered — the app has not confirmed it yet", e, awaiting=e["awaiting"])
    return e["awaiting"]


def wait(clauses: list) -> str:
    """Why an end state that reads None is not unreadable: `pending` (wait for the ack) or `no_ack` (none came), ""
    when no clause names a report or every reported one is known."""
    marks = [read(c)[0] for c in clauses if field_of(c)]
    if PENDING in marks:
        return PENDING
    return NO_ACK if UNKNOWN in marks else ""
