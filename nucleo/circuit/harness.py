"""nucleo/circuit/harness.py — the ERRAND HARNESS: what END STATE a turn implied, verified against the REAL state.

V2-660: after his «Adelante» the model said «aquí tienes el texto completo» over an EMPTY `documento` card, and
nothing compared the claim with the screen until he complained (session 0141a72a).

WHAT THIS IS. A small ledger of GOALS — (kind, target, the operator's words) — born when a turn implies
an end state, verified by the readers of the product's own truth (`verify.card_view`, `verify.card_on_screen`), and
consulted at two seams (a third, the turn end reading the reply for a CLAIM of delivery — «aquí lo tienes» — and
speaking a follow-up after it, went in V2-851 F5: a phrase table over our own reply and a second line after it):
  · the prompt's live state: an open goal travels as a FACT WITH THE RULE (V2-453) so the next turn cannot
    narrate it as done;
  · the heartbeat: open goals are re-verified, closed when met (observability), expired when stale.

WHAT THIS IS NOT. Not a scenario script: goals are typed by what the turn TOUCHED (a widget id, a task),
never by the words of one errand; a widget whose truth cannot be read yields `None` (unverifiable) and the
harness stays silent about it — a wrong «you did not deliver» over a delivered card is worse than none.
Verifiers are the RESOURCE half (nailed down, testable); what to deliver stays the model's and the
worker's call (the brain-worker doctrine).
"""
from __future__ import annotations

import time
import unicodedata


TTL_S = 300.0          # an errand nobody could deliver in five minutes is history, not a live goal

KIND_WIDGET_CONTENT = "widget_content"


def _norm(s: str) -> str:
    n = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in n if not unicodedata.combining(c)).lower()


# ── the ledger ──────────────────────────────────────────────────────────────────────────────────────────
#: V2-776 M4 — the goals are no longer a registry of this module: they are entries of the ONE spec ledger
#: (`nucleo/circuit/spec.py`), marked `source="shown"`. What stays here is what makes them different from an action's
#: end state — they are verified by this module's readers, they speak only when a reply CLAIMS delivery, and they
#: expire at `TTL_S` — so `circuit.tick` leaves them alone (`SOURCE`).
SOURCE = "shown"


def _ledger():
    from nucleo.circuit import spec as _spec
    return _spec


def _expire(now: float) -> None:
    for g in _ledger().open_specs(now):
        if g.get("source") == SOURCE and now - float(g.get("born") or now) > TTL_S:
            g["why"] = "expired"                               # never read before its time ran out
            from nucleo import circuit as _circuit
            _circuit.settle(g, verdict="unverifiable", now=now)
            _emit("🕰 arnés: objetivo caducado sin verificar", g)


def open_goals(now: float | None = None) -> list[dict]:
    now = time.time() if now is None else now
    _expire(now)
    return [g for g in _ledger().open_specs(now) if g.get("source") == SOURCE]


def reset() -> None:
    led = _ledger()
    led._OPEN[:] = [e for e in led._OPEN if e.get("source") != SOURCE]


# ── the verifiers (the RESOURCE half: read the product's own truth, never a copy of it) ─────────────────
async def verify(goal: dict) -> bool | None:
    """True = met · False = unmet · None = this goal's truth cannot be read (the harness stays silent).

    The verdict is REMEMBERED on the goal (`last`) because the prompt cannot await one: see `prompt_lines`.
    """
    from nucleo.circuit import verify as _verify
    goal["checks"] = int(goal.get("checks") or 0) + 1
    out: bool | None = None
    if goal["kind"] == KIND_WIDGET_CONTENT:
        view = _verify.card_view(goal["target"])
        if not view or "empty" not in view or str(view.get("error") or "").strip():
            out = None                       # a widget that does not declare emptiness is unverifiable
            if goal.get("last_seen") != "unreadable":
                _emit("🫥 arnés: objetivo NO verificable — la app no declara si está vacía", goal)
        elif view.get("empty"):
            out = False
            goal["why"] = "empty"
        else:
            opened = _verify.card_on_screen(goal["target"])
            out = True if opened is None else bool(opened)
            goal["why"] = "" if out else "off_screen"
    goal["last"] = out
    goal["last_seen"] = {True: "met", False: "unmet"}.get(out, "unreadable")
    return out


async def sweep(now: float | None = None) -> list[dict]:
    """Heartbeat: re-verify open goals; a met one closes with an event. Returns the goals closed now."""
    now = time.time() if now is None else now
    closed: list[dict] = []
    for g in open_goals(now):
        try:
            ok = await verify(g)
        except Exception:
            ok = None
        if ok:
            from nucleo import circuit as _circuit
            _circuit.settle(g, verdict="met", now=now)
            _emit("✅ arnés: objetivo conseguido", g)
            closed.append(g)
    return closed


def _emit(label: str, g: dict, extra: dict | None = None) -> None:
    try:
        from voice.observer import emit
        emit("brain", label, text=g.get("text", "")[:120], role="system",
             extra={"goal": g.get("id"), "goal_kind": g.get("kind"), "target": g.get("target"),
                    "status": g.get("status"), **({"trace": g["trace"]} if g.get("trace") else {}),
                    **(extra or {})})
    except Exception:
        pass
