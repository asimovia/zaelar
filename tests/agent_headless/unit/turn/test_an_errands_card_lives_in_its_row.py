"""An errand's CARD lives in its durable row (V2-878 §1, nodes 2.1671 and 2.1672).

His commissioning sentence (`heard`) lived only in RAM — on the dispatcher's record — and was `""` for every errand
when one sentence commissioned several: a restart or a suspend forgot what he had asked, the flow judge's pool
(`named_errand.known`) never carried it, and the second and third errands of a sentence were born without his words,
without the turn's reading, end state or consent class. The card is now on the row (`progress.card`: heard, part,
verb, last_mention_ts; its state is the row's own column): the 15-second status beat keeps it, a restart reads it back,
the pool and the rehydrate read it from there, and every errand of a sentence carries it.
"""
from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace

import pytest

from memory import db as memdb
from nucleo import dispatch
from nucleo.acts import errand
from nucleo.circuit import ledger
from nucleo.pulse import rehydrate
from nucleo.request import model as request_model
from nucleo.turn import brief as tb
from nucleo.turn import named_errand
from nucleo.turn import pipeline_errands as PE
from nucleo.workers.session_record import SessionRecord

SAID = {"es": "búscame un coche usado de menos de veinte mil, que sea diésel",
        "en": "find me a used car under twenty thousand, diesel only",
        "ca": "busca'm un cotxe de segona mà de menys de vint mil, que sigui dièsel"}
THREE = {"es": ("búscame un monitor de 27 pulgadas, hazme un informe del mercado y móntame un juego de plataformas",
                ["busca un monitor de 27 pulgadas", "haz un informe del mercado", "monta un juego de plataformas"]),
         "en": ("find me a 27 inch monitor, write me a market report and build me a platform game",
                ["find a 27 inch monitor", "write a market report", "build a platform game"]),
         "ca": ("busca'm un monitor de 27 polzades, fes-me un informe del mercat i munta'm un joc de plataformes",
                ["busca un monitor de 27 polzades", "fes un informe del mercat", "munta un joc de plataformes"])}


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    memdb.reset_db()
    monkeypatch.setattr(dispatch, "_SESSIONS", {})
    yield
    request_model._TURN.set(None)   # the turn this test began ends with it: a later file's question lands on ITS row
    memdb.reset_db()


@pytest.mark.parametrize("lang", ["es", "en", "ca"])
def test_an_errand_born_with_his_words_keeps_them_across_a_restart_and_the_pool_reads_them(db, lang):
    said = SAID[lang]
    uid = ledger.born("k1", said, {"said": said, "trace": "t1"})
    rec = SessionRecord(task_id="k1", goal=said[:200], uid=uid, heard=said)
    rec.status = "running"
    ledger.opened(rec, {"heard": said, "said": said})
    ledger.status_written({"uid": uid, "phase": "comparing", "done": 1, "total": 3, "note": "two found"})
    assert ledger.card(uid)["heard"] == said, "the status beat wiped the errand's card"

    memdb.reset_db()                                     # a restart: nothing in RAM, the row read again
    dispatch._SESSIONS.clear()
    card = ledger.card(uid)
    assert card["heard"] == said and card["verb"] == "new" and card["state"] in ("running", "pending")
    assert card["last_mention_ts"] > 0
    assert rehydrate.heard_of(uid) == {"said": said, "heard": said}, "a resumed errand lost his sentence"

    dispatch._SESSIONS["k1"] = rec                        # the pool (flow judge, Flash, the brief) reads the card
    (entry,) = [e for e in named_errand.known() if e["id"] == "k1"]
    assert entry["heard"] == said and entry["state"] == card["state"] and entry["last_mention_ts"] == card["last_mention_ts"]

    ledger.card_written(uid, last_mention_ts=1)
    named_errand.mentioned("k1")
    assert ledger.card(uid)["last_mention_ts"] > 1, "naming the errand again did not stamp it"
    ledger.card_written(uid, heard="something else")
    assert ledger.card(uid)["heard"] == said, "his first words on an errand were overwritten"


def _brief() -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t", "result": {
        "_call_id": "t", tb.ESCALATE_KEY: {"choice": "escalate", "confidence": 0.9, "probs": {}},
        errand.CLASS_KEY: {"choice": "reversible", "confidence": 0.9, "probs": {}}}}


def _launch(text: str, reqs: list[str], monkeypatch) -> list[tuple[str, dict]]:
    started = []
    esc = SimpleNamespace(
        escalate_to_slowbrain=lambda req, context=None: started.append((req, dict(context or {}))) or True,
        done_when_from_brief=lambda _b: None, class_verdict=errand.class_verdict)
    router = SimpleNamespace(create_widget_request=lambda _t: "", looks_like_create_widget=lambda _r: False)
    from nucleo import surfaces
    from nucleo.request import ending
    motor = SimpleNamespace(_surfaces_mod=surfaces, _similar_pending=lambda *_a: False)
    for mod, name, fn in ((PE._his_spec, "carry", lambda *_a, **_k: None), (PE._sbe, "routed", lambda *_a, **_k: None),
                          (PE._sbe, "each_line", lambda *_a, **_k: ""), (PE._reply, "say_started", lambda *_a, **_k: None),
                          (ending, "close_turn", lambda *_a, **_k: None), (ending, "only_held", lambda: False)):
        monkeypatch.setattr(mod, name, fn)
    request_model.begin(text, trace="t")
    req = {"v": reqs[0], "more": list(reqs[1:]), "surface": {}, "routed": True}
    asyncio.run(PE.launch_the_errands(
        motor=motor, send=lambda _s: None, speech=SimpleNamespace(sanitize=lambda s, **_k: s), emit=lambda *a, **k: None,
        brain=SimpleNamespace(), _brief=_brief(), _op_text=text, _escalate_mod=esc, _prev_pending=[], _router=router,
        _did_act=True, _acted_elsewhere=True, acted={"widget": False}, escalate_req=req, spoken_text="",
        worker_acted={"v": None}))
    return started


@pytest.mark.parametrize("lang", ["es", "en", "ca"])
def test_one_sentence_three_errands_three_cards_with_his_words_and_the_reading(db, monkeypatch, lang):
    text, reqs = THREE[lang]
    started = _launch(text, reqs, monkeypatch)
    assert [r for r, _c in started] == reqs
    for n, (_req, ctx) in enumerate(started):
        assert ctx["said"] == text, f"errand {n} was born without his sentence"
        assert ctx["part"] == n, f"errand {n} does not say which part of the sentence it is"
        assert ctx["reading"] and ctx["errand_class"]["choice"] == "reversible", f"errand {n} lost the turn's reading"
        assert not ctx.get("heard"), "a sheet of one of several errands would judge rows by the other two's words"
    cards = [ledger.card(ledger.born(f"k{n}", req, ctx)) for n, (req, ctx) in enumerate(started)]
    assert [c["heard"] for c in cards] == [text] * 3 and [c["part"] for c in cards] == [0, 1, 2]
