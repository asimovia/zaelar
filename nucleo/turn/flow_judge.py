"""The flow judge: whose is this request, within the turn's budget (V2-878 §3 e).

`judge` is the model half of `flow_of` (the containment yardstick is the other): it names the open flow a request
belongs to, or none, and says when it ran out of time. A timeout is NOT «none»: with an errand open, the door asks him
(`flow_of.route` → `undecided`, `which_flow`), it never guesses a new errand.
"""
from __future__ import annotations

import asyncio

from loguru import logger

from nucleo.turn import thread_event as _thread


async def judge(text: str, pool: list[dict]) -> tuple[str, bool]:
    """(the id of the flow the model judge names, or "") and whether it ran out of the turn's budget. Never raises."""
    from nucleo.turn import flow_of as _f
    try:
        from nucleo.request import append as _dedup
        with _thread.judging("flow_of"):           # the judge's own event names who asked
            tid = await asyncio.wait_for(asyncio.to_thread(
                _dedup.about_a_live_errand, text, [(str(c["id"]), str(c["request"])) for c in pool]), _f.JUDGE_S)
        return str(tid or ""), False
    except asyncio.TimeoutError:
        logger.warning(f"flow_of: the judge did not answer within {_f.JUDGE_S}s — undecided")
        _thread.judge_timeout(text, pool, budget_s=_f.JUDGE_S)
        return "", True
    except Exception as e:  # noqa: BLE001 — fail-open: no flow, the door opens a new one
        logger.warning(f"flow_of: the judge failed, treating as a new flow — {type(e).__name__}: {e}")
        return "", False

