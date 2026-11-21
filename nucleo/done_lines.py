"""What already happened, as live-state facts: the open harness goals, the data ops that RAN, the cron line with what
is scheduled, the closed sheets. Moved from `nucleo/flash/live_blocks.py` (refactor2710-08b).
"""
from __future__ import annotations


def done_ops_lines() -> list[str]:
    """V2-707 F6 — WHAT THE ENGINE ALREADY DID TO HIS DATA, with its rule beside it (V2-453's lesson: the
    fact alone changes nothing).

    Measured 2026-09-16 (session 080b96a7, i=10817 and i=10853): two `clear_range` sweeps had run, nine rows
    were gone, and the turn said «In this conversation I never confirmed a deletion, so nothing has been
    removed from your calendar». That was a correct deduction from the only ledger it could see — the
    PENDING confirmations — because nothing carried the EXECUTED ones. The instruction matters as much as the
    fact: what he is disputing is not whether he said yes, it is whether it happened, and only one of those
    two is a thing we know.

    Zero lines when nothing ran, and fail-open: a ledger that cannot be read costs the prompt nothing.
    """
    try:
        from nucleo import done_ops as _done
        rows = _done.recent()
        if not rows:
            return []
        import time as _t
        # V2-778 F2-19 — an op the request record already shows (`recent_lines`) is not listed twice; what no row
        # shows (a CLICK on the card opens none) still is, and the two rules below stay whenever they apply.
        shown = _shown_by_requests()
        listed = [d for d in rows if not any(w == d["wid"] and a == d["action"]
                                             and abs(float(d.get("at") or 0) - at) <= 60 for w, a, at in shown)]
        away = sorted({d["wid"] for d in rows if not _is_open(d["wid"])})
        if not listed and not any(d.get("destructive") for d in rows) and not away:
            return []
        bits = []
        for d in listed or rows:
            ago = max(0, int(_t.time() - float(d.get("at") or _t.time())))
            n = d.get("n")
            bits.append(f"«{d['wid']}:{d['action']}»" + (f" ({n} fila/s)" if isinstance(n, int) else "")
                        + f" hace {ago}s")
        head = ("YA EJECUTADO SOBRE SUS DATOS en esta sesión (hechos del sistema, no de la conversación): "
                + "; ".join(bits) + ".")
        if any(d.get("destructive") for d in rows):
            return [head + " Eso YA PASÓ. Si el operador dice que has borrado o cambiado algo, TIENE RAZÓN: "
                    "no razones desde si hubo confirmación o no —eso es otra cosa— ni le digas que no se ha "
                    "tocado nada. Dile QUÉ se ejecutó y ofrécele deshacerlo o revisarlo."]
        # Demo pass 59 (S1): «results:present hace 140s» + «cuéntalo como hecho» over a sheet he had put away,
        # and «so how did the monitors go, show me» got «Done.» with the card still in the dock. Done to the
        # DATA is not on the SCREEN: a card that is not open now says so, with the one call that brings it.
        tail = (f" Ojo: {', '.join(away)} NO está en pantalla ahora — si pide verlo, `show_widget` lo trae; "
                "decir «hecho» sin traerlo es mentirle.") if away else ""
        return [head + " Si pregunta por ello, cuéntalo como hecho en vez de volver a hacerlo." + tail]
    except Exception:  # noqa: BLE001
        return []


def _shown_by_requests() -> list[tuple[str, str, float]]:
    """(widget, action, when) of the inline request rows the turn's record block already reports."""
    try:
        from nucleo.circuit import ledger as _tasks
        out = []
        for r in _tasks.store().tasks_where(states=("done", "failed", "running"), modes=("now",), visible_only=False,
                                            limit=24) or []:
            wa = str(r.get("outcome") or "")
            if r.get("kind") == "inline" and ":" in wa and " " not in wa:
                w, a = wa.split(":", 1)
                out.append((w.split("::", 1)[0], a, float(r.get("finished_at") or r.get("started_at") or 0)))
        return out
    except Exception:  # noqa: BLE001 — nothing readable: list everything, as before
        return []


def _is_open(wid: str) -> bool:
    """Whether a card of this widget (base id or any of its instances) is ON SCREEN now — open minus minimized
    (V2-776 L2, the one reader in `nucleo/truth.py`). Fail-open to True: a state that cannot be read must not
    add a warning that may be false."""
    try:
        from nucleo import truth as _truth
        state = _truth.canvas_state(wid)
    except Exception:  # noqa: BLE001
        return True
    return True if state is None else state in ("visible", "maximized")


