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

import pytest

from i18n import langs
from nucleo.turn.prompt import packs as CP
from nucleo.turn.prompt.packs import introduction


@pytest.fixture(autouse=True)
def _fresh():
    introduction.install()
    introduction._turns = 0
    introduction._judging = False
    introduction._offer_pending = ""
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
    monkeypatch.setattr("nucleo.turn.prompt.packs.introduction_block._this_turn", lambda: "T")
    return store, state


class _Q:
    def __init__(self):
        self.items: asyncio.Queue = asyncio.Queue()

    async def get(self):
        return await self.items.get()


async def _turn(q: _Q, *, reply: str = "Hola, soy Zaelar. ¿Cómo te llamas?") -> None:
    """One `turn.completed` delivered to the watcher, with the window the observer publishes."""
    await q.items.put({"window": [{"role": "assistant", "text": reply}], "trace": "T"})
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
            assert "SI LO QUE ACABA DE DECIR CONTESTA" in t2
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
    introduction._settle_offer({"window": [], "trace": "T"})
    assert store.get(introduction.OFFER_FLAG) is None, "a mute first turn told him nothing"
    CP.compose(langs.spec("es").kickoff_prompt)
    introduction._settle_offer({"window": [{"role": "assistant", "text": "Hola, soy Zaelar."}], "trace": "T"})
    assert store.get(introduction.OFFER_FLAG) is True


def test_a_reply_without_our_name_still_tells_the_offer_and_a_rename_makes_it_moot(world, monkeypatch):
    """A7 audit P1: requiring our own name in the reply kept the offer riding every turn after «Encantado, Pepe. Puedes
    cambiarme el nombre y la voz» — the deterministic close never fired. The traced turn that replied tells it; and
    once he renamed us (the name slot set) it is moot."""
    store, _state = world
    store["stt_language"] = "es"
    CP.compose("pepe")
    introduction._settle_offer({"window": [{"role": "assistant", "text": "Encantado, Pepe. Puedes cambiarme el "
                                                                         "nombre y la voz."}], "trace": "T"})
    assert store.get(introduction.OFFER_FLAG) is True
    store.pop(introduction.OFFER_FLAG)
    from voice import attention
    monkeypatch.setitem(attention._state, "assistant_name", "Lola")
    assert introduction.offer_told() and "masculina o femenina" not in CP.compose("hola"), "renamed, offered again"


def test_the_offer_settles_by_the_real_trace_of_its_turn(world, monkeypatch):
    """A7 audit (d): `voice.trace` itself, not a mocked `_this_turn` — the compose inside a turn's scope binds it."""
    from voice import trace
    store, _state = world
    store["stt_language"] = "es"
    monkeypatch.undo()       # back to the real `_this_turn`; the world's stores are set again below
    monkeypatch.setattr("config.settings.get", lambda k, d=None: store.get(k, d))
    monkeypatch.setattr("config.settings.update", lambda patch: store.update(patch))
    monkeypatch.setattr(introduction, "_known", lambda: {})
    monkeypatch.setattr("nucleo.turn.brief.of_this_turn", lambda: None)
    import bus
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda *a, **k: None)
    monkeypatch.setattr(bus, "emit_sync", lambda topic, payload: introduction._settle_offer(payload))

    def close(tid):      # the turn's close as it publishes: `observer.turn_detail` → `turn.completed` on the bus
        with trace.scope(tid):
            observer.turn_detail(system="s", window=[{"role": "assistant", "content": "Hola."}], user="hola")
    with trace.scope(""):
        CP.compose(langs.spec("es").kickoff_prompt)       # a prompt warmed outside any turn
    close("T78·other")
    assert store.get(introduction.OFFER_FLAG) is None, "a compose outside any turn was settled by another turn's close"
    with trace.scope("T77·real"):
        CP.compose(langs.spec("es").kickoff_prompt)
    close("T78·other")
    assert store.get(introduction.OFFER_FLAG) is None, "another turn's close settled this turn's offer"
    with trace.scope("T77·real"):
        CP.compose(langs.spec("es").kickoff_prompt)
    close("T77·real")
    assert store.get(introduction.OFFER_FLAG) is True


def test_the_offer_is_told_only_by_the_turn_whose_prompt_carried_it(world, monkeypatch):
    """A7 P2: a block composed outside a turn (a prompt warmed ahead) or another turn's close settles nothing."""
    store, _state = world
    store["stt_language"] = "es"
    monkeypatch.setattr("nucleo.turn.prompt.packs.introduction_block._this_turn", lambda: "")
    CP.compose(langs.spec("es").kickoff_prompt)
    introduction._settle_offer({"window": [{"role": "assistant", "text": "Hola, soy Zaelar."}], "trace": ""})
    assert store.get(introduction.OFFER_FLAG) is None, "a compose outside any turn told him the offer"
    monkeypatch.setattr("nucleo.turn.prompt.packs.introduction_block._this_turn", lambda: "T1")
    CP.compose(langs.spec("es").kickoff_prompt)
    introduction._settle_offer({"window": [{"role": "assistant", "text": "Hola, soy Zaelar."}], "trace": "T0"})
    assert store.get(introduction.OFFER_FLAG) is None, "another turn's close settled this turn's offer"
    introduction._settle_offer({"window": [{"role": "assistant", "text": "Hola, soy Zaelar."}], "trace": "T1"})
    assert store.get(introduction.OFFER_FLAG) is True


