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
    monkeypatch.setattr(proactive, "_bot_probe", None)
    trace.adopt("")
    from memory import api as memory
    monkeypatch.setattr(memory, "write", lambda *a, **k: None)
    yield
    attention.reset()
    bulk_close.reset()
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


# ── A2 · a typed line barges in like a spoken one (CRIT-V21) ───────────────────────────────────────────────────────
class _Speech:
    def __init__(self, *, done=False, interruptible=True, boom=False):
        self.interrupted, self.allow_interruptions, self._done, self._boom = False, interruptible, done, boom

    def done(self):
        return self._done

    def interrupt(self):
        if self._boom:
            raise RuntimeError("speech handle gone")
        self.interrupted = True


class _Session:
    """The live AgentSession's slice the typed door uses."""
    def __init__(self, log, speech=None):
        self.current_speech, self.log = speech if speech is not None else _Speech(), log

    def generate_reply(self, user_input="", **kw):
        self.log.append(("reply", user_input, bool(self.current_speech and self.current_speech.interrupted), kw))


class _Remote:
    """The body's RemoteSession: no speech of its own, the voice process cuts it."""
    CUTS_IN_VOICE_PROCESS = True

    def __init__(self, log):
        self.log = log

    def generate_reply(self, user_input="", **kw):
        self.log.append(("reply", user_input, kw))


@pytest.fixture
def _not_held(monkeypatch):
    from nucleo.input import typed as _order
    monkeypatch.setattr(_order, "must_wait", lambda *a, **k: False)


def _type(line, session):
    from voice.engine.pipeline import agent_events
    events = []
    agent_events.receive_typed(line, _emit=lambda *a, **k: events.append(a[:2]), session=session)
    return events


LINES = ["para", "stop", "cierra todo", "close all", "para el cuento", "stop the story", "cuéntame otro",
         "tell me another one"]


@pytest.mark.parametrize("line", LINES)
def test_any_typed_line_cuts_the_speech_in_course_then_runs(_not_held, line):
    """Whatever the line (a stop, a close, an order), whatever the speech's state (generating, paused, sounding)."""
    log: list = []
    _type(line, _Session(log))
    assert log == [("reply", line, True, {})], f"{line!r} queued behind our speech"
    log = []
    _type(line, _Remote(log))
    assert log == [("reply", line, {"cut_speech": True})]       # remote: always, the voice process cuts what is there


@pytest.mark.parametrize("speech", [None, _Speech(done=True), _Speech(interruptible=False)])
def test_nothing_in_course_or_an_uninterruptible_speech_is_not_cut(_not_held, speech):
    log: list = []
    session = _Session(log, speech)
    session.current_speech = speech
    _type("para", session)
    assert log and log[-1][1] == "para" and not (speech and speech.interrupted)


def test_a_line_held_behind_his_own_spoken_sentence_cuts_nothing(_not_held):
    """CRIT-V20's order: the line waited for HIS sentence begun before it; it queues behind it, it does not barge in."""
    from voice.engine.pipeline import agent_events
    log: list = []
    asyncio.run(agent_events._typed_after_voice("y pon música", 0.0, _emit=lambda *a, **k: None, session=_Session(log)))
    assert log == [("reply", "y pon música", False, {})]


def test_a_cut_that_fails_never_drops_the_line(_not_held):
    log: list = []
    events = _type("para", _Session(log, _Speech(boom=True)))
    assert log and log[-1][1] == "para" and ("alert", "typed line: the speech in course was not cut") in events


def test_disarmed_without_the_cut_the_typed_stop_queues_behind_the_story(_not_held, monkeypatch):
    """RED proof: the door no longer cuts → «para» waits behind the story, as in failure 8."""
    from voice.engine.pipeline import agent_events
    monkeypatch.setattr(agent_events, "cut_current_speech", lambda session: False)
    log: list = []
    _type("para", _Session(log))
    assert log == [("reply", "para", False, {})]


