"""Export audio scenarios run against the real Flux as TOKEN fixtures for level 1 (no audio, no words).

    ./.venv/bin/python -m tests.conversation.benchmarks.audio.export_fixtures --report <report.json> \
        [--out tests/conversation/fixtures/audio3a] [ids…]

For each scenario it writes `<id>.jsonl` — the ear's signals as the speech adapter would deliver them (Flux's
`TurnInfo` → `WordSpan` · `EotHint` · `Watermark`, the VAD → `VadEdge` per v3.1 §1.6 bis E1), in ARRIVAL order — and
one `labels.json` with the truth of every scenario: who spoke when (role only), which segments form each of the
person's turns, where each turn truly ends, the provider's own turns, and what the manager measured on it.

Every word becomes `wNNNN`, stable within a scenario across the heard words and the labels (the same normalised word,
the same token), so a test can tell which heard tokens are the person's without any text. Times are ms from the
start of the stream; nothing of the voices or the text leaves the machine that ran the bench.
"""
from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path

from tests.conversation.benchmarks.audio import flux as F
from tests.conversation.benchmarks.audio.probe import OUT

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "audio3a"


def _norm(word: str) -> str:
    t = unicodedata.normalize("NFKD", str(word).lower())
    return "".join(ch for ch in t if ch.isalnum())


class Tokens:
    def __init__(self) -> None:
        self.map: dict[str, str] = {}

    def __call__(self, word: str) -> str:
        key = _norm(word) or "_"
        if key not in self.map:
            self.map[key] = f"w{len(self.map) + 1:04d}"
        return self.map[key]


def export(sid: str, flow: dict, out: Path) -> dict:
    labels = json.loads((OUT / "scenarios" / f"{sid}.labels.json").read_text(encoding="utf-8"))
    raw = F.load_raw(OUT / "flux" / f"{sid}.raw.jsonl")
    tok = Tokens()
    segments = []
    for seg in sorted(labels["segments"], key=lambda s: s["start_ms"]):
        segments.append({"i": seg["i"], "role": seg["role"], "turn": seg["turn"], "start_ms": seg["start_ms"],
                         "end_ms": seg["end_ms"], "cut": seg["cut"],
                         "words": [[tok(w), a, b] for w, a, b in seg["words"]] if seg["words"]
                         else [[tok(w), None, None] for w in seg["text"].split()] if seg["text"] else []})
    sig = F.signals(raw, [tuple(e) for e in flow["vad_edges"]])
    lines = []
    for s in sig:
        s = dict(s)
        if s["sig"] == "WordSpan":
            s["words"] = [[tok(w), a, b, c] for w, a, b, c in s["words"]]
        lines.append(json.dumps(s, sort_keys=True))
    (out / f"{sid}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    provider = [{"seq": t["seq"], "end_arrived_ms": t["end_ms"], "eot_prob": t["eot_prob"], "tokens": len(t["words"]),
                 "t0_ms": t["words"][0][1] if t["words"] else None, "t1_ms": t["words"][-1][2] if t["words"] else None}
                for t in F.flux_turns(raw)]
    b, mg = flow["batch"], flow["manager"]
    return {"description": labels["description"], "duration_ms": labels["duration_ms"], "segments": segments,
            "turns": [{k: t[k] for k in ("turn", "start_ms", "end_ms", "kind", "segments")} for t in labels["turns"]],
            "provider_turns": provider,
            "vad": {"edges": "e1", "quiet_ms": F.VAD_QUIET_MS, "on": F.VAD_ON, "off": F.VAD_OFF},
            "measured": {"batch_units": b["units"], "false_cuts": b["false_cuts"],
                         "spoke_over_user": mg["spoke_over_user"], "unclosed_turns": b["unclosed_turns"],
                         "eot_delay_ms": b["eot_delay_ms"], "exposure": b["exposure"],
                         "runs": {k: mg[k] for k in ("started", "held", "superseded")}}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").partition("\n")[0])
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=FIXTURES)
    ap.add_argument("--code", default="", help="the engine commit the measurement ran on, recorded in labels.json")
    ap.add_argument("ids", nargs="*")
    args = ap.parse_args(argv)
    report = json.loads(args.report.read_text(encoding="utf-8"))
    ids = args.ids or [i for i, f in report["flows"].items() if f["stratum"] == "hand"]
    args.out.mkdir(parents=True, exist_ok=True)
    labels = {"format": 1, "flux_config": report["flux_config"], "measured_on": args.code or None,
              "scenarios": {sid: export(sid, report["flows"][sid], args.out) for sid in ids}}
    (args.out / "labels.json").write_text(json.dumps(labels, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(args.out), "scenarios": ids}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
