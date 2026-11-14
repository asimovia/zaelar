"""Stopping and closing by TEXT always work, as they do by voice (audit 2026-11-14, failures 1, 2, 8, 9).

The operator's session that night was typed, on the desktop, build 139:

- **«cierra todo»** was VETOED (failure 2). Six typed lines had adopted the trace of a spoken fragment left in the
  accumulator, so the close was judged with `canvas=neither 0.94`, the brief verdict of an earlier line. Two fixes, one
  class — a turn never answers another turn's verdict: a typed line opens its OWN trace, and the hard close crosses the
  canvas door as `interrupt` (the seeded grammar is its licence) instead of as the model.
- **«para»** typed over a story did not cut the voice (failure 8): a typed line queues behind the speech, and the stop
  lane then handed the stop to `musica:pause` (0.52, nothing playing). A typed hard interrupt now cuts the speech at the
  typed door, as a barge-in does, and a stop that cut our speech is about that speech.
- **«para todo»** over a YouTube video did nothing (failure 1): the lane knew an errand or Spotify. It now pauses every
  app that REPORTS it is playing and declares a `pause` act.
- The close's receipt came 35 s late (failure 9), queued behind the story: the typed close cuts it too.

Typed and spoken, Spanish and English; each mechanism is disarmed and seen red.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from nucleo import done_ops
from nucleo.flash import bulk_close, hard_turn
from nucleo.turn import brief
from voice import attention, proactive, trace


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    attention.reset()
    done_ops.reset()
    bulk_close.reset()
    proactive._cut_at[0] = 0.0
    monkeypatch.setattr(proactive, "_bot_probe", None)
    trace.adopt("")
    from memory import api as memory
    monkeypatch.setattr(memory, "write", lambda *a, **k: None)
    yield
    attention.reset()
    bulk_close.reset()
    proactive._cut_at[0] = 0.0
    trace.adopt("")


def _collect():
    events: list[tuple] = []

    def emit(kind, label, text=None, role=None, extra=None, **_kw):
        events.append((kind, label, text, dict(extra or {})))
    return events, emit


# ── A1 · the hard close answers no brief verdict ───────────────────────────────────────────────────────────────────
CLOSE_ALL = ["cierra todo", "Ciérralo todo.", "close all", "close everything"]


@pytest.fixture
def _stale_verdict(monkeypatch):
    """What the trace held in the session: an earlier line's sure «neither»."""
    from nucleo.acts import canvas_turn
    monkeypatch.setattr(canvas_turn, "request_of", lambda brief=None, text=None, **k: {
        "text": text or "", "turn_credit": True, "last_reply": "", "verdict": {"canvas": ("neither", 0.94)}})
    monkeypatch.setattr(bulk_close, "_open_instances", lambda: ["youtube"])


def _hard_close(said):
    events, emit = _collect()
    assert attention.hard_interrupt(said) == "close"
    assert asyncio.run(hard_turn.handle(said, "close", emit)) is None
    closed = [e for e in events if e[0] == "widget" and e[1] == "close"]
    receipt = [e for e in events if e[1] == "🧾 close receipt"]
    return closed, receipt


@pytest.mark.parametrize("said", CLOSE_ALL)
def test_a_hard_close_is_never_vetoed_by_a_verdict_it_did_not_ask(_stale_verdict, said):
    closed, receipt = _hard_close(said)
    assert closed and closed[0][3].get("src") == "interrupt", f"{said!r}: nothing closed"
    assert receipt and receipt[0][2], f"{said!r}: closed in silence"


def test_disarmed_as_the_model_the_stale_verdict_vetoes_it_again(_stale_verdict):
    """RED proof: take `interrupt` out of the deterministic provenances and the close is judged like the model."""
    from nucleo.acts import canvas_arbiter
    real = canvas_arbiter._SRC_DETERMINISTIC
    canvas_arbiter._SRC_DETERMINISTIC = ("actionmap",)
    try:
        closed, receipt = _hard_close("cierra todo")
        assert not closed and not receipt, "the disarm did not land"
    finally:
        canvas_arbiter._SRC_DETERMINISTIC = real
    bulk_close.reset()
    closed, _ = _hard_close("close all")
    assert closed                                               # green again


