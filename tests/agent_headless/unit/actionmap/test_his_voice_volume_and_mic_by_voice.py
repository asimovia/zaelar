"""His voice's VOLUME and the MIC by voice, and the two one-way acts (V2-930, node 4.571).

The operator, 2026-11-17: by voice, on the phone and on the desktop, it must be 100 % reliable that «apaga el altavoz»
turns the agent's speaker off and «enciende el altavoz» back on (it keeps listening), that «sube / baja el volumen» and
«volumen al 30 %» move the agent's OWN voice on that screen, and that «apágate» and «silencia el micrófono» work — one
way: after them he cannot be heard, so the way back is the button, and the line before it says so.

The class: an order to the agent's own body. The mechanism stays ONE door (`nucleo/acts/self_controls.py`) reached by
the action map's seeds and the model's `agent_controls` call; this file pins what V2-930 added on the brain's side:

  1. every new act reaches the door from both lanes and leaves exactly its `controls` event, in ES and EN;
  2. a level is a NUMBER clamped to 0-100, and a `volume_set` without one emits nothing (nothing to claim);
  3. a one-way act's line names the button as the way back and is said even over the model's own words, and even with
     short acks switched off — on both lanes;
  4. a combined order runs both acts in his order — two model calls, or the barge-in stop plus a one-word order
     («cállate y apágate»), whose remainder used to be dropped;
  5. a bare «sube el volumen» is not seeded — a playing video or song owns that order as often as the agent does.

The screen half (idempotent by state, volume persisted, the button moved) is `tests/browser/unit/voice/
test_his_controls_move_the_buttons.mjs` and the rendered phone/desktop test beside it.
Disarm: `test_disarm_the_one_way_tail` removes the tail and the off line stops being said over the model's words.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.platform import turn_harness as H

ENGINE = Path(__file__).resolve().parents[4]
_HISTORY = [{"role": "user", "text": "hola"}, {"role": "assistant", "text": "Hola, aquí estoy."}]


@pytest.fixture
def johnny():
    from voice import attention
    before = attention._state.get("assistant_name")
    attention.set_assistant_name("Johnny")
    yield
    attention._state["assistant_name"] = before


def _case(cid, lang, phrase, expect, model=None):
    case = {"id": cid, "lang": lang, "phrase": phrase, "source": "his volume and mic by voice",
            "screen": {"open": []}, "expect": expect, "history": _HISTORY}
    if model is not None:
        case["model"] = model
    return case


def _controls(out) -> list[tuple[str, object]]:
    return [(str(e.get("act") or e.get("label")), e.get("value")) for e in out.events if e.get("kind") == "controls"]


def _line(act, lang, n=None):
    from i18n import langs
    return str(langs.words(f"controls_said.{act}", code=lang)).replace("{n}", str(n))


# ── 1. the seeds: mic and his voice's volume, ES and EN, behind his name ─────────────────────────────────────
@pytest.mark.parametrize("lang,phrase,act", [
    ("es", "Johnny, silencia el micrófono.", "mic_off"),
    ("es", "Johnny, apaga el micro", "mic_off"),
    ("es", "Johnny, sube tu volumen", "volume_up"),
    ("es", "Johnny, habla más bajo", "volume_down"),
    ("en", "Johnny, mute the microphone.", "mic_off"),
    ("en", "Johnny, turn off the mic", "mic_off"),
    ("en", "Johnny, speak louder", "volume_up"),
    ("en", "Johnny, turn your volume down", "volume_down"),
])
def test_a_seeded_order_reaches_the_door_without_the_model(johnny, lang, phrase, act):
    case = _case(f"vol-{lang}-{act}", lang, phrase, f"controls:{act}")
    out = H.run_case(case)
    assert not out.failures(case), (out.as_dict(), out.events[-6:])
    assert _controls(out) == [(act, None)]


def test_a_bare_volume_order_is_not_seeded_it_may_be_the_video_s():
    from nucleo.actionmap.normalize import normalize as _n
    for lang, bare in (("es", ("sube el volumen", "baja el volumen", "bajalo")), ("en", ("volume up", "turn it down"))):
        d = json.loads((ENGINE / f"i18n/genesis/{lang}/actionmap.json").read_text(encoding="utf-8"))
        have = {_n(e["phrase"]) for e in d["entries"]}
        for b in bare:
            assert _n(b) not in have, f"{lang}: «{b}» is seeded — a playing video/song owns that order as often"
        assert d["version"] >= 21, "new phrases in an old version reach no existing install"


# ── 2. the model's call: every new act, a level clamped, a level-less volume_set refused ─────────────────────
@pytest.mark.parametrize("lang,phrase,args,want", [
    ("es", "pon el volumen al treinta por ciento", {"act": "volume_set", "value": 30}, ("volume_set", 30)),
    ("en", "set your volume to 30 percent", {"act": "volume_set", "value": "30%"}, ("volume_set", 30)),
    ("es", "ponte al máximo, al ciento cincuenta", {"act": "volume_set", "value": 150}, ("volume_set", 100)),
    ("en", "volume at minus five", {"act": "volume_set", "value": -5}, ("volume_set", 0)),
    ("es", "bájalo un poco", {"act": "volume_down"}, ("volume_down", None)),
    ("en", "a bit louder please", {"act": "volume_up"}, ("volume_up", None)),
    ("es", "apaga el altavoz", {"act": "mute"}, ("mute", None)),
    ("en", "turn the speaker back on", {"act": "unmute"}, ("unmute", None)),
    ("es", "deja de escucharme un rato", {"act": "mic_off"}, ("mic_off", None)),
])
def test_the_models_call_reaches_the_same_door(johnny, lang, phrase, args, want):
    act = want[0]
    case = _case(f"vol-model-{lang}-{act}", lang, phrase, f"controls:{act}",
                 model={"say": "", "tools": [{"name": "agent_controls", "args": args}]})
    out = H.run_case(case)
    assert not out.failures(case), (out.as_dict(), out.events[-6:])
    assert _controls(out) == [want]
    assert _line(act, lang, want[1]) in out.reply, (out.reply, act)
    assert "{n}" not in out.reply


def test_a_volume_set_without_a_level_emits_nothing():
    from nucleo.acts import self_controls
    fired = []
    for v in (None, "", "loud", float("nan"), float("inf")):
        assert self_controls.apply("volume_set", lambda *a, **k: fired.append(a), src="flash", value=v) is False, v
    assert fired == []
    assert self_controls.level("45.4 %") == 45 and self_controls.level(-1) == 0 and self_controls.level(101) == 100


def test_the_tool_offers_every_act_and_a_level():
    from nucleo.flash import router
    from nucleo.acts import self_controls
    fn = next(t["function"] for t in router.TOOLS if t["function"]["name"] == "agent_controls")
    props = fn["parameters"]["properties"]
    assert set(props["act"]["enum"]) == set(self_controls.ACTS), "an act the door knows and the model cannot call"
    assert props["value"]["type"] == "integer"


# ── 3. one way: the line names the button, said over his words and with acks off ────────────────────────────
@pytest.mark.parametrize("lang", ["es", "en"])
@pytest.mark.parametrize("act", ["off", "mic_off"])
def test_a_one_way_act_says_the_way_back_even_over_the_models_words(johnny, lang, act):
    say = "Vale." if lang == "es" else "Okay."
    case = _case(f"oneway-{lang}-{act}", lang, "hasta luego, desconecta" if lang == "es" else "bye, disconnect",
                 f"controls:{act}", model={"say": say, "tools": [{"name": "agent_controls", "args": {"act": act}}]})
    out = H.run_case(case)
    assert _controls(out) == [(act, None)]
    assert say in out.reply and _line(act, lang) in out.reply, out.reply


@pytest.mark.parametrize("lang,phrase,act", [("es", "Johnny, apágate.", "off"), ("en", "Johnny, mute the mic", "mic_off")])
def test_a_one_way_seed_says_its_line_even_with_short_acks_off(johnny, monkeypatch, lang, phrase, act):
    from nucleo import style_policy
    from voice.engine.llm.providers import fast_lane
    said = []

    async def _ack(brain, receipt=""):
        said.append(receipt)
    monkeypatch.setattr(style_policy, "confirm_short_actions", lambda: False)
    monkeypatch.setattr(fast_lane, "_speak_ack", _ack)
    out = H.run_case(_case(f"oneway-seed-{lang}", lang, phrase, f"controls:{act}"))
    assert _controls(out) == [(act, None)]
    assert said == [_line(act, lang)], said


def test_every_line_exists_in_both_languages_and_one_way_names_the_button():
    from nucleo.acts import self_controls
    for lang in ("es", "en"):
        for act in ("mute", "unmute", "volume_up", "volume_down", "volume_set", "mic_off", "off"):
            assert _line(act, lang, 30), (lang, act)
    assert self_controls.ONE_WAY == {"off", "mic_off"}


# ── 4. combined orders: both run, in his order ───────────────────────────────────────────────────────────────
# «cállate y apágate»: «cállate» is the barge-in stop (it silences the voice and ends a bare turn), and the rest of the
# sentence keeps its turn. That remainder was dropped when it was ONE word — «apágate» died in silence while «shut up
# and switch off» worked — so a one-word remainder now counts when it is a declared order (the action map).
@pytest.mark.parametrize("lang,phrase", [("es", "cállate y apágate"), ("en", "shut up and switch off"),
                                         ("es", "Johnny, cállate y apágate.")])
def test_a_stop_and_an_off_both_run(johnny, lang, phrase):
    out = H.run_case(_case(f"combo-stop-{lang}", lang, phrase, "controls:off"))
    assert _controls(out) == [("off", None)], out.events[-8:]


def test_a_one_word_remainder_counts_only_when_it_is_a_declared_order():
    from voice import interrupt_grammar as g
    known = {"apágate"}.__contains__                       # the caller's reading of the declared orders
    assert g.stop_remainder("cállate y apágate", known) == "apágate"
    assert g.stop_remainder("cállate y apágate") == "", "without a reading of the declared orders, the old floor"
    assert g.stop_remainder("cállate, música", known) == "", "a bare word that is no order buys no model turn"
    assert g.stop_remainder("cállate, por favor", known) == ""
    assert g.close_all_remainder("cierra todo y apágate", known) == "apágate"


@pytest.mark.parametrize("lang,phrase", [("es", "silencia el altavoz y apágate del todo"),
                                         ("en", "mute the speaker and then turn yourself off")])
def test_a_combined_order_runs_both_acts_in_order(johnny, lang, phrase):
    case = _case(f"combo-{lang}", lang, phrase, "controls:mute",
                 model={"say": "", "tools": [{"name": "agent_controls", "args": {"act": "mute"}},
                                             {"name": "agent_controls", "args": {"act": "off"}}]})
    out = H.run_case(case)
    assert _controls(out) == [("mute", None), ("off", None)], out.events[-8:]
    assert _line("off", lang) in out.reply, out.reply


def test_the_same_act_twice_in_one_turn_runs_once(johnny):
    case = _case("twice", "es", "apágate, apágate", "controls:off",
                 model={"say": "", "tools": [{"name": "agent_controls", "args": {"act": "off"}},
                                             {"name": "agent_controls", "args": {"act": "off"}}]})
    assert _controls(H.run_case(case)) == [("off", None)]


# ── the disarm ───────────────────────────────────────────────────────────────────────────────────────────────
def test_disarm_the_one_way_tail(johnny, monkeypatch):
    from nucleo.acts import self_controls
    monkeypatch.setattr(self_controls, "one_way", lambda act: False)
    case = _case("disarm-tail", "es", "hasta luego, desconecta", "controls:off",
                 model={"say": "Vale.", "tools": [{"name": "agent_controls", "args": {"act": "off"}}]})
    out = H.run_case(case)
    assert _controls(out) == [("off", None)]
    assert _line("off", "es") not in out.reply, "with the tail disarmed the way back is still said — the test proves nothing"
