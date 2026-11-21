"""A question about the agent itself is answered from its own catalogue and its live facts (V2-932).

Measured 2026-11-17: with the camera's «look at me» on, the agent said «te veo» and nine seconds later «no tengo cámara».
`about_self(topic)` reads the catalogue entry in his language (`i18n/genesis/<lang>/self.json`) and the live facts that
entry names (`nucleo/self/snapshot.py`); the screen's beat carries the camera FLAG, and the live tail says the camera is
on only while it is. ES and EN.

Disarm: drop the `camera` assignment in `voice/screens.beat` → the camera tests go red.
"""
from __future__ import annotations

import json

import pytest

from nucleo.self import about, snapshot
from voice import screens


@pytest.fixture(autouse=True)
def _clean_screens():
    screens._reset_for_tests()
    yield
    screens._reset_for_tests()


def _facts(system: str) -> dict:
    """The live facts block of a composed answer pass (its last paragraph is the JSON)."""
    return json.loads(system.rsplit("\n", 1)[-1])


@pytest.mark.parametrize("code, says, denies", [
    ("es", "Ajustes ⚙ ▸ Forma física", "NO te ve"),
    ("en", "Settings ⚙ ▸ Physical form", "It does NOT see you"),
])
def test_the_camera_entry_is_answered_in_his_language_with_its_live_fact(code, says, denies):
    screens.beat("desktop:a1", visible=True, camera=True)
    system = about.compose_system("", "¿me ves?" if code == "es" else "can you see me?", "camera", code=code)
    assert says in system and denies in system
    facts = _facts(system)
    assert facts["camera"], "the camera running on the computer is a live fact of the answer"


@pytest.mark.parametrize("code, entry_word", [("es", "palabra de activación"), ("en", "Wake-word mode")])
def test_the_wake_word_entry_carries_the_name_and_the_mode(code, entry_word, monkeypatch):
    monkeypatch.setattr(snapshot, "name", lambda: "Quillon")
    monkeypatch.setattr(snapshot, "wake_mode", lambda: "smart")
    system = about.compose_system("", "how do I make you listen only to your name?", "wake_word", code=code)
    assert entry_word in system
    assert _facts(system) == {"name": "Quillon", "wake_mode": "smart"}, "only the facts the entry names, read live"


def test_an_unknown_topic_reads_the_overview():
    assert about.entry("nonsense")["id"] == "overview"
    assert about.entry("CAMERA")["id"] == "camera"


def test_a_broken_reader_is_absent_never_guessed(monkeypatch):
    monkeypatch.setattr(snapshot, "build", lambda: (_ for _ in ()).throw(OSError("gone")))
    monkeypatch.setattr(snapshot, "host", lambda: {"kind": "self-hosted"})
    assert snapshot.fields(["host", "build", "not_a_field"]) == {"host": {"kind": "self-hosted"}}


def test_the_camera_flag_reaches_the_snapshot_and_leaves_it():
    screens.beat("mobile:p1", visible=True)
    assert snapshot.camera() == []
    screens.beat("mobile:p1", camera=True)
    assert len(snapshot.camera()) == 1
    screens.beat("mobile:p1", visible=False)            # a beat without the flag keeps it
    assert len(snapshot.camera()) == 1
    screens.beat("mobile:p1", camera=False)
    assert snapshot.camera() == []


def test_the_beat_route_passes_the_flag():
    from server import screens_api
    screens_api.beat({"dev": "desktop:b2", "visible": True, "camera": True})
    assert snapshot.camera(), "POST /api/screens/beat {camera:true} sets the flag"
    screens_api.beat({"dev": "desktop:b2", "camera": "yes"})   # not a boolean: ignored
    assert snapshot.camera()


@pytest.mark.parametrize("code, word", [("es", "ENCENDIDA"), ("en", "is ON")])
def test_the_live_tail_says_the_camera_only_while_it_runs(code, word, monkeypatch):
    monkeypatch.setattr(about, "words", lambda c=None, _w=about.words: _w(code))
    monkeypatch.setattr(snapshot, "face_on", lambda: False)
    assert snapshot.live_lines() == [], "no screen open: the tail pays nothing"
    screens.beat("desktop:c3", visible=True)
    assert snapshot.live_lines() == [], "a screen without the camera: still nothing"
    screens.beat("desktop:c3", camera=True)
    lines = snapshot.live_lines()
    assert len(lines) == 1 and word in lines[0]
    screens.beat("desktop:c3", camera=False)
    assert snapshot.live_lines() == []


def test_the_face_line_names_the_face_worn_on_an_open_screen(monkeypatch):
    monkeypatch.setattr(snapshot, "presence", lambda: {"face": "c-porcelain", "on": True})
    monkeypatch.setattr(about, "words", lambda c=None, _w=about.words: _w("en"))
    assert snapshot.live_lines() == [], "no screen open: no face line"
    screens.beat("desktop:d4", visible=True)
    lines = snapshot.live_lines()
    assert len(lines) == 1 and "«" in lines[0] and "c-porcelain" not in lines[0], "the face by its name, not its id"


def test_prepare_composes_off_the_loop_and_leaves_its_trace(monkeypatch):
    import asyncio
    monkeypatch.setattr(about, "words", lambda c=None, _w=about.words: _w("en"))
    seen = []
    system = asyncio.run(about.prepare({"topic": "feedback"}, "how do I report a bug?", "", lambda *a, **k: seen.append(k)))
    assert "Feedback button" in system and "how do I report a bug?" in system
    assert seen and seen[0]["extra"]["topic"] == "feedback"
