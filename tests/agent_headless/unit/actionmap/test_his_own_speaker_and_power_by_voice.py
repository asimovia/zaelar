"""His OWN speaker and ⏻, by voice — one door with the buttons, on the screen that heard him.

He often talks to the agent from across the room. When its speaker bothers him he wants «Johnny, mutea el altavoz»
(it keeps listening) and, when he is done, «Johnny, apágate» (the session ends, exactly as the ⏻ ends it). Neither
had a route: the 🔊 and the ⏻ were buttons and nothing else.

The class: a control of the agent's own body that only a hand could reach. The mechanism: ONE `controls` act
(`nucleo/acts/self_controls.py`) that two lanes reach — the action map for a known whole-utterance order and the
model's `agent_controls` call for any other wording — and that the screen which heard him obeys by running its own
button (`frontend/app/services/sse.js` → `session.toggleBotMute` / `power.setPower`). Pinned here:

  1. the seeded orders, ES and EN, with his chosen name in front, are the action map's — no model;
  2. the model's call takes the very same door and emits the very same event;
  3. a REMARK about the speaker («qué ruido hace el altavoz») does nothing — no seed matches it and the model, which
     made no call, has no order to obey;
  4. the event is scoped to the screen that heard him (`origin_dev`), and that screen runs the button's function.

Disarm: `test_the_disarmed_door_emits_nothing_and_the_order_falls_to_the_model` turns the door into a no-op and the
seeded order stops being an act — the red this file exists to show.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.platform import turn_harness as H

ENGINE = Path(__file__).resolve().parents[4]
_HISTORY = [{"role": "user", "text": "hola"}, {"role": "assistant", "text": "Hola, aquí estoy."}]


@pytest.fixture
def johnny():
    """His chosen name is a SLOT (the wake word list grows with it), never a word in a table."""
    from voice import attention
    before = attention._state.get("assistant_name")
    attention.set_assistant_name("Johnny")
    yield
    attention._state["assistant_name"] = before


def _case(cid, lang, phrase, expect, model=None):
    case = {"id": cid, "lang": lang, "phrase": phrase, "source": "his own controls by voice",
            "screen": {"open": []}, "expect": expect, "history": _HISTORY}
    if model is not None:
        case["model"] = model
    return case


def _controls(out) -> list[str]:
    return [str(e.get("act") or e.get("label")) for e in out.events if e.get("kind") == "controls"]


# ── 1. the seeded orders are the action map's, in both languages, behind his name ─────────────────────────
@pytest.mark.parametrize("lang,phrase,act", [
    ("es", "Johnny, silencia el altavoz.", "mute"),
    ("es", "Johnny, mutea el altavoz", "mute"),
    ("es", "Johnny, quita el mute", "unmute"),
    ("es", "Johnny, vuelve a hablar.", "unmute"),
    ("es", "Johnny, apágate.", "off"),
    ("en", "Johnny, mute the speaker.", "mute"),
    ("en", "Johnny, unmute the speaker", "unmute"),
    ("en", "Johnny, turn yourself off.", "off"),
    ("en", "Johnny, switch off.", "off"),
])
def test_a_seeded_order_is_the_buttons_act_without_the_model(johnny, lang, phrase, act):
    out = H.run_case(_case(f"ctl-{lang}-{act}", lang, phrase, f"controls:{act}"))
    assert not out.failures(_case(f"ctl-{lang}-{act}", lang, phrase, f"controls:{act}")), (out.as_dict(), out.events[-6:])
    assert _controls(out) == [act], f"exactly one `controls:{act}` event, the one its button's door obeys"


# ── 2. any other wording: the model's call takes the same door ────────────────────────────────────────────
@pytest.mark.parametrize("lang,phrase,act", [
    ("es", "Oye, ¿te puedes callar un rato con el altavoz? que me molesta el ruido", "mute"),
    ("en", "Could you go quiet on the speaker for a while, it's bugging me", "mute"),
    ("es", "Bueno Johnny, ya hemos acabado por hoy, apaga todo lo tuyo", "off"),
    ("en", "Alright, we're done for today, power yourself down", "off"),
])
def test_the_models_call_takes_the_same_door(johnny, lang, phrase, act):
    case = _case(f"ctl-model-{lang}-{act}", lang, phrase, f"controls:{act}",
                 model={"say": "", "tools": [{"name": "agent_controls", "args": {"act": act}}]})
    out = H.run_case(case)
    assert not out.failures(case), (out.as_dict(), out.events[-6:])
    assert _controls(out) == [act]


# ── 3. a remark is no order ───────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("lang,phrase", [
    ("es", "Qué ruido hace el altavoz, ¿no?"),
    ("es", "Johnny, el altavoz suena un poco raro hoy"),
    ("en", "The speaker sounds a bit loud today"),
])
def test_a_remark_about_the_speaker_does_nothing(johnny, lang, phrase):
    case = _case(f"ctl-remark-{lang}", lang, phrase, "talk",
                 model={"say": "Sí, puedo bajarlo si quieres." if lang == "es" else "I can mute it if you like.",
                        "tools": []})
    out = H.run_case(case)
    assert not out.failures(case), out.as_dict()
    assert _controls(out) == [], "a remark switched his speaker or the agent"


def test_an_unknown_act_is_refused_by_the_door_and_the_map():
    from nucleo.actionmap import executor
    from nucleo.acts import self_controls
    fired = []
    assert self_controls.apply("explode", lambda *a, **k: fired.append(a), src="flash") is False
    assert executor.validate({"do": "controls", "act": "explode"})
    assert fired == []


# ── 4. the screen that heard him, and the button it runs ──────────────────────────────────────────────────
def test_the_act_is_scoped_to_the_screen_that_heard_him_and_runs_the_buttons_door():
    scope = (ENGINE / "frontend/app/services/event-scope.js").read_text(encoding="utf-8")
    assert 'controls: "*"' in scope, "a «controls» act must land only on the origin screen (origin_dev)"
    sse = (ENGINE / "frontend/app/services/sse.js").read_text(encoding="utf-8")
    assert 'd.kind === "controls"' in sse and "self-controls.js" in sse, "the stream must hand `controls` to its module"
    body = (ENGINE / "frontend/app/services/self-controls.js").read_text(encoding="utf-8")
    assert "setPower(true" in body, "«off» must run the ⏻'s own door (power.setPower), not a copy of it"
    assert "toggleBotMute" in body and "openSpeakerHere" in body, "the 🔊 must run the speaker button's own door"
    orb = (ENGINE / "frontend/app/components/Orb.js").read_text(encoding="utf-8")
    assert "session.openSpeakerHere" in orb and "session.toggleBotMute" in orb and "power.togglePower" in orb, \
        "the button doors this act reuses moved — follow them"


def test_both_packs_seed_every_act_and_the_version_moved():
    import json
    for lang in ("es", "en"):
        d = json.loads((ENGINE / f"i18n/genesis/{lang}/actionmap.json").read_text(encoding="utf-8"))
        assert d["version"] >= 17, f"{lang}: new phrases in an old version reach no existing install"
        acts = {(e.get("action") or {}).get("act") for e in d["entries"] if (e.get("action") or {}).get("do") == "controls"}
        assert acts == {"mute", "unmute", "off"}, (lang, acts)


# ── the disarm ────────────────────────────────────────────────────────────────────────────────────────────
def test_the_disarmed_door_emits_nothing_and_the_order_falls_to_the_model(johnny, monkeypatch):
    from nucleo.acts import self_controls
    monkeypatch.setattr(self_controls, "apply", lambda *a, **k: False)
    case = _case("ctl-disarmed", "es", "Johnny, apágate.", "controls:off")
    out = H.run_case(case)
    assert _controls(out) == []
    assert out.failures(case), "with the door disarmed the order still read as the ⏻ — the test proves nothing"
