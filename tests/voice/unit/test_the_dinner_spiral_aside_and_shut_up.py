from tests import voice_turn_source as _vts
"""V2-657 — the dinner spiral (measured 2026-09-10, session 130418ed): with the household talking near the
mic, every table utterance landed inside the open conversation window, the model answered it («Acostaros» →
«Buenas noches, Ricardo»), and both the utterance and the answer re-anchored the window — so the
conversation structurally could not die, until «¿Por qué sigues escuchando? Maldita sea, cállate. Apaga.»

Three mechanisms close it, each measured here:
  1. `[[aparte]]` — the model's SANCTIONED silence for a turn addressed to somebody else present; the
     channel marks the turn handled (no mute backstop, no hollow repair) and RETRACTS the window refresh.
  2. `attention.retract_last_directed()` — undo exactly one admission's re-anchor, refusing when anything
     newer re-anchored since (deafness is the worse failure, V2-655).
  3. The spoken SHUT-UP order («cállate», «silencio») closes the window at the gate, reaching no model —
     answering it would itself re-anchor the window it ordered shut.
"""
import importlib.util
import os

import pytest

from voice import attention

ENG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for k in ("ZAELAR_ATTENTION", "ZAELAR_ATTENTION_WINDOW", "ZAELAR_WAKEWORDS"):
        monkeypatch.delenv(k, raising=False)
    attention.reset()
    yield
    attention.reset()


def _src(rel: str) -> str:
    return _vts.read(os.path.join(ENG, rel))


# ── the shut-up grammar ─────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("txt", [
    "Cállate.",
    "cállate ya",
    "Maldita sea, cállate. Apaga.",          # the session's literal sentence — the order lives mid-turn
    "¿Por qué sigues escuchando? Maldita sea, cállate.",
    "zaelar, cállate",                        # wake word stripped before matching
    "Silencio.",
    "deja de escucharme",
    "shut up",
])
def test_a_shut_up_order_is_recognized(txt):
    assert attention.is_shut_up(txt)


@pytest.mark.parametrize("txt", [
    "no te calles",                           # negated — never an order to shut
    "apaga",                                  # names the POWER or a device, deliberately out
    "apaga la música",
    "calla a los niños",                      # somebody else is told to be quiet
    "te lo digo para que no te calles nunca",
    "cállate luego cuando acabe la canción",  # extra cargo after the verb: not the bare order
    "",
])
def test_room_talk_is_not_a_shut_up_order(txt):
    assert not attention.is_shut_up(txt)


def test_close_window_wipes_the_anchor_and_tells_the_clients(monkeypatch):
    import voice.observer as observer
    monkeypatch.setenv("ZAELAR_ATTENTION", "smart")
    seen = []
    monkeypatch.setattr(observer, "emit", lambda *a, **k: seen.append((a, k)))
    t = 1000.0
    attention.note_directed(now=t)
    assert attention.window_open(now=t + 1)
    attention.close_window(src="voice-order")
    assert not attention.window_open(now=t + 1)
    assert any(a[:2] == ("ui", "orb:attention") for a, _ in seen), \
        "the ring must darken at once, like a mode flip"
    told = [k.get("extra") or {} for a, k in seen if a[:2] == ("ui", "orb:attention")]
    assert told and all("state" not in x and x.get("window") == "closed" for x in told), \
        "a closed window names no mode: a stop read as «attention: always» on his screens (E-5)"
    from pathlib import Path
    sse = (Path(__file__).resolve().parents[3] / "frontend/app/services/sse.js").read_text(encoding="utf-8")
    assert "if (d.state) store.setAttentionMode(" in sse, "the client changes its mode only when the event names one"


# ── the retract ─────────────────────────────────────────────────────────────────────────────────────────
def test_an_aside_admission_is_retracted_and_the_window_can_die(monkeypatch):
    monkeypatch.setenv("ZAELAR_ATTENTION", "smart")
    t = 1000.0
    attention.note_directed(now=t)            # his real turn opened the conversation
    attention.note_directed(now=t + 3)        # table talk admitted in-window (provisional by nature)
    assert attention.window_open(now=t + 7)   # the refresh keeps it alive past the first anchor
    assert attention.retract_last_directed()
    assert not attention.window_open(now=t + 7), \
        "with the aside retracted, the window expires from HIS last word — the spiral is the bug"
    assert attention.window_open(now=t + 4)   # ...but his own anchor survives intact


def test_the_retract_refuses_once_something_newer_anchored(monkeypatch):
    monkeypatch.setenv("ZAELAR_ATTENTION", "smart")
    t = 1000.0
    attention.note_directed(now=t)
    # The agent's own falling edge (note_bot_speech) re-anchors by writing last_directed directly —
    # after that, rolling back would eat an anchor that is not ours.
    attention._state["last_directed"] = t + 9
    assert not attention.retract_last_directed()
    assert attention.window_open(now=t + 10)


def test_a_second_retract_is_a_noop():
    attention.note_directed(now=500.0)
    assert attention.retract_last_directed()
    assert not attention.retract_last_directed()


# ── the gate swallows the shut-up turn ──────────────────────────────────────────────────────────────────
def _load_attention_turn():
    # By file path on purpose: importing the providers PACKAGE registers every provider (livekit stack).
    spec = importlib.util.spec_from_file_location(
        "attention_turn_isolated", os.path.join(ENG, "voice/engine/llm/providers/attention_turn.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── the [[aparte]] tag ──────────────────────────────────────────────────────────────────────────────────
def test_the_aparte_tag_is_parsed_and_never_spoken():
    from voice.tag_protocol import strip_tags
    emitted = []
    spoken, rest = strip_tags("[[aparte]]", lambda a, e: emitted.append((a, e)), True)
    assert ("aparte" in [a for a, _ in emitted]) and not spoken.strip() and not rest


# ── the honest provider label (a stale stored label that reappeared in v2.json) ──────────────────────────
def test_a_stale_stored_label_loses_to_the_endpoint():
    from nucleo.llm.model_spec import _provider_label
    assert _provider_label("xai", "https://api.deepseek.com") == "deepseek"
    assert _provider_label("", "https://api.deepseek.com") == "deepseek"
    assert _provider_label("ollama", None) == "ollama"          # ollama IS routing, not a label
    assert _provider_label("xai", None) == "deepseek"           # no endpoint stored: the default endpoint decides
    assert _provider_label("custom", "https://llm.example/v1") == "custom"   # unknown endpoint: the label may be true


def test_the_remote_profile_matches_the_canonical_model_table():
    """The profile WRITES config/v2.json, so a stale broker entry here resurrects the stale label on
    every re-apply — measured live 2026-09-10 at 21:59, an hour after the config had been cleaned."""
    import json
    from config import profiles
    table = json.load(open(os.path.join(ENG, "config/models.default.json")))
    titular = table["services"]["voice_brain"]["titular"]
    fast = profiles._PROFILES["cloud"]["v2"]["fast"]
    assert fast["provider"] == titular["provider"]
    assert fast["model"] == titular["model"]
    assert fast["base_url"] == titular["base_url"]
