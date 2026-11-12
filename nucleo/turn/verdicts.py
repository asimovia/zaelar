"""How a verdict of the brief is READ — asymmetric, in one place (refactor2710-07).

A verdict and the model can disagree. Who wins depends on the direction:

  · LICENCE (≥ `LICENCE`, Jev's own floor): a verdict is readable — a guard may consult it;
  · ACT (≥ `consent.intent_act_at`, `to_act`): a verdict may launch, complete or relaunch an act the model did not
    make — the screen action, the request type and `corrects_last` are all read at this one floor;
  · VETO (≥ `VETO`): a verdict may refuse what the model CALLED only when it is this sure — a weaker reader never
    silently overrules a stronger one (CRIT-K1/K2);
  · between the two, a disagreement with the model's call is a DOUBT, and a doubt about what will be touched is asked
    (`consent.ASK_WHICH`), never refused in silence and never executed blind.

The pieces that already read this way are here too: two calls the verdict heard in his sentence are two orders
(`both_heard`, was `two_orders`), and an order is sure at the operator's own threshold (`sure_order`). Every read emits the `jev read` event (`nucleo.jev.read`).
"""
from __future__ import annotations

from loguru import logger

#: A verdict below this is a shrug (`jev.MIN_CONFIDENCE`).
LICENCE = 0.5
#: A verdict must be at least this sure to refuse what the model called.
VETO = 0.85
#: A call the verdict heard with at least this mass in the distribution was in his sentence (`both_heard`).
HEARD_FLOOR = 0.15

RUN, VETOED = "run", "veto"


def read(handle, key: str, fallback, *, min_confidence: float | None = None):
    """One verdict out of the brief: `(choice, info)` when ready and at least `min_confidence` (default the licence),
    else `(fallback, info-or-None)`. Never waits, never raises."""
    try:
        from nucleo import jev as _jev
        return _jev.read(handle, key, fallback, min_confidence=LICENCE if min_confidence is None else min_confidence)
    except Exception:  # noqa: BLE001
        return fallback, None


def act_floor() -> float:
    """The ACT floor: the operator's `consent.intent_act_at` (his «at 60 % we do it»), never under `LICENCE`."""
    try:
        from nucleo import consent
        return max(consent.intent_act_at(), LICENCE)
    except Exception as e:  # noqa: BLE001 — an unreadable knob never lowers the floor
        logger.debug(f"verdicts: intent_act_at unreadable — {e!r}")
        return 0.6


def to_act(handle, key: str, fallback):
    """A verdict read to LAUNCH or RELAUNCH an act (the screen action that completes an empty turn, an order, a redo, a
    binding to a waiting task's question): ONE floor, `act_floor`, never `LICENCE` nor a reader's own higher bar (A7;
    `route_by_verdict` declares why it reads the licence). `(choice, info)` as `read`."""
    return read(handle, key, fallback, min_confidence=act_floor())


def against_the_model(handle, key: str, agrees) -> str:
    """The model CALLED something this verdict is about: may it run? `agrees(choice)` says whether the verdict's choice
    is what the model did. `run` · `veto` (a disagreeing verdict ≥ VETO). A disagreeing verdict between LICENCE and VETO
    is a recorded doubt and the call runs (V2-886 D2); no verdict, or one below the licence, lets the call run."""
    choice, info = read(handle, key, None, min_confidence=0.0)
    if not info or not choice:
        return RUN
    try:
        if agrees(choice):
            return RUN
    except Exception as e:  # noqa: BLE001 — an unreadable comparison never refuses
        logger.debug(f"verdicts: {key} comparison failed — {e!r}")
        return RUN
    conf = float(info.get("confidence") or 0.0)
    if conf >= VETO:
        return VETOED
    if conf >= LICENCE:
        # V2-886 D2: a disagreeing verdict below the veto is a DOUBT, not a question — the model's call runs and the
        # doubt is recorded (operator, 2026-11-11: «at 60 % sure we do it, and he tells us if not»). It used to ask
        # «which one?» here, interrupting him over the engine's own uncertainty.
        try:
            from voice.observer import emit
            emit("brain", "🤔 a verdict doubts the call below the veto — the call runs", role="system",
                 text=f"{key}: {choice}", extra={"cat": "flash", "kind_diag": "doubt", "key": key,
                                                  "verdict": str(choice), "confidence": round(conf, 2)})
        except Exception as e:  # noqa: BLE001 — the call runs either way; only the record is lost
            logger.debug(f"verdicts: doubt not recorded — {e!r}")
    return RUN


def mass(handle, key: str, choice: str) -> float:
    """The probability the verdict's distribution gave `choice` (0 when it cannot say)."""
    try:
        from nucleo import jev as _jev
        verdict = _jev.peek(handle) if isinstance(handle, dict) else None
        ans = (verdict or {}).get(key) or {}
        probs = ans.get("probabilities") or ans.get("probs") or {}
        return float(probs.get(choice) or 0.0)
    except Exception:  # noqa: BLE001
        return 0.0


def both_heard(handle, wid: str, action: str, other: str) -> bool:
    """Did `screen_action` hear BOTH payload-less actions on this card in his sentence? Then they are two ORDERS, not the
    model enumerating alternatives (`build-a-video-playlist-from-links` ES, 2026-10-10: «súbele… y pásate al siguiente»).
    False when it cannot say — the enumeration guard holds."""
    from nucleo.turn import brief
    if not handle or not action or not other or action == other:
        return False
    base = str(wid or "").split("::", 1)[0].strip().lower()
    return (mass(handle, brief.TARGET_KEY, f"{base}:{action}") >= HEARD_FLOOR
            and mass(handle, brief.TARGET_KEY, f"{base}:{other}") >= HEARD_FLOOR)


def sure_order(handle, widget_id: str, action: str) -> bool:
    """Is the turn read as an ORDER, and its action as exactly `widget_id:action`, both at or above the operator's
    `consent.intent_act_at`? The one place a doubt is weighed against his threshold. Never raises."""
    try:
        from nucleo.turn import brief
        kind, k_info = to_act(handle, brief.REQUEST_KEY, "")
        target, t_info = to_act(handle, brief.TARGET_KEY, "")
        owner, _sep, name = str(target or "").rpartition(":")
        return bool(k_info and t_info) and str(kind) == "order" and name == action \
            and owner.split("::", 1)[0].lower() == str(widget_id or "").split("::", 1)[0].lower()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"verdicts: sure_order skipped — {e}")
        return False