# ── the block reads the turn, not the stale state ────────────────────────────────────────────────────────

def test_an_answer_to_our_question_leaves_the_unknowns_this_turn(world, monkeypatch):
    store, _state = world
    store["stt_language"] = "es"
    monkeypatch.setattr("nucleo.memory_agent.answer_frame.asked_before", lambda **k: "¿Cómo te llamas?")
    b = introduction.block("pepe")
    assert "SI LO QUE ACABA DE DECIR CONTESTA" in b and "sin confirmarlo" in b and "¿Cómo te llamas?" not in b, "the close already quotes it"
    monkeypatch.setattr("nucleo.memory_agent.answer_frame.asked_before", lambda **k: "")
    b = introduction.block("pepe")
    assert "SI LO QUE ACABA DE DECIR CONTESTA" not in b and "su nombre" in b, "without a question of ours, nothing was answered"


def test_an_answer_to_another_question_of_ours_is_never_read_as_his_name(world, monkeypatch):
    """I1: «sí, claro» to «¿quieres que te cuente qué puedo hacer?» was told to the model as «he just told you (his
    name)» — the block guessed WHICH goal from the order. Now it names the question asked; the fact stays unknown."""
    store, _state = world
    for code, asked, said in (("es", "¿Quieres que te cuente qué puedo hacer por ti?", "sí, claro"),
                              ("es", "¿De dónde eres?", "Madrid"),
                              ("en", "Do you want me to tell you what I can do?", "yes, sure"),
                              ("en", "Where are you based?", "Madrid")):
        store["stt_language"] = code
        monkeypatch.setattr("nucleo.memory_agent.answer_frame.asked_before", lambda **k: asked)
        b = introduction.block(said)
        assert "SI LO QUE ACABA DE DECIR CONTESTA" in b and "(su nombre)" not in b and "ACABA DE DECÍRTELO" not in b, (code, said, b)
        unknown = b.split("LO QUE TODAVÍA NO SABES")[-1][:60]
        assert "su nombre" in unknown, (code, said, "his name was dropped from the unknowns")


def test_a_sure_answer_verdict_also_counts(world, monkeypatch):
    import threading
    store, _state = world
    store["stt_language"] = "es"
    monkeypatch.setattr("nucleo.memory_agent.answer_frame.asked_before", lambda **k: "")
    ev = threading.Event()
    ev.set()
    brief = {"event": ev, "result": {"request_type": {"choice": "answer", "confidence": 0.95, "probs": {}}}}
    monkeypatch.setattr("nucleo.turn.brief.of_this_turn", lambda: brief)
    long = "me llamo pepe, encantado de conocerte hoy"         # over the bare-answer length: only the verdict reads it
    # A7 audit (a): our reply did not END on the question (the kickoff asks, then tells the offer) — the verdict alone
    assert "SI LO QUE ACABA DE DECIR CONTESTA" in introduction.block(long)
    brief["result"]["request_type"]["confidence"] = 0.4
    assert "SI LO QUE ACABA DE DECIR CONTESTA" not in introduction.block(long)


def test_the_builders_question_is_read_once_and_passed(world, monkeypatch):
    """A7 audit (e): `asked_before` (a SQLite read) ran up to 3 times per composition. The builder reads it and hands
    it to the pack; a caller without it makes the pack read it once."""
    store, _state = world
    store["stt_language"] = "es"
    reads = []
    monkeypatch.setattr("nucleo.memory_agent.answer_frame.asked_before",
                        lambda **k: reads.append(1) or "¿Cómo te llamas?")
    assert "SI LO QUE ACABA DE DECIR CONTESTA" in CP.compose("pepe", "¿Cómo te llamas?") and reads == []
    CP.compose("pepe")
    assert len(reads) == 1


def test_the_recheck_never_asks_the_judge_again(world, monkeypatch):
    """A7 P2: the turn's close asks the judge on its turn; the recheck 4 s later read the same turn count and asked
    it again. Now the recheck is the deterministic read only."""
    store, state = world
    store["stt_language"] = "es"
    introduction._turns = introduction._JUDGE_AFTER
    asked = []
    monkeypatch.setattr(introduction, "_judge_sync", lambda t: asked.append(t) or False)
    monkeypatch.setattr(introduction, "_recent", lambda limit=14: "PERSON: hola")
    asyncio.run(introduction._maybe_close())
    asyncio.run(introduction._recheck())
    assert len(asked) == 1, "the judge ran twice for one turn"
    state["operator_name"], store[introduction.OFFER_FLAG] = "Pepe", True
    asyncio.run(introduction._recheck())
    assert store.get("intro_done") is True


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


def test_the_wake_word_line_forbids_asking_his_name_only_when_it_is_known():
    """I1 (row 5, observed c): the line said «never ask the operator's name: it is in your STATE» before it was."""
    from nucleo.flash import style_directive
    unknown = style_directive.prompt_lines({"assistant_name": "Zaelar"})[0]
    assert "cómo se llama el operador" not in unknown and "Zaelar" in unknown
    known = style_directive.prompt_lines({"assistant_name": "Zaelar", "operator_name": "Pepe"})[0]
    assert "ni cómo se llama el operador: ambos están en tu ESTADO" in known
