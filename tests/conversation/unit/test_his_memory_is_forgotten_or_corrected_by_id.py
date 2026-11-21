"""His memory is forgotten or corrected by the pill's id, never by matching his words (node 13.140, E7d-4, R-4).

The model reads the pills with `recall` (each with its id) and names them: forgetting is soft — gone from recall, kept
for audit, undoable by id, a pinned pill untouched; correcting writes the new text through the memory's one writer
with the old pill superseded, its kind, level and slot kept. An id nobody holds is a failure the model sees.
"""
from __future__ import annotations

from memory import api as memory
from nucleo.conversation_host import acts_memory


def test_forgetting_by_id_is_soft_undoable_and_spares_a_pinned_pill():
    a = memory.write_now("w_works at w_acme", kind="fact", level="mid")
    b = memory.write_now("w_lives in w_town", kind="fact", level="mid", pinned=True)
    got = acts_memory.run("forget", {"ids": [a, b]})
    assert got.status == "ok" and got.data["forgotten"] == [a]
    assert memory.pill(a) is None and memory.pill(b) is not None
    assert memory.unforget_ids([a]) == [a] and memory.pill(a) is not None
    assert acts_memory.run("forget", {"ids": [987654]}).status == "failed"


def test_correcting_by_id_writes_through_the_one_writer_and_supersedes_the_old(monkeypatch):
    a = memory.write_now("w_lives in w_old_town", kind="fact", level="long", slot="operator.location")
    written = []
    monkeypatch.setattr(memory, "write", lambda text, **kw: written.append((text, kw)))
    got = acts_memory.run("correct", {"id": a, "text": "w_lives in w_new_town"})
    assert got.status == "ok" and got.data["corrected"] == a
    text, kw = written[0]
    assert text == "w_lives in w_new_town" and kw["supersedes"] == [a]
    assert (kw["kind"], kw["level"], kw["slot"]) == ("fact", "long", "operator.location")
    assert acts_memory.run("correct", {"id": 987654, "text": "w_x"}).status == "failed" and len(written) == 1
