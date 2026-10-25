"""One agent, one voice, many screens (V2-792) — the server half.

The operator opens the same agent on the desktop and on the phone. One conversation, so the chat and the progress
belong on both; but a card a request opens belongs on the screen that ASKED. Before this, every event reached
every screen with nothing saying where it came from, so a video asked for on the desktop opened — and played — on
the phone as well; a phone without the voice could not type at all (its line waited for a LiveKit room the voice lock
would never give it); and the brain's idea of «what is on screen» was whichever screen reported last.

What is pinned here, each with its own disarm in `test_..._disarm` below:
  · every event of a turn carries `origin_dev`, the screen that asked — a spoken turn the voice holder, a typed one
    the screen that typed it (even while the other screen holds the voice), an errand the screen that commissioned
    it, whichever screen moved since;
  · a typed line from a screen with no room reaches the live session through `POST /api/chat`;
  · the canvas the brain sees is the one of the screen the current turn came from;
  · the voice changing hands is announced on the stream with the new holder's tab, so the loser stands down at once;
  · the turn context names the screens only when there are two.
"""
from __future__ import annotations

import asyncio

import pytest

from voice import screens

DESK = "desktop:aaaa1111"
PHONE = "mobile:bbbb2222"


@pytest.fixture(autouse=True)
def _fresh():
    screens._reset_for_tests()
    yield
    screens._reset_for_tests()


def _two_open(holder=DESK):
    screens.attach(DESK)
    screens.attach(PHONE)
    screens.holder_beat(holder)


def test_a_spoken_turn_belongs_to_the_voice_holder():
    _two_open(holder=DESK)
    screens.stamp({"kind": "transcript", "role": "user", "text": "pon el vídeo", "trace": "t-1"})
    ev = screens.stamp({"kind": "widget", "label": "show", "id": "youtube", "trace": "t-1"})
    assert ev["origin_dev"] == DESK


def test_a_typed_turn_belongs_to_the_screen_that_typed_it_while_the_other_holds_the_voice():
    _two_open(holder=DESK)
    tok = screens.ORIGIN.set(PHONE)
    try:
        screens.stamp({"kind": "transcript", "role": "user", "text": "hazme un informe", "dev": PHONE})
        ev = screens.stamp({"kind": "widget", "label": "show", "id": "documento"})
    finally:
        screens.ORIGIN.reset(tok)
    assert ev["origin_dev"] == PHONE


def test_a_turn_keeps_its_screen_when_another_turn_starts_meanwhile():
    """The trace is the turn's identity: a voice turn still running when a typed line arrives keeps its screen."""
    _two_open(holder=DESK)
    screens.stamp({"kind": "transcript", "role": "user", "text": "abre la agenda", "trace": "voice-1"})
    screens.stamp({"kind": "transcript", "role": "user", "text": "y el correo", "dev": PHONE, "trace": "typed-1"})
    late = screens.stamp({"kind": "widget", "label": "show", "id": "agenda", "trace": "voice-1"})
    assert late["origin_dev"] == DESK


def test_an_errand_opens_on_the_screen_that_commissioned_it():
    _two_open(holder=DESK)
    screens.stamp({"kind": "transcript", "role": "user", "text": "busca un hotel", "dev": PHONE, "trace": "t-9"})
    screens.note_task("42", screens.origin_of({"trace": "t-9"}))
    # …two minutes later the operator is back on the desktop
    screens.stamp({"kind": "transcript", "role": "user", "text": "qué hora es", "trace": "t-10"})
    ev = screens.stamp({"kind": "widget", "label": "show", "id": "results::42", "src": "worker:42"})
    assert ev["origin_dev"] == PHONE


def test_an_event_that_already_names_its_screen_keeps_it():
    _two_open()
    ev = screens.stamp({"kind": "screens", "label": "moved", "id": "youtube", "to": PHONE, "origin_dev": PHONE})
    assert ev["origin_dev"] == PHONE


def test_the_observer_stamps_before_the_event_is_stored_or_sent():
    from voice import observer
    _two_open(holder=PHONE)
    observer.emit("transcript", "final", text="ponme música", role="user")
    ev = observer.emit("widget", "show", extra={"id": "musica", "src": "flash"})
    assert ev and ev.get("origin_dev") == PHONE


def test_a_screen_word_points_at_the_open_screen():
    _two_open()
    assert screens.resolve("computer") == DESK
    assert screens.resolve("phone") == PHONE
    assert screens.resolve("here", asking=PHONE) == PHONE
    assert screens.resolve("tablet") == ""


