"""The introduction is ONE phase of the genesis, run once, and it closes (A7, 2026-11-12).

Measured on the operator's first session after a reset: `introduction.start()` ran at boot, before the language
was locked, saw `is_active()` false and returned — so the watcher never subscribed, the phase never closed, and its
block rode every turn. On the turn he gave his name the pack still said «you do not know his name» (the memory
agent writes it two seconds after the turn), and the model confirmed what it had just read.

Three facts, each with its red disarm: the watcher is always subscribed and reads the condition per turn; the
block reads THE TURN (he just answered our question → the block names THAT question, never a goal guessed from the
order — I1: «sí, claro» to the tour offer was read as his name); the phase closes on two facts — his name known AND
the offer told by the turn that carried it — and a fresh session, Spanish or English, closes it in three turns.
Also (A7 P2): the recheck after the memory agent is deterministic only (the judge ran twice), `turn.completed` is
published with the prompt capture off (the phase never closed), and the wake-word line forbids asking his name only
when it is in the state.
"""
from __future__ import annotations

import asyncio




class _Q:
    def __init__(self):
        self.items: asyncio.Queue = asyncio.Queue()

    async def get(self):
        return await self.items.get()


async def _turn(q: _Q, *, reply: str = "Hola, soy Johnny. ¿Cómo te llamas?") -> None:
    """One `turn.completed` delivered to the watcher, with the window the observer publishes."""
    await q.items.put({"window": [{"role": "assistant", "text": reply}], "trace": "T"})
    for _ in range(4):
        await asyncio.sleep(0)


# ── the watcher is armed before the language, and reads the condition per turn ──────────────────────────

# ── the block reads the turn, not the stale state ────────────────────────────────────────────────────────

def test_the_turn_topic_is_published_with_the_prompt_capture_off(monkeypatch):
    """A7 P2: with `ZAELAR_LOG_PROMPTS=0` nothing published `turn.completed` and the phase never closed."""
    import bus
    from voice import observer
    monkeypatch.setenv("ZAELAR_LOG_PROMPTS", "0")
    got, emitted = [], []
    monkeypatch.setattr(bus, "emit_sync", lambda topic, payload: got.append(topic))
    monkeypatch.setattr(observer, "emit", lambda *a, **k: emitted.append(a))
    observer.turn_detail(system="s", window=[{"role": "assistant", "content": "hola"}], user="pepe")
    assert got == ["turn.completed"] and not emitted, "the capture switch also switched the topic off"

