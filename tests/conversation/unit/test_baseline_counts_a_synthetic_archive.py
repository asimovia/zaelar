"""F0 tools (node 13.25): the baseline counts a synthetic archive right, and the converter writes tokens only.

The archive below is invented, in the exported-row shape of today's observer: one voice sentence cut by an eager
hint that resumed, a second final in the same run (a sentence split in two), a cancelled turn, a reply, a final the
model never saw, a stop, host stalls, a nudge, a typed line, a forced source and a dropped fragment. Every number the
baseline prints is asserted, and the converter's whole output is searched for every word of the invented speech.
"""
from __future__ import annotations

import csv
import json

from tests.conversation.benchmarks import baseline
from tests.conversation.tools import archive, export_envelopes

T0 = 1_800_000_000_000
DEV = "desktop:0000aaaa"
SPEECH = ("Andrew", "viernes", "NVIDIA", "mañana", "Friday", "acciones")


def _row(dt: int, kind: str, label: str, **payload) -> dict:
    body = {"t_ms": T0 + dt, "kind": kind, "label": label, "origin_dev": DEV, **payload}
    return {"ts_ms": T0 + dt, "kind": kind, "label": label, "corr_id": payload.get("trace"),
            "payload": json.dumps(body)}


def _interim(dt: int, text: str) -> dict:
    row = _row(dt, "interim", "…", text=text, role="user")
    row["payload"] = json.dumps({k: v for k, v in json.loads(row["payload"]).items() if k != "t_ms"})
    return row   # today's partials carry no t_ms of their own: the row's stamp is the time


def _archive() -> list[dict]:
    a, b, c = "Andrew viernes", "Andrew viernes NVIDIA", "mañana Friday acciones"
    return [
        _row(0, "vad", "🎤 voz detectada (VAD)", edge="on"),
        _interim(200, a),
        _row(400, "vad", "⚡ eager", detector="stt-eager", text=a),
        _interim(700, b),                                                   # new words after the hint → resumed
        _row(900, "vad", "⚡ eager", detector="stt-eager", text=b),
        _interim(950, b),                                                   # same words → not a resumption
        _row(1000, "transcript", "🗣", text=b, role="user"),
        _row(1005, "vad", "… fin de voz", edge="off"),
        _row(1100, "brain", "jev turn-brief (12q)"),
        _row(1150, "brain", "jev read request_type"),
        _row(1200, "brain", "jev read canvas"),
        _row(1300, "brain", "⚡ Nucleo(flash): prompt", text=b, trace="T1"),
        _row(1500, "transcript", "🗣", text="Friday", role="user"),          # second final in the same run → split
        _row(1600, "brain", "✂️ cancelled", cut_after_ms=300, trace="T1"),
        _row(1700, "brain", "⚡ Nucleo(flash): prompt", text="Friday", trace="T2"),
        _row(2000, "bot_speech", "speaking", speaking=True),
        _row(2000, "perf", "⏱ primer audio 1000 ms desde que dejó de hablar", onset_ms=T0 + 1000),
        _row(2100, "transcript", "zaelar", text="ok", role="assistant"),
        _row(3000, "bot_speech", "idle", speaking=False),
        _row(5000, "transcript", "🗣", text=c, role="user"),                 # no prompt in 10 s
        _row(6000, "ambient", "✋ hard", reason="hard_interrupt", text="para"),
        _row(6250, "bot_speech", "idle", speaking=False),
        _row(7000, "homeostasis", "held", lag_s=0.3),
        _row(7010, "homeostasis", "held", lag_s=0.05),
        _row(7020, "homeostasis", "held", lag_s=1.2),
        _row(7100, "brain", "🔁 break-loop: nudge"),
        _row(8000, "transcript", "text-injected chat", text="Andrew mañana", role="user"),
        _row(8100, "rail", "🛤 upsert"),
        _row(8200, "brain", "🧩 dropped", dropped_reply=True),
    ]


def _write(tmp_path) -> object:
    path = tmp_path / "session-under-test.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in _archive()) + "\n", encoding="utf-8")
    return path


