"""A fact the voice process asks twice is replayed once by the body (measured 2026-11-19).

The voice process asks ONCE more for his final words and the items when a batch is not answered inside its short
timeout. A body whose loop was held HAS the first batch and answers late, so the second ask replayed the same fact:
his sentence and the reply twice on the wall, about a second apart (9 of 57 finals in one session).

The tests go through the body's three doors (`server/voice_child_api.py`) with the replay captured, so removing the
door's filter fails them. A sentence said twice on purpose carries two stamps and is replayed twice.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server import voice_child_api, voice_child_once
from voice import remote_session


@pytest.fixture
def door(monkeypatch):
    replayed = []
    voice_child_once.forget()
    monkeypatch.setattr(voice_child_api, "_allowed", lambda request: True)
    monkeypatch.setattr(remote_session, "handle_batch", lambda events: replayed.extend(events or ()) or len(events or ()))
    monkeypatch.setattr(remote_session, "kickoff",
                        lambda room, events=None: replayed.extend(events or ()) or {"greet": ""})

    async def turn_lines(payload):
        replayed.extend(payload.get("events") or ())
        yield {"t": "end"}
    monkeypatch.setattr(remote_session, "turn_lines", turn_lines)
    app = FastAPI()
    app.include_router(voice_child_api.router)
    yield TestClient(app), replayed
    voice_child_once.forget()


def _final(text, at):
    return {"k": "transcript", "final": True, "text": text, "at": at}


def _item(text, at, role="assistant"):
    return {"k": "item", "role": role, "text": text, "speech_id": "s1", "surfaced": False, "at": at}


def _words(replayed, k):
    return [e["text"] for e in replayed if e["k"] == k]


def test_a_batch_answered_late_and_asked_again_is_replayed_once(door):
    client, replayed = door
    first = [{"k": "user_state", "state": "listening", "at": 99.9}, _final("que te calles", 100.25), _item("Vale.", 100.26)]
    again = [{**e, "_retried": True} for e in first if e["k"] != "user_state"]   # what the sender asks once more
    assert client.post("/api/voice/child/events", json={"events": first}).json()["n"] == 3
    assert client.post("/api/voice/child/events", json={"events": again}).json()["n"] == 0
    assert _words(replayed, "transcript") == ["que te calles"] and _words(replayed, "item") == ["Vale."]
    assert voice_child_once.STATS["dropped"] == 2


def test_the_same_sentence_said_again_is_a_new_fact(door):
    client, replayed = door
    client.post("/api/voice/child/events", json={"events": [_final("para", 100.0)]})
    client.post("/api/voice/child/events", json={"events": [_final("para", 100.6)]})      # he said it twice
    client.post("/api/voice/child/events", json={"events": [_item("Sí.", 101.0), _item("Sí.", 103.0)]})
    assert _words(replayed, "transcript") == ["para", "para"] and _words(replayed, "item") == ["Sí.", "Sí."]


def test_a_fact_a_turn_carried_and_the_line_asks_again_is_replayed_once(door):
    client, replayed = door
    fact = _final("pon música", 200.5)
    client.post("/api/turn/stream", json={"text": "pon música", "events": [fact]})
    client.post("/api/voice/child/kickoff", json={"room": "r", "events": [fact, _final("otra", 201.0)]})
    client.post("/api/voice/child/events", json={"events": [{**fact, "_retried": True}]})
    assert _words(replayed, "transcript") == ["pon música", "otra"]


def test_captions_states_and_unstamped_facts_always_pass(door):
    client, replayed = door
    caption = {"k": "transcript", "final": False, "text": "pon mú", "at": 300.0}
    state = {"k": "user_state", "state": "speaking", "at": 300.0}
    bare = {"k": "transcript", "final": True, "text": "sin sello"}
    for _ in range(2):
        client.post("/api/voice/child/events", json={"events": [caption, state, bare]})
    assert len(replayed) == 6


def test_the_memory_of_replayed_facts_is_bounded():
    voice_child_once.forget()
    voice_child_once.once([_final("x", float(i)) for i in range(voice_child_once._KEPT + 50)])
    assert len(voice_child_once._SEEN) == voice_child_once._KEPT == len(voice_child_once._ORDER)
    assert len(voice_child_once.once([_final("x", 0.0)])) == 1, "a fact older than the memory is replayed, never lost"
    voice_child_once.forget()
