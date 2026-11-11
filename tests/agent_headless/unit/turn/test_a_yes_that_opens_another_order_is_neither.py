"""The answer to a waiting question is yes, no or NEITHER (V2-873, ES/EN).

Measured on a Spanish demo pass (2026-11-10):

  · «abre el que sea mejor oferta» (open the best offer — a link) was parked behind «Esto mueve dinero… ¿Sigo?», and
    «vale cierra los resultados» was then taken as the YES to that question and launched «Abrir la mejor oferta».

The classes, each with its mechanism:

  1. The parked errand's question waits on its ROW (a durable ask with two declared answers). When the turn's brief
     read the binding question, its pick is the reader — the task gate's word reading yields (CRIT-C13).
  2. With no pick, only a reply that IS one of the row's declared answers decides (V2-878 §4b: the word tables went):
     «vale cierra los resultados» is neither, whatever card order it opens. The declared yes is still the yes.
  3. When the brief read his turn as an ANSWER and its pick answered none of the waiting rows, the errand keeps
     waiting and he is TOLD so.

Disarms (seen red): `_the_binding_reads_it` → False; `_answered_none` → False.
"""
from __future__ import annotations

import threading
import time

import pytest

from nucleo.dispatch import confirm as dc
from nucleo.turn import brief as tb
from nucleo.turn import confirm_gates as gates

ORDER = {"es": "vale cierra los resultados", "en": "ok close the results"}
BARE = {"es": "Sí", "en": "Yes"}         # the declared yes of each language (`answer_yes`)


def _brief(result: dict):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "result": {"_call_id": "t", **result}, "_call_id": "t", "turn_id": "t",
            "open_ids": ["results"]}


def _v(choice, conf=0.95):
    return {"choice": choice, "confidence": conf, "probs": {choice: conf}, "used": True}


@pytest.fixture
def parked(monkeypatch):
    relaunched: list = []
    monkeypatch.setattr("nucleo.acts.errand.escalate_to_slowbrain",
                        lambda req, context=None: relaunched.append(req) or 1)
    monkeypatch.setattr(dc, "_PENDING_CONFIRM", {})
    monkeypatch.setattr(gates, "_named_parked", lambda _w: "")
    dc._PENDING_CONFIRM["9"] = {
        "request": "abre el que sea mejor oferta", "kind": "generic", "trusted": True, "context": {},
        "question": "Esto mueve dinero («abre el que sea mejor oferta») y no hago ningún cargo sin tu OK. ¿Sigo?",
        "sheet": "", "ts": time.time(), "uid": "row-9", "ask_id": f"row-9-start-{time.monotonic_ns()}"}
    return relaunched


@pytest.mark.parametrize("lang", ["es", "en"])
def test_the_rows_question_is_read_by_the_briefs_pick_not_by_his_words(parked, lang):
    """The binding verdict was read («none»): the task gate does not take his «vale» as the yes."""
    from nucleo.cli import worker_api_bind as bind
    brief = _brief({bind.KEY: _v(bind.NONE, 0.9)})
    for said in (ORDER[lang], BARE[lang]):
        assert not gates.resolve_all(said, brief=brief), f"«{said}» answered the parked errand by its words"
    assert "9" in dc._PENDING_CONFIRM and not parked


@pytest.mark.parametrize("lang", ["es", "en"])
@pytest.mark.parametrize("verdict", [{tb.CANVAS_KEY: _v("close")}, {tb.TARGET_KEY: _v("results:close")}],
                         ids=["canvas-close", "card-action"])
def test_a_yes_word_that_opens_a_sure_card_order_is_neither(parked, lang, verdict, monkeypatch):
    monkeypatch.setattr(tb, "owner_still_open", lambda _b, _o: True)
    ans = gates.resolve_all(ORDER[lang], brief=_brief(verdict))
    assert not ans, f"«{ORDER[lang]}» was read as {'YES' if ans.yes else 'NO'} to the parked errand"
    assert "9" in dc._PENDING_CONFIRM and not parked


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_bare_yes_still_answers(parked, lang, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    monkeypatch.setattr(tb, "owner_still_open", lambda _b, _o: True)
    ans = gates.resolve_all(BARE[lang], brief=_brief({tb.CANVAS_KEY: _v("close")}))
    assert ans and ans.gate == "task" and ans.yes and parked


# ── V2-873 · a «neither» is SAID; V2-878 §4b: only the declared answer is read without the brief ─────────────────

NEITHER = {"es": ["sí, y cierra el vídeo", "vale para el vídeo y cierra youtube", "vale cierra los resultados"],
           "en": ["yes, and close the video", "ok stop the video and close youtube", "ok close the results"]}


def _answered_none():
    from nucleo.cli import worker_api_bind as bind
    return _brief({tb.REQUEST_KEY: _v("answer"), bind.KEY: _v(bind.NONE, 0.9)})


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_yes_word_inside_a_longer_order_is_neither_and_is_said(parked, lang):
    """The brief read an ANSWER and its pick answered none of the rows: neither, and the gate hands back the request
    still waiting, which the turn says (`errand_still_waiting`). With no brief, a longer reply answers nothing."""
    for said in NEITHER[lang]:
        ans = gates.resolve_all(said, brief=_answered_none())
        assert not ans, f"«{said}» answered the parked errand"
        assert ans.waiting == "abre el que sea mejor oferta", f"«{said}»: the waiting errand is not said"
        assert not gates.resolve_all(said, brief=None), f"«{said}» answered by a word, with no brief"
    assert "9" in dc._PENDING_CONFIRM and not parked


@pytest.mark.parametrize("lang,word", [("es", "sí"), ("en", "yes")])
def test_a_one_word_answer_is_still_the_fast_path(parked, lang, word, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    ans = gates.resolve_all(word, brief=None)
    assert ans and ans.gate == "task" and ans.yes and parked


def test_the_waiting_line_exists_in_both_languages():
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[4]
    for lang in ("es", "en"):
        line = json.loads((root / f"i18n/genesis/{lang}/voice.json").read_text(encoding="utf-8"))["errand_still_waiting"]
        assert "{request}" in line, lang


@pytest.mark.parametrize("lang,said", [("es", "sí, y cierra el vídeo"), ("en", "yes, and close the video")])
def test_the_turn_says_the_errand_still_waits(parked, lang, said, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    heard: list = []
    assert not gates.resolve_all(said, brief=_answered_none(), say=heard.append)
    assert heard and "abre el que sea mejor oferta" in heard[0], heard
    heard.clear()
    gates.resolve_all("sí" if lang == "es" else "yes", brief=None, say=heard.append)
    assert not heard, "an answer that answered says nothing of the kind"