def test_the_baseline_counts_every_metric_of_the_synthetic_archive(tmp_path):
    _write(tmp_path)
    report, mapping = baseline.run(tmp_path)
    t = report["totals"]
    assert report["sessions"] == 1 and mapping == {"s1": "session-under-test"}
    assert (t["eager"], t["resumed"], t["finals"], t["split_sentences"]) == (2, 1, 3, 1)
    assert (t["turns_cancelled"], t["prompts"], t["deciders"], t["deciders_per_turn"]) == (1, 2, 3, 1.5)
    assert t["final_to_prompt_ms"]["n"] == 2 and t["final_to_prompt_ms"]["max"] == 300
    assert t["final_to_prompt_ms"]["p50"] == 200 and t["not_reached_10s"] == 1
    assert t["first_audio_ms"]["p50"] == 1000.0 and t["stop_to_silence_ms"]["p50"] == 250
    assert (t["loop_stalls_100"], t["loop_stalls_500"], t["loop_stall_total_ms"]) == (2, 1, 1550)
    assert (t["loop_nudges"], t["typed"], t["forced_source"], t["dropped"]) == (1, 1, 1, 1)


def test_the_baseline_report_carries_no_text_and_no_session_id(tmp_path):
    _write(tmp_path)
    report, _ = baseline.run(tmp_path)
    blob = json.dumps(report)
    assert "session-under-test" not in blob
    assert not [w for w in SPEECH if w.lower() in blob.lower()]


def test_the_converter_writes_tokens_times_and_proposed_labels_only(tmp_path):
    src = _write(tmp_path)
    out = tmp_path / "out"
    assert export_envelopes.main([str(src), "--out", str(out), "--name", "s1", "--pauses"]) == 0
    written = "".join(p.read_text(encoding="utf-8") for p in sorted(out.iterdir()))
    assert not [w for w in SPEECH if w.lower() in written.lower()], "a word of the speech reached the output"
    assert DEV not in written and "session-under-test" not in written
    signals = [json.loads(line) for line in (out / "s1.jsonl").read_text().splitlines()]
    kinds = [s["sig"] for s in signals]
    for want in ("WordSpan", "VadEdge", "EotHint", "Watermark", "PlaybackState", "TypedSubmit", "Control",
                 "AgentLine"):
        assert want in kinds, want
    hints = [s["kind"] for s in signals if s["sig"] == "EotHint"]
    assert hints.count("eager") == 2 and hints.count("resumed") == 1 and hints.count("end") == 3
    finals = [s for s in signals if s["sig"] == "WordSpan" and s["final"]]
    assert [len(f["words"]) for f in finals] == [3, 1, 3]
    assert all(w[0].startswith("w") and w[0][1:].isdigit() for f in finals for w in f["words"])
    labels = json.loads((out / "s1.labels.json").read_text())
    assert labels["interventions"] == [[0, 4], [4, 7]] and labels["reviewed"] is False
    rows = list(csv.DictReader((out / "s1.pauses.csv").open()))
    assert [r["source"] for r in rows] == ["eager", "eager"]
    assert [r["label"] for r in rows] == ["continues", "continues"]


def test_the_same_word_is_the_same_token_and_punctuation_is_dropped():
    toks = export_envelopes.Tokens()
    assert toks.of("Andrew, viernes.") == ["w0001", "w0002"]
    assert toks.of("viernes andrew") == ["w0002", "w0001"]


def test_both_archive_shapes_read_the_same_event(tmp_path):
    row = _row(5, "vad", "x", edge="on")
    local = {"i": 1, "t_ms": T0 + 5, "kind": "vad", "label": "x", "edge": "on"}
    p1, p2 = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    p1.write_text(json.dumps(row) + "\n")
    p2.write_text(json.dumps(local) + "\n")
    e1, e2 = archive.read_file(p1)[0], archive.read_file(p2)[0]
    assert (e1.t_ms, e1.kind, e1.payload["edge"]) == (e2.t_ms, e2.kind, e2.payload["edge"])