@pytest.mark.parametrize("speech", [_Speech(), _Speech(boom=True)])
def test_the_voice_process_cuts_then_queues_in_one_request(monkeypatch, speech):
    """`/voice/reply` with `cut`: the speech in course is interrupted on the session loop, then the reply queued — even
    when the cut itself fails."""
    from voice.engine.pipeline import body_link, child
    log: list = []
    live = _Session(log, speech)
    monkeypatch.setenv(body_link.TOKEN_ENV, "tok")
    monkeypatch.setitem(child.LIVE, "session", live)

    async def _run():
        monkeypatch.setitem(child.LIVE, "loop", asyncio.get_running_loop())

        async def _json():
            return {"text": "para", "cut": True}
        await child.reply(SimpleNamespace(headers={body_link.HEADER: "tok"}, json=_json))
    asyncio.run(_run())
    assert log and log[-1][1] == "para" and live.current_speech.interrupted is not speech._boom


# ── A stop with an app act: the act wins, unless the lane served it or nothing runs (P1, failure 8) ─────────────────
def _verdict(monkeypatch, choice, conf=0.9):
    async def _v(text, key):
        return choice, {"used": True, "confidence": conf}
    monkeypatch.setattr(brief, "verdict_before_the_turn", _v)


def _state(monkeypatch, playing):
    """musica's declared `playing` as reported now: True, False, or None (the field not known)."""
    from widgets import server_api, state_render
    fields = {} if playing is None else {"playing": playing}
    monkeypatch.setattr(state_render, "read", lambda app, *a, **k: {"declared": True, "surfaces": [
        {"instance": app, "dev": "desktop", "fields": dict(fields)}] if app == "musica" else []})
    done: list = []

    async def _action(wid, action, payload):
        done.append((wid, action))
        return {"ok": True}
    monkeypatch.setattr(server_api, "brain_action", _action)
    return done


async def _nothing():
    return []


def _stop(said):
    events, emit = _collect()
    return asyncio.run(hard_turn.handle(said, "stop", emit)), events


@pytest.mark.parametrize("typed", [True, False])
@pytest.mark.parametrize("said,choice", [("Stop showing me the Social tab", "mensajeria:mail_sort"),
                                         ("stop it", "activity:stop"),
                                         ("para eso, ábreme la agenda", "agenda:open")])
def test_a_stop_that_names_another_act_goes_on_whole(monkeypatch, said, choice, typed):
    """CRIT-W10 / V2-834 T25: said over our speech or not, typed or spoken — the act he names wins."""
    _state(monkeypatch, False)
    _verdict(monkeypatch, choice)
    if typed:
        attention.note_typed(text=said)
    rest, events = _stop(said)
    assert rest == said and any("nombra una acción" in e[1] for e in events)


@pytest.mark.parametrize("typed", [True, False])
@pytest.mark.parametrize("said", ["para", "stop"])
def test_the_pause_of_an_app_where_nothing_plays_is_empty_and_the_stop_ends(monkeypatch, said, typed):
    """Failure 8: «para» → `musica:pause` 0.52 with the music NOT playing went to the model («Parado.»)."""
    _state(monkeypatch, False)
    _verdict(monkeypatch, "musica:pause", 0.52)
    if typed:
        attention.note_typed(text=said)
    rest, events = _stop(said)
    assert rest is None and any("already served" in e[1] for e in events)


def test_the_pause_the_lane_just_did_is_served_and_the_stop_ends(monkeypatch):
    done = _state(monkeypatch, True)
    _verdict(monkeypatch, "musica:pause")
    assert _stop("stop")[0] is None and done == [("musica", "pause")]


def test_disarmed_without_the_declared_state_the_empty_pause_goes_to_the_model_again(monkeypatch):
    """RED proof: the filter reads no declared state → failure 8 again."""
    _state(monkeypatch, False)
    _verdict(monkeypatch, "musica:pause", 0.52)
    monkeypatch.setattr(hard_turn, "_states", lambda: [])
    assert _stop("para")[0] == "para"


