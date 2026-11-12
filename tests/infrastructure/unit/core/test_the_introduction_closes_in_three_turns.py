"""The introduction is ONE phase of the genesis, run once, and it closes (A7, 2026-11-12).

Measured on the operator's first session after a reset: `introduction.start()` ran at boot, before the language
was locked, saw `is_active()` false and returned — so the watcher never subscribed, the phase never closed, and its
block rode every turn. On the turn he gave his name the pack still said «you do not know his name» (the memory
agent writes it two seconds after the turn), and the model confirmed what it had just read.

Three facts, each with its red disarm: the watcher is always subscribed and reads the condition per turn; the
block reads THE TURN (he just answered our question → that goal is «he just told you», not «unknown»); the phase
closes on two facts — his name known AND the offer told — and a fresh session, Spanish or English, closes it in
three turns, so the fourth prompt carries no block.
"""
from __future__ import annotations

import asyncio

import pytest

from i18n import langs
from nucleo.turn.prompt import packs as CP
from nucleo.turn.prompt.packs import introduction


@pytest.fixture(autouse=True)
def _fresh():
    introduction.install()
    introduction._turns = 0
    introduction._judging = False
    introduction._offer_pending = False
    introduction._tasks = []
    yield
    introduction._tasks = []


@pytest.fixture
def world(monkeypatch):
    """A boot BEFORE the language is locked, a memory the agent writes into, and no brief for the turn."""
    store: dict = {}
    state: dict = {}
    monkeypatch.setattr("config.settings.get", lambda k, d=None: store.get(k, d))
    monkeypatch.setattr("config.settings.update", lambda patch: store.update(patch))
    monkeypatch.setattr(introduction, "_known", lambda: dict(state))
    monkeypatch.setattr(introduction, "_RECHECK_S", 0)
    monkeypatch.setattr("nucleo.turn.brief.of_this_turn", lambda: None)
    return store, state


class _Q:
    def __init__(self):
        self.items: asyncio.Queue = asyncio.Queue()

    async def get(self):
        return await self.items.get()


async def _turn(q: _Q, *, reply: str = "Hola, soy Zaelar. ¿Cómo te llamas?") -> None:
    """One `turn.completed` delivered to the watcher, with the window the observer publishes."""
    await q.items.put({"window": [{"role": "assistant", "text": reply}]})
    for _ in range(4):
        await asyncio.sleep(0)


def _watch(q: _Q):
    return asyncio.get_event_loop().create_task(introduction._consume_turns(q))


# ── the watcher is armed before the language, and reads the condition per turn ──────────────────────────

def test_start_subscribes_even_before_the_language_is_locked(world, monkeypatch):
    store, _state = world
    subscribed: list = []
    import bus
    monkeypatch.setattr(bus, "subscribe", lambda topic: subscribed.append(topic) or _Q())

    async def run():
        introduction.start()
        assert subscribed == ["turn.completed"], "boot before the language lock must still arm the watcher"
        assert introduction._tasks, "nothing is watching"
        await introduction.stop()
    asyncio.run(run())


def test_a_session_closes_the_phase_in_three_turns(world, monkeypatch):
    """ES then EN: kickoff (the offer is told) → his name (memory writes it after the turn) → any turn → closed."""
    store, state = world
    for code in ("es", "en"):
        store.clear()
        state.clear()
        introduction._turns = 0
        note = langs.spec(code).kickoff_prompt
        monkeypatch.setattr("nucleo.memory_agent.answer_frame.asked_before", lambda **k: "¿Cómo te llamas?")

        async def run():
            q = _Q()
            task = _watch(q)
            store["stt_language"] = code                          # the ceremony locks it AFTER the boot
            assert "masculina o femenina" in CP.compose(note), "T1: the first prompt carries the offer"
            await _turn(q)                                        # T1 closes: the offer was told
            assert store.get(introduction.OFFER_FLAG) is True
            t2 = CP.compose("pepe")                               # T2: he answers; the state is still empty
            assert "ACABA DE DECÍRTELO" in t2 and "su nombre" not in t2.split("LO QUE TODAVÍA NO SABES")[-1][:60]
            await _turn(q, reply="Encantado, Pepe.")
            state["operator_name"] = "Pepe"                        # the memory agent, ~2 s later
            assert CP.compose("vale") and store.get("intro_done") is not True, "T3 still runs, the name just landed"
            await _turn(q, reply="Dime.")                         # T3 closes → the deterministic exit fires
            assert store.get("intro_done") is True, f"{code}: the phase did not close by the third turn"
            assert CP.compose("qué tal") == "", "the fourth prompt still carries the block"
            task.cancel()
        asyncio.run(run())


def test_closing_needs_BOTH_facts(world):
    store, state = world
    store["stt_language"] = "es"
    state["operator_name"] = "Pepe"
    assert introduction._deterministic_close() == "", "a name alone is not an introduction: the offer is owed"
    store[introduction.OFFER_FLAG] = True
    assert introduction._deterministic_close()
    state.clear()
    assert introduction._deterministic_close() == "", "the offer alone is not an introduction: the name is owed"


def test_the_offer_is_not_told_by_a_turn_that_said_nothing(world):
    store, _state = world
    store["stt_language"] = "es"
    CP.compose(langs.spec("es").kickoff_prompt)
    assert introduction._offer_pending
    introduction._settle_offer({"window": []})
    assert store.get(introduction.OFFER_FLAG) is None, "a mute first turn told him nothing"
    CP.compose(langs.spec("es").kickoff_prompt)
    introduction._settle_offer({"window": [{"role": "assistant", "text": "Hola."}]})
    assert store.get(introduction.OFFER_FLAG) is True


# ── the block reads the turn, not the stale state ────────────────────────────────────────────────────────

def test_an_answer_to_our_question_leaves_the_unknowns_this_turn(world, monkeypatch):
    store, _state = world
    store["stt_language"] = "es"
    monkeypatch.setattr("nucleo.memory_agent.answer_frame.asked_before", lambda **k: "¿Cómo te llamas?")
    b = introduction.block("pepe")
    assert "ACABA DE DECÍRTELO en este mismo turno (su nombre)" in b, b
    unknown = b.split("LO QUE TODAVÍA NO SABES")[-1] if "LO QUE TODAVÍA NO SABES" in b else ""
    assert "su nombre" not in unknown, "the goal he just answered is still listed as unknown"
    assert "sin confirmarlo" in b
    monkeypatch.setattr("nucleo.memory_agent.answer_frame.asked_before", lambda **k: "")
    b = introduction.block("pepe")
    assert "ACABA DE DECÍRTELO" not in b and "su nombre" in b, "without a question of ours, nothing was answered"


def test_a_sure_answer_verdict_also_counts(world, monkeypatch):
    import threading
    store, _state = world
    store["stt_language"] = "es"
    monkeypatch.setattr("nucleo.memory_agent.answer_frame.asked_before", lambda **k: "")
    ev = threading.Event()
    ev.set()
    brief = {"event": ev, "result": {"request_type": {"choice": "answer", "confidence": 0.95, "probs": {}}}}
    monkeypatch.setattr("nucleo.turn.brief.of_this_turn", lambda: brief)
    assert "ACABA DE DECÍRTELO" in introduction.block("me llamo pepe, encantado de conocerte hoy")
    brief["result"]["request_type"]["confidence"] = 0.4
    assert "ACABA DE DECÍRTELO" not in introduction.block("me llamo pepe, encantado de conocerte hoy")