# ── A1 · every typed line opens its own trace ──────────────────────────────────────────────────────────────────────
def _brain_with_a_spoken_fragment_pending():
    from nucleo.input import stt as acc_mod
    from nucleo.input.stt import Accumulator
    from voice.engine.llm.providers.nucleo import NucleoLLM, _begin_or_adopt_trace

    async def _incomplete(text):
        return "incomplete", ""
    acc_mod.set_judge(_incomplete)
    brain = NucleoLLM()
    brain._acc = Accumulator()
    _begin_or_adopt_trace(brain, "Pues mira, me vas a", False)
    chain = trace.current()
    asyncio.run(brain._acc.offer("Pues mira, me vas a"))
    assert brain._acc.pending()
    return brain, chain, _begin_or_adopt_trace


def _typed(brain, begin, line):
    attention.note_typed(text=line)
    trace.adopt("")
    begin(brain, line, False)
    return trace.current()


@pytest.mark.parametrize("lines", [["búscame vídeos del apolo 11", "para todo", "cierra todo"],
                                   ["find me videos of apollo 11", "stop everything", "close all"]])
def test_typed_lines_beside_a_pending_spoken_fragment_each_open_their_own_trace(lines):
    from nucleo.input import stt as acc_mod
    try:
        brain, chain, begin = _brain_with_a_spoken_fragment_pending()
        tids = [_typed(brain, begin, line) for line in lines]
        assert len(set(tids)) == len(lines) and chain not in tids, (chain, tids)
        assert brain._acc_trace_id == chain                     # the spoken sentence keeps its own for what may follow
        attention.reset()
        trace.adopt("")
        begin(brain, "borrar la agenda", False)                 # …and its spoken continuation still adopts it
        assert trace.current() == chain
    finally:
        acc_mod.set_judge(None)


def test_disarmed_a_typed_line_read_as_speech_adopts_the_fragments_trace_again(monkeypatch):
    """RED proof: read every line as speech and the typed lines share the fragment's trace, as in the session."""
    from nucleo import input as _input
    from nucleo.input import stt as acc_mod
    monkeypatch.setattr(_input, "of_turn", lambda text, **k: _input.Utterance(text=text, channel=_input.VOICE))
    try:
        brain, chain, begin = _brain_with_a_spoken_fragment_pending()
        assert {_typed(brain, begin, line) for line in ("para todo", "cierra todo")} == {chain}
    finally:
        acc_mod.set_judge(None)


# ── A2 · a typed hard interrupt cuts the speech sounding now ───────────────────────────────────────────────────────
class _Speech:
    def __init__(self):
        self.interrupted = False
        self.allow_interruptions = True

    def done(self):
        return False

    def interrupt(self):
        self.interrupted = True


class _Session:
    """The live AgentSession's slice the typed door uses."""
    def __init__(self, log):
        self.current_speech, self.log = _Speech(), log

    def generate_reply(self, user_input="", **kw):
        self.log.append(("reply", user_input, self.current_speech.interrupted, kw))


class _Remote:
    """The body's RemoteSession: no speech of its own, the voice process cuts it."""
    def __init__(self, log):
        self.log = log

    def generate_reply(self, user_input="", **kw):
        self.log.append(("reply", user_input, kw))


def _type(line, session_cls, *, speaking=True):
    from voice.engine.pipeline import agent_events
    proactive.register_bot_probe(lambda: speaking)
    log: list = []
    session = session_cls(log)
    agent_events.receive_typed(line, _emit=lambda *a, **k: None, session=session)
    return session, log