def test_a_playing_not_yet_known_is_paused_too(monkeypatch):
    """P2-2: «ponme un vídeo» then «para» 2 s later — the order is not acked yet; the pause is idempotent."""
    done = _state(monkeypatch, None)
    _verdict(monkeypatch, "none")
    _stop("para")
    assert done == [("musica", "pause")]


def test_a_refusal_is_not_a_stop(monkeypatch):
    from widgets import server_api
    _state(monkeypatch, True)

    async def _refuse(wid, action, payload):
        return {"ok": False, "message": "nothing_playing"}
    monkeypatch.setattr(server_api, "brain_action", _refuse)
    events, emit = _collect()
    assert asyncio.run(hard_turn.stop_what_runs("para", emit)) == []


@pytest.mark.parametrize("said,paused", [("para todo", True), ("stop everything", True), ("para eso", False)])
def test_a_total_stop_beside_an_errand_also_ends_what_runs(monkeypatch, said, paused):
    """P2-1: a live errand + a video + «para todo» → the errand's turn goes on AND the video stops; «para eso» is the
    errand's alone."""
    done = _state(monkeypatch, True)
    monkeypatch.setattr(hard_turn, "is_worker_stop", lambda text, hard: True)
    assert _stop(said)[0] == said
    assert (done == [("musica", "pause")]) is paused


# ── A3 · a stop pauses whatever is SOUNDING ────────────────────────────────────────────────────────────────────────
OWN_PLAYER = {"id": "mi_radio", "actions": {"pause": {}},
              "state": {"report": {"playing": {"type": "bool", "stop": {"act": "pause", "when": True}}}}}


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
    assert any(e[1] == "⏸ stop: stopped what was running" for e in events)


def test_disarmed_without_the_pause_the_video_plays_on(_sounding, monkeypatch):
    """RED proof: the lane no longer pauses what sounds → «para todo» leaves the video playing, as in failure 1."""
    monkeypatch.setattr(hard_turn, "stop_what_runs", lambda text, emit: _nothing())
    _stop("para todo")
    assert _sounding == []


# ── every app that DECLARES a running state is stopped — parametrized over the catalogue, so a new one is covered ───
def _declared_stops():
    from widgets import runtime, state_decl
    return [(m["id"], f, st) for m in runtime.catalog()
            for f, spec in state_decl.report_fields(m.get("state") or {}).items() if (st := state_decl.stop_of(spec))]


def test_the_players_declare_what_a_stop_ends():
    assert {a for a, _f, _s in _declared_stops()} >= {"youtube", "musica"}


@pytest.mark.parametrize("app,field,stop", _declared_stops(), ids=lambda v: v if isinstance(v, str) else "")
def test_a_stop_ends_every_app_running_its_declared_state(monkeypatch, app, field, stop):
    from widgets import server_api, state_render
    act, when = stop
    monkeypatch.setattr(state_render, "read", lambda a, *x, **k: {"declared": True, "surfaces": [
        {"instance": a, "dev": "desktop", "fields": {field: when}}] if a == app else []})
    done: list = []

    async def _action(wid, action, payload):
        done.append((wid, action))
        return {"ok": True}
    monkeypatch.setattr(server_api, "brain_action", _action)
    events, emit = _collect()
    assert asyncio.run(hard_turn.stop_what_runs("para todo", emit)) == [app]
    assert done == [(app, act)]


@pytest.mark.parametrize("stop", [{"act": "no_such_act", "when": True}, {"act": "pause", "when": "yes"}, {"when": True}])
def test_a_stop_that_names_no_act_of_the_app_or_a_value_of_another_type_is_refused(stop):
    from widgets import state_decl
    man = {"id": "x", "actions": {"pause": {}},
           "state": {"order": {"p": "p"}, "report": {"playing": {"type": "bool", "follows": "p", "stop": stop}}}}
    assert "stop is" in (state_decl.problem(man) or "")
    man["state"]["report"]["playing"]["stop"] = {"act": "pause", "when": True}
    assert state_decl.problem(man) is None


