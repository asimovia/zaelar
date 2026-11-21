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


def test_a_bare_volume_order_is_not_seeded_it_may_be_the_video_s():
    from nucleo.actionmap.normalize import normalize as _n
    for lang, bare in (("es", ("sube el volumen", "baja el volumen", "bajalo")), ("en", ("volume up", "turn it down"))):
        d = json.loads((ENGINE / f"i18n/genesis/{lang}/actionmap.json").read_text(encoding="utf-8"))
        have = {_n(e["phrase"]) for e in d["entries"]}
        for b in bare:
            assert _n(b) not in have, f"{lang}: «{b}» is seeded — a playing video/song owns that order as often"
        assert d["version"] >= 21, "new phrases in an old version reach no existing install"


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


def test_every_line_exists_in_both_languages_and_one_way_names_the_button():
    from nucleo.acts import self_controls
    for lang in ("es", "en"):
        for act in ("mute", "unmute", "volume_up", "volume_down", "volume_set", "mic_off", "off"):
            assert _line(act, lang, 30), (lang, act)
    assert self_controls.ONE_WAY == {"off", "mic_off"}


def test_a_one_word_remainder_counts_only_when_it_is_a_declared_order():
    from voice import interrupt_grammar as g
    known = {"apágate"}.__contains__                       # the caller's reading of the declared orders
    assert g.stop_remainder("cállate y apágate", known) == "apágate"
    assert g.stop_remainder("cállate y apágate") == "", "without a reading of the declared orders, the old floor"
    assert g.stop_remainder("cállate, música", known) == "", "a bare word that is no order buys no model turn"
    assert g.stop_remainder("cállate, por favor", known) == ""
    assert g.close_all_remainder("cierra todo y apágate", known) == "apágate"
