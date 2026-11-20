"""The host's hands for a stop the MODEL ordered (V2-941, plan v3.2 §3): the `Stops` port of a switched session.

The package has already cut our voice (`voice`, `run`, `all`) when it hands the stop here. What is the host's:
  · `voice`, `run`, `all` — the attention window closes, as his spoken stop always closed it;
  · `media`, `all`        — what is playing stops, through each card's declared suspension (`widgets/producers`);
  · `all`                 — his errands in course are cancelled through the screen's own door (`control.cancel_row`),
                            each row ending `cancelled` with the reason. Nothing is deleted.
Local and immediate: the card and errand doors run on the engine's own loop; nothing waits here.
"""
from __future__ import annotations

from loguru import logger

from conversation.manager.commands import SILENCES, Scope

#: how a row this stop cancelled says why
CANCELLED_BY = "stopped by his order"


class HostStops:
    def stop(self, scope: str, endpoint: str | None) -> None:
        s = Scope(scope)
        if s in SILENCES:
            from voice import attention
            attention.close_window(src="voice-order")
        if s in (Scope.MEDIA, Scope.ALL):
            _on_loop(_media)
        if s is Scope.ALL:
            _on_loop(_errands)


def _on_loop(fn) -> None:
    """`fn` on the engine's loop (the one the cards and the errands live on); with none, here."""
    from nucleo import dispatch
    loop = dispatch._LOOP
    if loop is None or not loop.is_running():
        fn()
        return
    loop.call_soon_threadsafe(fn)


def _media() -> None:
    import asyncio

    from widgets import producers
    try:
        asyncio.get_running_loop().create_task(producers.suspend_all(reason=CANCELLED_BY))
    except RuntimeError:                                # no loop: the cards stop as the engine's ⏻ would
        asyncio.run(producers.suspend_all(reason=CANCELLED_BY))


def _errands() -> int:
    """Every errand of his in course, cancelled at its own door: the row ends `cancelled`, nothing is deleted."""
    from nucleo.circuit import ledger
    from nucleo.dispatch import control
    ts = ledger.store()
    n = 0
    for r in ts.tasks_where(states=ts.LIVE_STATES, modes=("now",), visible_only=True, limit=50):
        try:
            n += control.cancel_row(str(r.get("id") or ""), outcome=CANCELLED_BY) == "cancelled"
        except Exception as e:  # noqa: BLE001 — one errand that will not stop never keeps the others running
            logger.warning(f"conversation stops: an errand was not cancelled ({e!r})")
    return n
