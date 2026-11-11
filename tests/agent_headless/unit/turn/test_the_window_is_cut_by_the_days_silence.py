"""The dialog window is cut by the same silence as the day, and what was said is in it as it was said (V2-878 §3 (b)(c),
node 2.1677).

  · The window kept its last ten messages whatever their age: after a night, last evening's exchange was still «the
    conversation» the model answered inside. Now ONE reader (`dialog.live_slice`) cuts it: the last ten AND nothing
    from before the last silence of `LIVE_GAP_MIN` — the silence that already cuts the day's episodes.
  · A reply he cut (barge-in) vanished from the window; the next turn read no trace of it and the model repeated it
    whole. It now enters marked `cut`, and the model reads it ending in «…».
  · A line said out of turn reached the window only; the conversation record (`conv`) never had it. It is written
    there now, with the notice it came from (`meta.notice`) — and as OURS: the recall's repeat finder never reads it
    as words he said.
  · Words a worker handed back never folded into that errand again, even after it ended: the hand-back now ends with
    the row that handed it back.

Disarms (seen red): `live_slice` back to the count alone; the cut reply not appended; `_to_conversation` a no-op;
the repeat finder reading a row's text when his words are empty; the hand-back kept past its row.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from nucleo.flash import dialog

GAP = 20 * 60


def _msg(role, text, ts):
    return {"role": role, "content": text, "ts": ts}


def test_a_window_with_a_silence_starts_after_it():
    now = time.time()
    w = [_msg("user", "busca un hotel en Roma", now - GAP - 120), _msg("assistant", "Busco.", now - GAP - 110),
         _msg("user", "¿y el vuelo?", now - 30), _msg("assistant", "Lo miro.", now - 20)]
    dialog.live_slice(w, 10)
    assert [m["content"] for m in w] == ["¿y el vuelo?", "Lo miro."]


def test_a_silence_up_to_now_leaves_nothing_live():
    now = time.time()
    w = [_msg("user", "hola", now - GAP - 60), _msg("assistant", "Hola.", now - GAP - 50)]
    dialog.live_slice(w, 10)
    assert w == []


def test_without_a_silence_the_count_still_cuts_and_new_messages_are_stamped():
    now = time.time()
    w = [_msg("user", f"u{i}", now - 100 + i) for i in range(12)] + [{"role": "assistant", "content": "a"}]
    dialog.live_slice(w, 10)
    assert len(w) == 10 and w[-1]["content"] == "a" and w[-1]["ts"] >= now


def test_the_model_reads_role_and_words_only_and_a_cut_reply_ends_open():
    w = [_msg("user", "cuéntame el plan", 1.0), {"role": "assistant", "content": "Primero vamos a", "cut": True, "ts": 2.0}]
    assert dialog.prune_window(w) == [{"role": "user", "content": "cuéntame el plan"},
                                      {"role": "assistant", "content": "Primero vamos a …"}]


def test_the_cut_turn_keeps_what_was_said_marked():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[4] / "nucleo/turn/pipeline_stream.py").read_text(encoding="utf-8")
    assert '"cut": True' in src and "live_slice(brain._window" in src


@pytest.fixture
def captured(monkeypatch):
    from memory import api as memory
    rows: list = []
    monkeypatch.setattr(memory, "write", lambda text, **kw: rows.append((text, kw)) or 1)
    return rows


def test_a_line_said_out_of_turn_reaches_the_conversation_record(captured):
    from voice import proactive
    proactive._to_conversation("Ya tienes la lista de hoteles.", "job:7:1")
    (text, kw), = captured
    assert kw["kind"] == "conv" and kw["meta"]["notice"] == "job:7:1" and kw["meta"]["a"].startswith("Ya tienes")
    assert kw["meta"]["u"] == "", "an out-of-turn line is ours: nothing he said"


def test_a_line_of_ours_is_never_his_repeat():
    import json
    from memory import history
    q = "busca un monitor de veintisiete pulgadas para jugar"
    ours = {"id": 1, "created": 1.0, "text": q, "meta": json.dumps({"source": "conv", "u": "", "a": q, "notice": "job:7:1"})}
    his = {"id": 2, "created": 2.0, "text": q, "meta": json.dumps({"source": "conv", "u": q, "a": "Lo busco."})}
    assert history._oldest_repeat([ours, his], history._words(q), None) != 1, "our own line was read as his words"
    old = {"id": 3, "created": 0.5, "text": q, "meta": ""}           # a row from before the structured fields
    assert history._oldest_repeat([old, his], history._words(q), None) == 3


def test_a_hand_back_ends_with_the_row_that_handed_it_back():
    from nucleo.turn import flow_of
    flow_of._NOT_MINE.clear()
    words = "reserva mesa para cuatro el viernes"
    flow_of.not_mine(words, "w7")
    assert flow_of._was_handed_back(words, {"id": "w7", "request": "busca monitor"})
    assert not flow_of._was_handed_back(words, {"id": "w7", "request": "busca monitor", "ended": True})
    assert not flow_of._NOT_MINE, "the hand-back outlived its row"