# ── a turn never reads another turn's verdict — over EVERY store that keeps one by trace ───────────────────────────
def _stores():
    from nucleo.acts import canvas_turn
    from nucleo.flash import capability_gap
    from nucleo.turn import brief_turn
    return {
        "canvas_turn": (lambda t: canvas_turn._reads.setdefault(t, {}).update(canvas=("neither", 0.94)),
                        lambda t: canvas_turn._reads.get(t)),
        "brief_turn": (lambda t: brief_turn._BY_TRACE.__setitem__(t, {"judged": "earlier line"}),
                       lambda t: brief_turn._BY_TRACE.get(t)),
        "capability_gap": (lambda t: capability_gap.remember({"judged": "earlier line"}, t),
                           lambda t: capability_gap.brief_of(t)),
    }


def test_every_by_trace_verdict_store_is_turn_scoped():
    stores = _stores()
    assert len(trace.TURN_SCOPED) >= len(stores)


@pytest.mark.parametrize("store", ["canvas_turn", "brief_turn", "capability_gap"])
def test_a_new_turn_on_a_used_trace_starts_with_none_of_its_verdicts(store):
    write, read = _stores()[store]
    tid = trace.begin("búscame vídeos del apolo 11", origin="turno")
    write(tid)
    assert read(tid)
    trace.new_turn_on(tid)                                  # «cierra todo» adopts that trace
    assert not read(tid), f"{store} kept an earlier turn's verdict"


def test_the_turn_admission_starts_its_trace_fresh_and_a_prefired_brief_joins_it(monkeypatch):
    from nucleo.flash import capability_gap
    from nucleo.turn import brief, brief_turn
    tid = trace.begin("cierra todo", origin="turno")
    _stores()["canvas_turn"][0](tid)
    pre = {"judged": "cierra todo"}
    monkeypatch.setattr(brief_turn, "prefired", lambda text: pre)
    trace.new_turn_on(tid)
    got = brief.ask_for_turn("cierra todo", turn_id="t-2")
    assert got is pre and pre["turn_id"] == "t-2"
    assert brief_turn.of_this_turn() is pre and capability_gap.brief_of(tid) is pre
    assert not _stores()["canvas_turn"][1](tid)


def test_disarmed_without_the_registry_a_stale_verdict_survives_the_new_turn(monkeypatch):
    """RED proof: no store registered → the earlier line's `canvas=neither 0.94` is still there for the new turn."""
    monkeypatch.setattr(trace, "TURN_SCOPED", [])
    write, read = _stores()["canvas_turn"]
    tid = trace.begin("x", origin="turno")
    write(tid)
    trace.new_turn_on(tid)
    assert read(tid)


class _Asked(Exception):
    pass


def test_the_admission_door_starts_its_trace_fresh_before_the_brief(monkeypatch):
    """The wiring: `admit_the_turn` forgets the trace's verdicts BEFORE it fires (or reuses) the turn's brief."""
    from nucleo.input import stt
    from nucleo.turn import brief, pipeline_admit
    monkeypatch.setattr(stt, "whole_turn", lambda brain, text: text)
    tid = trace.begin("búscame vídeos del apolo 11", origin="turno")
    write, read = _stores()["canvas_turn"]
    write(tid)
    seen = {}

    def _ask(text, **k):
        seen["stale"] = read(tid)
        raise _Asked
    monkeypatch.setattr(brief, "ask_for_turn", _ask)
    motor = SimpleNamespace(_show_target=SimpleNamespace(_running_goals=lambda: []))
    with pytest.raises(_Asked):
        asyncio.run(pipeline_admit.admit_the_turn(motor=motor, attention=attention, emit=lambda *a, **k: None,
                                                  brain=SimpleNamespace(_last_reply="", _acc_gen=0),
                                                  first_turn=False, text="cierra todo"))
    assert not seen["stale"]