@pytest.mark.parametrize("line", ["para", "para ya", "stop", "Stop it.", "cierra todo", "close all"])
def test_a_typed_hard_interrupt_cuts_the_speech_before_its_turn_is_queued(monkeypatch, line):
    from nucleo.input import typed as _order
    monkeypatch.setattr(_order, "must_wait", lambda *a, **k: False)
    session, log = _type(line, _Session)
    assert session.current_speech.interrupted, f"{line!r} queued behind the speech"
    assert log == [("reply", line, True, {})]                   # cut first, then his turn — never its own reply
    assert proactive._cut_at[0] > 0
    _, log = _type(line, _Remote)
    assert log == [("reply", line, {"cut_speech": True})]       # the body asks the voice process to cut it


@pytest.mark.parametrize("line,speaking", [("cuéntame más", True), ("tell me more", True), ("para", False),
                                           ("stop", False)])
def test_any_other_line_or_a_silent_agent_cuts_nothing(monkeypatch, line, speaking):
    from nucleo.input import typed as _order
    monkeypatch.setattr(_order, "must_wait", lambda *a, **k: False)
    session, log = _type(line, _Session, speaking=speaking)
    assert not session.current_speech.interrupted and log == [("reply", line, False, {})]
    assert proactive._cut_at[0] == 0.0


def test_disarmed_without_the_door_reading_the_stop_the_typed_stop_queues_again(monkeypatch):
    """RED proof: the typed door no longer reads the grammar → «para» waits behind the story, as in the session."""
    from nucleo.input import typed as _order
    from voice.engine.pipeline import agent_events
    monkeypatch.setattr(_order, "must_wait", lambda *a, **k: False)
    monkeypatch.setattr(agent_events, "_cuts_our_speech", lambda txt: False)
    session, log = _type("para", _Session)
    assert not session.current_speech.interrupted and log == [("reply", "para", False, {})]


def test_the_voice_process_cuts_then_queues_in_one_request(monkeypatch):
    """`/voice/reply` with `cut`: the speech sounding now is interrupted on the session loop, then the reply queued."""
    from voice.engine.pipeline import body_link, child
    log: list = []
    live = _Session(log)
    monkeypatch.setenv(body_link.TOKEN_ENV, "tok")
    monkeypatch.setitem(child.LIVE, "session", live)

    async def _run(cut):
        monkeypatch.setitem(child.LIVE, "loop", asyncio.get_running_loop())

        async def _json():
            return {"text": "para", **({"cut": True} if cut else {})}
        req = SimpleNamespace(headers={body_link.HEADER: "tok"}, json=_json)
        await child.reply(req)
    asyncio.run(_run(True))
    assert live.current_speech.interrupted and log[-1][:3] == ("reply", "para", True)
    live.current_speech = _Speech()
    asyncio.run(_run(False))
    assert not live.current_speech.interrupted


# ── A2 · a stop that cut our speech is about our speech ────────────────────────────────────────────────────────────
@pytest.fixture
def _names_musica_pause(monkeypatch):
    async def _pause(text, key):
        return "musica:pause", {"used": True, "confidence": 0.52}
    monkeypatch.setattr(brief, "verdict_before_the_turn", _pause)
    monkeypatch.setattr(hard_turn, "pause_what_sounds", lambda text, emit: _nothing())


async def _nothing():
    return []


def _stop(said):
    events, emit = _collect()
    return asyncio.run(hard_turn.handle(said, "stop", emit)), events


@pytest.mark.parametrize("said,typed", [("para", True), ("stop", True), ("para", False), ("stop", False)])
def test_a_stop_that_cut_our_speech_ends_there(_names_musica_pause, said, typed):
    """Typed: the typed door noted the cut. Spoken: the barge-in did. Then his turn is born."""
    if typed:
        attention.note_typed(text=said)
    proactive.note_speech_cut()
    trace.begin(said, origin="turno")
    rest, events = _stop(said)
    assert rest is None, f"{said!r} handed to the brief's app act over our speech"
    assert not any("nombra una acción" in e[1] for e in events)


