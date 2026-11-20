"""Every word the provider gave reaches exactly one intervention, whole — on REAL provider messages (node 13.95,
V2-941, v3.1 B8d; I2).

The voice smoke (3b) lost his words: leading words dropped, whole sentences discarded `no_words`, the barge-in's words
never heard. The cause is TH-1: every new stream of the provider numbers its turns from 0 again. Synthetic messages
never showed it; the tester's recordings do (`fixtures/flux_raw/`, five real Flux message sequences from the 3a bench —
synthetic voices, invented text — each with its labels). Each one goes through the whole voice path the body runs: the
tap (`ear_tap`), the facts, the body's lane (`ear_in`, boot and seq) and the package's ear, then the conversation;
once as one stream, and once with the stream starting again before every turn of the provider (its turn numbers and
its audio clock from 0, as a reconnect or a new session does). The words of every `EndOfTurn` must be, in order and
nothing else, the words of the entries the conversation accepted.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from conversation.ports import Done
from conversation.testing.scripted_model import reply
from nucleo.conversation_host import ear_in
from tests.conversation.unit.convkit import Harness
from voice.engine.pipeline import ear_tap

FLUX = Path(__file__).resolve().parents[1] / "fixtures" / "flux_raw"
RECORDINGS = ("en-clean-03-g9", "es-pauses4000-00-g9u1", "en-interruption-00-g9", "mix-pauses1500-00-g9u1",
              "es-long-00-g9")
T0 = 1_800_000_000_000


def _shifted(msg: dict, turn0: int, s0: float) -> dict:
    """The message as a NEW stream would send it: its turns and its audio clock from 0."""
    return {**msg, "turn_index": msg["turn_index"] - turn0,
            "audio_window_start": max(0.0, msg.get("audio_window_start", 0) - s0),
            "audio_window_end": msg.get("audio_window_end", 0) - s0,
            "words": [{**w, "start": w["start"] - s0, "end": w["end"] - s0} for w in msg.get("words") or []]}


def _through_the_voice_path(store, name: str, restart: bool) -> tuple[list, list]:
    ear_in._reset_for_tests()
    h = Harness(store, grace=False)
    h.model.default = lambda ids: [reply("w_ok"), Done()]
    h.at(T0)
    facts: list = []
    tap = ear_tap.Tap("d1", facts.append)
    tap.new_stream()
    tap.clock.t0_wall_ms = T0
    finals, seq, turn0, s0 = [], 0, 0, 0.0
    for line in (FLUX / f"{name}.jsonl").read_text(encoding="utf-8").splitlines():
        msg = json.loads(line)["msg"]
        if msg.get("type") != "TurnInfo":
            continue
        if restart and msg["event"] == "StartOfTurn" and msg["turn_index"] > turn0:
            turn0, s0 = msg["turn_index"], float(msg.get("audio_window_start") or 0)
            tap.new_stream()
            tap.clock.t0_wall_ms = T0 + int(s0 * 1000)
        if restart:
            msg = _shifted(msg, turn0, s0)
        if msg["event"] == "EndOfTurn":
            finals += [w["word"] for w in msg.get("words") or ()]
        tap.on_message(msg)
        for fact in facts:
            seq += 1
            ear_in.receive({**fact, "boot": "b1", "seq": seq}, h.hear)
        facts.clear()
    h.settle(12_000)
    rows = sorted((r for _k, r in h.store.snapshot(h.conv.account).scan("inbox") if r["kind"] == "user.utterance"),
                  key=lambda r: r["accepted"])
    return finals, [w for r in rows for w in r["env"]["body"]["text"].split()]


@pytest.fixture(autouse=True)
def clean():
    ear_in._reset_for_tests()
    yield
    ear_in._reset_for_tests()


@pytest.mark.parametrize("restart", [False, True], ids=["one-stream", "a-new-stream-per-turn"])
@pytest.mark.parametrize("name", RECORDINGS)
def test_every_final_word_reaches_one_intervention_whole(store, name, restart):
    finals, heard = _through_the_voice_path(store, name, restart)
    assert finals and heard == finals, (len(finals), len(heard))


def test_the_recordings_are_what_their_manifest_froze():
    import hashlib
    files = json.loads((FLUX / "manifest.json").read_text(encoding="utf-8"))["files"]
    assert set(files) == set(RECORDINGS)
    for name, meta in files.items():
        assert hashlib.sha256((FLUX / f"{name}.jsonl").read_bytes()).hexdigest() == meta["sha256"], name
        assert hashlib.sha256((FLUX / f"{name}.labels.json").read_bytes()).hexdigest() == meta["labels_sha256"], name
