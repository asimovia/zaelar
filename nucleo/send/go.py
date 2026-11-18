"""The act on his yes, and what follows it: the card's act off the loop, its line, the receipt followed — run to the
end even when his turn is cut meanwhile (the line is then said out of turn), and the next queued message opened."""
from __future__ import annotations

import asyncio

from loguru import logger

from nucleo.send import ask as _ask
from nucleo.send import deliver as _deliver
from nucleo.send import draft as _draft
from nucleo.send import receipt as _receipt


def _note(e: Exception) -> None:
    logger.debug(f"send.go: {type(e).__name__}: {e}")


async def send(d) -> str:
    """The act and what follows it run to the end even if his turn is cut meanwhile: a message that left is never
    left unreported (its line is said out of turn when the turn that asked is gone)."""
    d.state = _draft.SENDING
    job = asyncio.ensure_future(_sent(d))
    try:
        return await asyncio.shield(job)
    except asyncio.CancelledError:
        job.add_done_callback(_say_late)
        from nucleo.send import intake as _intake
        job.add_done_callback(lambda _j: asyncio.ensure_future(_intake.open_the_next()))
        raise


def _say_late(job) -> None:
    try:
        line = job.result()
        if line:
            from nucleo.send import receipt
            asyncio.ensure_future(receipt.say_out(line, f"send:late:{abs(hash(line))}"))
    except Exception as e:  # noqa: BLE001
        _note(e)


async def _sent(d) -> str:
    from nucleo.send import owner
    try:
        res = await asyncio.to_thread(owner._run, d)
    except Exception as e:  # noqa: BLE001
        res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    if not (isinstance(res, dict) and res.get("ok")):
        why = str((res or {}).get("message") or (res or {}).get("error") or "unknown")[:200]
        owner._emit("refused", d, why=why)
        if d.kind == "act":
            from nucleo.send import act as _act
            _draft.close(d, _draft.FAILED)
            return await _act.line(d, "failed", why=why)
        d.state, d.asked = _draft.OPEN, _draft.WHO        # his text stays: he decides what to do with it
        return await _ask.line("send_cannot", who=d.target.get("name"), why=why)
    d.ref = _deliver.ref_of(res)
    _draft.close(d, _draft.SENT)
    if res.get("later"):
        owner._emit("held for later", d, ref=d.ref, at=res["later"])
        return await _ask.line("send_later", who=d.target.get("name"), when=_ask.when(res["later"]))
    owner._emit("queued", d, ref=d.ref)
    _receipt.follow_soon(d)
    if d.kind == "act":
        from nucleo.send import act as _act
        return await _act.line(d, "going")
    return await _ask.line("send_going", who=d.target.get("name"))
