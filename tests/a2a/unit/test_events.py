"""T590 · observability: OPS is the one table, the doc mirrors it, rows never leak a DID, hash or body."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from a2a import events

DOC = Path(__file__).resolve().parents[3] / ".meshkore" / "docs" / "modules" / "zaelar-a2a.md"


def test_the_doc_table_is_OPS():
    text = DOC.read_text()
    block = text.split("<!-- OPS:BEGIN -->")[1].split("<!-- OPS:END -->")[0]
    doc_ops = {}
    for line in block.splitlines():
        m = re.match(r"\|\s*`([a-z_]+)`\s*\|\s*([^|]*)\|", line)
        if m:
            doc_ops[m.group(1)] = tuple(re.findall(r"`([a-z_]+)`", m.group(2)))
    assert doc_ops == events.OPS


def test_an_undeclared_op_or_field_is_a_programming_error():
    with pytest.raises(KeyError):
        events.emit("made_up")
    with pytest.raises(KeyError):
        events.emit("msg", body="x")


def test_rows_carry_8_chars_of_a_peer_and_scrub_outside_text(rows):
    peer = "did:key:" + "Q" * 43 + "="
    r = events.emit("msg", peer=peer, dir="in", len=3, shown="card",
                    excerpt="call me " + "ab" * 32 + " from " + peer + " " + "x" * 500)
    assert r["peer"] == "Q" * 8
    assert peer not in str(r) and "ab" * 32 not in str(r)
    assert len(r["excerpt"]) <= events.EXCERPT


def test_a_sink_that_raises_never_breaks_the_caller():
    def bad(row):
        raise RuntimeError("sink down")
    events.add_sink(bad)
    try:
        assert events.emit("beat", pulls=1, empty=1, avg_ms=0, max_ms=0)["op"] == "beat"
    finally:
        events.remove_sink(bad)