def test_with_nothing_spoken_over_the_stop_the_brief_still_names_the_act(_names_musica_pause):
    """CRIT-W10 / V2-834 T25 stay: «stop it» with nothing of ours sounding goes on to the card act."""
    trace.begin("stop it", origin="turno")
    rest, _ = _stop("stop it")
    assert rest == "stop it"


def test_the_cut_belongs_to_the_first_turn_after_it_only(_names_musica_pause):
    """A barge-in that became another turn does not make a later stop «about our speech»."""
    proactive.note_speech_cut()
    trace.begin("vale, sigue", origin="turno")
    trace.begin("para", origin="turno")
    assert not proactive.turn_cut_our_speech()
    assert _stop("para")[0] == "para"


def test_a_spoken_barge_in_notes_the_cut():
    from voice.engine.pipeline import agent_events
    busy = {"bot": True, "user": False}
    ev = SimpleNamespace(new_state="speaking")
    agent_events._on_user_state(ev, _busy=busy, _emit=lambda *a, **k: None, _onset={},
                                sm=SimpleNamespace(on_user_state=lambda s: None))
    trace.begin("para", origin="turno")
    assert proactive.turn_cut_our_speech()


def test_disarmed_without_the_cut_the_stop_goes_to_the_app_act_again(_names_musica_pause, monkeypatch):
    """RED proof: the stop lane no longer asks whether it cut our speech → `musica:pause` 0.52 takes it, as in failure 8."""
    monkeypatch.setattr(hard_turn, "_over_our_speech", lambda: False)
    proactive.note_speech_cut()
    trace.begin("para", origin="turno")
    assert _stop("para")[0] == "para"


# ── A3 · a stop pauses whatever is SOUNDING ────────────────────────────────────────────────────────────────────────
OWN_PLAYER = {"id": "mi_radio", "actions": {"pause": {}},
              "state": {"report": {"playing": {"type": "bool"}}}}


@pytest.fixture
def _sounding(monkeypatch):
    """YouTube and a user's own player report `playing`; the music widget is at rest; the map declares no pause."""
    from widgets import runtime, server_api, state_render
    real = runtime.catalog()
    monkeypatch.setattr(runtime, "catalog", lambda: [*real, OWN_PLAYER])
    playing = {"youtube": True, "mi_radio": True, "musica": False}
    monkeypatch.setattr(state_render, "read", lambda app, *a, **k: {"declared": True, "surfaces": [
        {"instance": app, "dev": "desktop", "fields": {"playing": playing[app]}}] if app in playing else []})
    paused: list = []

    async def _action(wid, action, payload):
        paused.append((wid, action))
        return {"ok": True}
    monkeypatch.setattr(server_api, "brain_action", _action)

    async def _none(text, key):
        return "none", {"used": True, "confidence": 0.63}
    monkeypatch.setattr(brief, "verdict_before_the_turn", _none)
    return paused


@pytest.mark.parametrize("said", ["para todo", "para", "stop everything", "stop"])
def test_a_stop_pauses_every_app_that_reports_it_is_playing(_sounding, said):
    assert attention.hard_interrupt(said) == "stop"
    rest, events = _stop(said)
    assert rest is None
    assert sorted(_sounding) == [("mi_radio", "pause"), ("youtube", "pause")]
    assert any(e[1] == "⏸ stop: paused what was sounding" for e in events)


def test_a_stop_about_an_errand_pauses_nothing(_sounding, monkeypatch):
    monkeypatch.setattr(hard_turn, "is_worker_stop", lambda text, hard: True)
    assert _stop("para eso")[0] == "para eso" and _sounding == []


def test_disarmed_without_the_pause_the_video_plays_on(_sounding, monkeypatch):
    """RED proof: the lane no longer pauses what sounds → «para todo» leaves the video playing, as in failure 1."""
    monkeypatch.setattr(hard_turn, "pause_what_sounds", lambda text, emit: _nothing())
    _stop("para todo")
    assert _sounding == []
