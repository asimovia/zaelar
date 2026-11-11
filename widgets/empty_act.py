"""widgets/empty_act.py — an act that filled none of its declared slots and changed nothing is NOT done (V2-879).

Measured in the sandbox, es and en, 4 of 4: «pon un temporizador de 10 minutos» reached the timer as `set {"minutes":
10}` (once `{"duration": 600}`); the card reads `seconds`, set 0, answered `ok: True`, and the turn said «Listo» over a
timer that never ran. The model spoke the card's act in its own vocabulary and the card's `ok` was taken as the act.

Why it is judged AFTER the act and not refused before it: twelve cards' handlers read keys their manifests do not
declare (`documento.append` takes `text` beside the declared `body`; `map.show` reads `points`/`items`), so «fills none
of the declared slots» alone would refuse calls that work today. The handler is the truth about what it read; the
card's own data says whether anything happened. So, at the single funnel (`server_api._dispatch`): a call that carries
keys of its own and fills none of the act's declared slots (`contract.unfilled`) runs; if the card answered ok and its
data is exactly what it was before, the answer becomes the refusal (`slots_unfilled`, naming the declared slots) — the
turn's one mouth says it in his language, never «done». An act that DID change the card keeps its answer, and what it
changed is judged by the act's declared end state (`done_when`), not here. A backed card (queued to its owner) and an
unreadable view are left as they are: this never invents a failure it cannot see.
"""
from __future__ import annotations

from loguru import logger


async def _view(wid: str, payload: dict):
    from . import server_api
    q = str((payload or {}).get("q") or "")

    def call(view_data):
        try:
            return view_data(q=q)
        except TypeError:
            return view_data()
    try:
        got = await server_api._run_widget(wid, "view_data", call)
        return None if got is server_api._MISSING else got
    except Exception as e:  # noqa: BLE001 — an unreadable view judges nothing
        logger.debug(f"empty_act: view of {wid} unreadable — {type(e).__name__}: {e}")
        return None


async def run(wid: str, action: str, payload: dict, act):
    """`await act(wid, action, payload)`, with its answer turned into the `slots_unfilled` refusal when the call
    filled none of the act's declared slots and the card did not change. Never raises beyond what `act` raises."""
    from . import contract
    try:
        probe = contract.unfilled(wid, action, contract._spec(wid, action), payload)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"empty_act: {wid}:{action} unreadable — {e!r}")
        probe = None
    before = await _view(wid, payload) if probe else None
    res = await act(wid, action, payload)
    if probe is None or before is None or not isinstance(res, dict) or res.get("ok") is False or res.get("queued"):
        return res
    if await _view(wid, payload) != before:
        return res
    try:
        from voice.observer import emit
        emit("widget", "action_refused", text=str(probe.get("detail") or "")[:160],
             extra={"id": wid, "action": str(action), "error": contract.SLOTS_UNFILLED,
                    "field": ",".join(probe.get("unmet") or []), "sent": ",".join(probe.get("sent") or []),
                    "is_error": True})
    except Exception:  # noqa: BLE001
        pass
    return probe
