"""Privacy of the P2 fixtures (node 13.21): a recorded session enters the public repo as tokens and times only.

Every string in `fixtures/sessions/*.jsonl` is a token (`w0001`), a run of tokens, or one of the converter's own
structural values (signal kinds, edges, sources, device and client ids); no name, number-as-word, account, session id
or clock time of a real session. Times are relative to the session's first event.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "sessions"
TOKENS = re.compile(r"^w\d{4}( w\d{4})*$")
STRUCTURE = re.compile(r"^(WordSpan|VadEdge|EotHint|Watermark|PlaybackState|TypedSubmit|Control|AgentLine|"
                       r"rise|fall|flux|eager|resumed|end|stop|d\d+|c\d+)$")
KEYS = {"sig", "stream", "seq", "revision", "final", "words", "window", "endpoint", "edge", "t_ms", "echo_safe",
        "source", "kind", "prob", "processed_through_ms", "speaking", "client_id", "text", "op"}


def _strings(v):
    if isinstance(v, str):
        yield v
    elif isinstance(v, list):
        for x in v:
            yield from _strings(x)
    elif isinstance(v, dict):
        for x in v.values():
            yield from _strings(x)


def test_every_string_of_every_fixture_is_a_token_or_structure():
    files = sorted(FIX.glob("*.jsonl"))
    assert len(files) >= 2
    for f in files:
        for n, line in enumerate(f.read_text().splitlines(), start=1):
            row = json.loads(line)
            assert set(row) <= KEYS, (f.name, n, set(row) - KEYS)
            bad = [s for s in _strings(row) if s and not (TOKENS.match(s) or STRUCTURE.match(s))]
            assert not bad, (f.name, n, bad)


def test_times_are_relative_and_no_real_id_is_kept():
    for f in sorted(FIX.glob("*.jsonl")):
        text = f.read_text()
        times = [r.get("t_ms", r.get("processed_through_ms", 0)) for r in map(json.loads, text.splitlines())]
        assert max(times) < 24 * 3600 * 1000, f"{f.name}: a clock time, not a time since the session began"
        assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-", text), f"{f.name}: an id"
    labels = (FIX / "labels.json").read_text()
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-", labels)
