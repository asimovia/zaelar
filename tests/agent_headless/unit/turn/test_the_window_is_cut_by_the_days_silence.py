"""The dialog window is cut by the same silence as the day, and what was said is in it as it was said (V2-878 §3 (b)(c),
node 2.1676).

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


import pytest


GAP = 20 * 60


def _msg(role, text, ts):
    return {"role": role, "content": text, "ts": ts}


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