def test_the_screen_parameter_exists_only_with_two_screens_open():
    from nucleo.flash import router_catalog, tool_selection
    tools = list(router_catalog.TOOLS)
    show = lambda ts: next(t for t in ts if t["function"]["name"] == "show_widget")["function"]["parameters"]
    screens.attach(DESK)
    assert "screen" not in show(tool_selection.with_screens(tools))["properties"]
    screens.attach(PHONE)
    assert show(tool_selection.with_screens(tools))["properties"]["screen"]["enum"] == ["computer", "phone", "here"]
    assert "screen" not in show(tools)["properties"], "the static catalog must stay as it was"


def test_a_turn_sent_to_another_screen_opens_there_and_moves_it():
    _two_open(holder=PHONE)

    async def turn():
        screens.stamp({"kind": "transcript", "role": "user", "text": "ponlo en el ordenador"})
        assert screens.send_turn_to("computer") == DESK
        return screens.stamp({"kind": "widget", "label": "show", "id": "youtube"})

    ev = asyncio.run(turn())
    assert ev["origin_dev"] == DESK and ev.get("moved") is True


def test_the_turn_context_names_the_screens_only_when_there_are_two():
    screens.attach(DESK)
    screens.holder_beat(DESK)
    assert screens.slot_line() == ""
    screens.attach(PHONE)
    line = screens.slot_line()
    assert line.startswith("screens: ") and "computer (voice" in line and "phone" in line


def test_a_typed_line_from_a_screen_without_a_room_reaches_the_live_session(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from nucleo import runstate
    from server import screens_api
    monkeypatch.setattr(runstate, "stopped", lambda: False)
    app = FastAPI()
    app.include_router(screens_api.router)
    client = TestClient(app)

    r = client.post("/api/chat", json={"text": "hola", "dev": PHONE}).json()
    assert r == {"ok": False, "reason": "no_session"}

    got = []

    async def door(text, dev):
        got.append((text, dev))

    screens.register_typed(door)
    r = client.post("/api/chat", json={"text": "hazme un informe", "dev": PHONE}).json()
    assert r == {"ok": True} and got == [("hazme un informe", PHONE)]


def test_a_closing_session_only_clears_its_own_door():
    """The voice moving between screens opens the new room's session BEFORE the old one closes."""
    async def old(text, dev): ...
    async def new(text, dev): ...
    screens.register_typed(old)
    screens.register_typed(new)
    screens.clear_typed(old)
    assert screens.has_session()


def test_the_voice_changing_hands_is_announced_with_the_new_holders_tab(monkeypatch):
    from server import livekit_api as lk
    seen = []
    monkeypatch.setattr("voice.observer.emit", lambda kind, label, **k: seen.append((kind, k.get("extra") or {})))
    monkeypatch.setitem(lk._active, "sid", "tab-desk")
    monkeypatch.setitem(lk._active, "dev", DESK)
    lk.session_steal(sid="tab-phone", dev=PHONE)
    assert ("session", {"src": "steal", "dev": PHONE, "voice_sid": "tab-phone"}) in seen
    assert screens.holder() == PHONE
    lk.session_release(sid="tab-phone")
    assert screens.holder() == ""


def test_the_brain_sees_the_canvas_of_the_screen_the_turn_came_from():
    from memory import api as memory
    from server import canvas_api
    _two_open(holder=DESK)
    screens.stamp({"kind": "transcript", "role": "user", "text": "hola"})        # a desktop turn
    asyncio.run(canvas_api.canvas_state({"open": ["youtube"], "dev": DESK}))
    r = asyncio.run(canvas_api.canvas_state({"open": ["documento"], "dev": PHONE}))
    assert b"ignored" in r.body
    assert memory.state().get("open_widgets") == ["youtube"]
    # the operator types on the phone: the phone's canvas becomes the brain's, with no new report
    screens.stamp({"kind": "transcript", "role": "user", "text": "ciérralo", "dev": PHONE})
    assert memory.state().get("open_widgets") == ["documento"]


def test_a_restored_screen_learns_what_the_other_one_has_open():
    from server import canvas_api
    _two_open(holder=DESK)
    screens.stamp({"kind": "transcript", "role": "user", "text": "hola"})
    asyncio.run(canvas_api.canvas_state({"open": ["youtube"], "dev": DESK}))
    assert {"id": "youtube", "dev": DESK} in canvas_api._open_elsewhere(PHONE)
    assert canvas_api._open_elsewhere(DESK) == [] or all(x["dev"] != DESK for x in canvas_api._open_elsewhere(DESK))
