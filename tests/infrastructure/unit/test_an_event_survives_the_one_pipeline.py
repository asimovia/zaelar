"""What the old text channel emitted is still emitted by the one turn, and the new doors say their verdict (V2-826 §2b,
refactor2710-01).

Deleting `nucleo/flash/probe*.py` moved the typed channel onto the voice turn. Of the literal (kind, label) pairs those
files emitted, every one has its counterpart on the voice turn except two mirrors retired on purpose — «🔓 close
licenciado por Jev (espejo del provider)» and «📩 system note → FlashBrain (probe)» copied the voice turn's own
events («… (la gramática no veía orden, dos lectores de acuerdo)», «📩 system note → FlashBrain»), which a typed turn
now emits itself. The pairs below may move between files, never vanish; a pair retired on purpose leaves this set in
the same commit, with the reason.

The new mechanism emits its verdict: every consequence door a turn reaches is a `consequence` event (door, blocked,
trace), live or dry, so the timeline shows what a dry turn kept from the world.
"""
from __future__ import annotations

import ast
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]

FROZEN = {
    # («💬 chat (canal de texto)» went with `cli/api._wall`: the manager's mouth paints both sides of a typed line)
    # («📩 system note → FlashBrain» went with the notes mailbox, V2-851 F5: no note is drained into a turn)
    ("perf", "🧾 turno (prompt+ventana+tools+decisión)"),       # the turn's decision row, typed or spoken
    ("brain", "🔓 close licenciado por Jev (la gramática no veía orden, dos lectores de acuerdo)"),
}
#: Kinds emitted with a computed label: the kind itself must survive.
FROZEN_KINDS = {"consequence"}


def _emitted() -> tuple[set, set]:
    pairs, kinds = set(), set()
    for root in ("nucleo", "voice"):
        for p in (ENGINE / root).rglob("*.py"):
            for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
                if not isinstance(n, ast.Call):
                    continue
                name = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
                if "emit" not in name or not n.args or not isinstance(n.args[0], ast.Constant):
                    continue
                kinds.add(n.args[0].value)
                if len(n.args) > 1 and isinstance(n.args[1], ast.Constant):
                    pairs.add((n.args[0].value, n.args[1].value))
    return pairs, kinds


def _missing(pairs: set, kinds: set) -> list:
    return sorted(FROZEN - pairs) + sorted(FROZEN_KINDS - kinds)


def test_no_frozen_event_of_the_typed_turn_vanishes():
    assert not _missing(*_emitted()), f"an event stopped being emitted: {_missing(*_emitted())}"


def test_disarm_a_dropped_event_is_named():
    pairs, kinds = _emitted()
    turn_row = ("perf", "🧾 turno (prompt+ventana+tools+decisión)")
    assert _missing(pairs - {turn_row}, kinds) == [turn_row]
    assert _missing(pairs, kinds - {"consequence"}) == ["consequence"]


def test_a_door_reached_is_a_consequence_event_with_its_verdict_and_trace():
    from nucleo import consequence
    from voice import observer, trace
    n0 = len(observer._events)
    tok = trace._ctx.set(("t-consequence", ""))
    try:
        with consequence.dry_turn(ingest=True):
            assert consequence.passes("music", arg="jazz") is False
            assert consequence.passes("memory.ingest") is True
    finally:
        trace._ctx.reset(tok)
    got = [e for e in observer._events[n0:] if e.get("kind") == "consequence"]
    assert [(e["label"], e["door"], e["verdict"], e["dry"]) for e in got] == \
        [("music", "music", "veto", True), ("memory.ingest", "memory.ingest", "pass", True)]
    assert got[0]["arg"] == "jazz"
    assert all(e.get("trace") == "t-consequence" for e in got)
