"""Turn a recorded session into ear signals with their times, every word replaced by a token. For P2 and F0.

    ./.venv/bin/python -m tests.conversation.tools.export_envelopes <session.jsonl> --out <dir> [--name s1]
        [--pauses]

Writes, under `<dir>`:
  <name>.jsonl         one ear signal per line, in time order, in the shapes of the conversation ear (`WordSpan`,
                       `VadEdge`, `EotHint`, `Watermark`, `PlaybackState`, `TypedSubmit`, `Control`, `AgentLine`)
  <name>.labels.json   the PROPOSED truth: which final tokens form each intervention of the person (one intervention =
                       what they said between two agent lines), as `[start, end)` token indices — to be reviewed by a person
                       against the original and saved as a list of cuts
  <name>.counts.json   how many of each signal, with no text
  <name>.pauses.csv    (with `--pauses`) every pause in the middle of the person's speech — an eager hint or a VAD gap of
                       300 ms or more inside an intervention — with the proposed label `continues` / `ended`; the
                       `annotator` column is for the person who checks it

Anonymised in the converter itself: each word becomes `wNNNN`, stable within the session (the same word, the same
token), punctuation dropped; times are made relative to the session's first event, so no clock time of a real
session is kept. Times, revisions, eager/resumed hints, channels and controls are kept; a stop is a field,
never a word. Devices become `d1, d2, …`. Nothing of the original text, names or ids reaches the output.

Today's archive has no per-word times: the words of a partial or a final are spread evenly over the window from the
previous final (or the voice rise) to the event, and `conf` is 1.0. Flux gives per-word times (see the adapter doc);
the P2 fixtures are about ORDER and grouping, not about the milliseconds inside a sentence.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

from tests.conversation.tools import archive, today

PAUSE_GAP_MS = 300


class Tokens:
    """Word → `wNNNN`, stable within one session."""

    def __init__(self) -> None:
        self._map: dict[str, str] = {}

    def of(self, text: str) -> list[str]:
        out = []
        for raw in text.split():
            word = "".join(ch for ch in raw.lower() if ch.isalnum())
            if not word:
                continue
            if word not in self._map:
                self._map[word] = f"w{len(self._map) + 1:04d}"
            out.append(self._map[word])
        return out


def _spread(tokens: list[str], t0: int, t1: int) -> list[list]:
    if not tokens:
        return []
    t1 = max(t1, t0 + len(tokens))
    step = (t1 - t0) / len(tokens)
    return [[tok, int(t0 + i * step), int(t0 + (i + 1) * step), 1.0] for i, tok in enumerate(tokens)]


def convert(events: list[archive.Event]) -> tuple[list[dict], dict, list[dict]]:
    toks, devices = Tokens(), {}
    signals: list[dict] = []
    seq, revision, window_start = 1, 0, None
    eager_tokens: list[str] | None = None
    final_index, interventions, run_start = 0, [], None
    last_final_t = None
    pauses: list[dict] = []
    last_fall: int | None = None

    seen = next((str(e.payload.get("origin_dev") or e.payload.get("dev")) for e in events
                 if e.payload.get("origin_dev") or e.payload.get("dev")), "local")
    last = {"raw": seen}

    def dev(ev: archive.Event) -> str:
        """The device an event came from; an event that does not say (today's partials) is the last one's."""
        raw = ev.payload.get("origin_dev") or ev.payload.get("dev")
        if raw:
            last["raw"] = str(raw)
        return devices.setdefault(last["raw"], f"d{len(devices) + 1}")

    def close_run() -> None:
        nonlocal run_start
        if run_start is not None and final_index > run_start:
            interventions.append([run_start, final_index])
        run_start = None

    for ev in events:
        sig = today.classify(ev)
        t = ev.t_ms
        if sig in ("vad_on", "vad_off"):
            d = dev(ev)
            signals.append({"sig": "VadEdge", "endpoint": d, "edge": "rise" if sig == "vad_on" else "fall",
                            "t_ms": t, "echo_safe": not ev.payload.get("over_agent", False)})
            if sig == "vad_on":
                if last_fall is not None and run_start is not None and t - last_fall >= PAUSE_GAP_MS:
                    pauses.append({"t_ms": last_fall, "source": "vad_gap", "gap_ms": t - last_fall})
                window_start = window_start or t
            else:
                last_fall = t
        elif sig == "user_interim":
            words = toks.of(ev.text)
            if eager_tokens is not None and words != eager_tokens:
                signals.append({"sig": "EotHint", "stream": dev(ev), "source": "flux", "kind": "resumed",
                                "prob": None, "t_ms": t})
                eager_tokens = None
            revision += 1
            t0 = window_start or last_final_t or t
            signals.append({"sig": "WordSpan", "stream": dev(ev), "seq": seq, "revision": revision, "final": False,
                            "words": _spread(words, t0, t), "window": [t0, t]})
        elif sig == "eager":
            eager_tokens = toks.of(ev.text)
            signals.append({"sig": "EotHint", "stream": dev(ev), "source": "flux", "kind": "eager", "prob": None,
                            "t_ms": t})
            if run_start is not None or eager_tokens:
                pauses.append({"t_ms": t, "source": "eager", "gap_ms": None})
        elif sig == "user_final":
            words = toks.of(ev.text)
            revision += 1
            t0 = window_start or last_final_t or t
            if run_start is None:
                run_start = final_index
            signals.append({"sig": "WordSpan", "stream": dev(ev), "seq": seq, "revision": revision, "final": True,
                            "words": _spread(words, t0, t), "window": [t0, t]})
            signals.append({"sig": "EotHint", "stream": dev(ev), "source": "flux", "kind": "end", "prob": None,
                            "t_ms": t})
            signals.append({"sig": "Watermark", "stream": dev(ev), "processed_through_ms": t})
            final_index += len(words)
            seq, revision, window_start, eager_tokens, last_final_t = seq + 1, 0, None, None, t
        elif sig == "typed":
            close_run()
            signals.append({"sig": "TypedSubmit", "endpoint": dev(ev), "client_id": f"c{len(signals) + 1}",
                            "text": " ".join(toks.of(ev.text)), "t_ms": t})
        elif sig == "stop_attended":
            signals.append({"sig": "Control", "op": "stop", "endpoint": dev(ev), "t_ms": t})
        elif sig in ("agent_speaking", "agent_idle"):
            signals.append({"sig": "PlaybackState", "endpoint": dev(ev), "speaking": sig == "agent_speaking",
                            "t_ms": t})
            if sig == "agent_speaking":
                close_run()
        elif sig == "agent_line":
            signals.append({"sig": "AgentLine", "t_ms": t})
            close_run()
    close_run()
    labels = {"proposed_by": "converter", "reviewed": False, "tokens": final_index,
              "interventions": interventions}
    return signals, labels, _label_pauses(pauses, interventions, signals)


def _label_pauses(pauses: list[dict], interventions: list[list[int]], signals: list[dict]) -> list[dict]:
    """`continues` when more final words of theirs land after the pause inside the same proposed intervention."""
    finals = [(s["window"][1], len(s["words"])) for s in signals if s["sig"] == "WordSpan" and s["final"]]
    cum, starts = 0, []
    for t, n in finals:
        starts.append((t, cum))
        cum += n
    out = []
    for i, p in enumerate(sorted(pauses, key=lambda p: p["t_ms"]), start=1):
        before = [idx for t, idx in starts if t <= p["t_ms"]]
        after = [idx for t, idx in starts if t > p["t_ms"]]
        here = before[-1] if before else 0
        iv = next((iv for iv in interventions if iv[0] <= here < iv[1]), None)
        cont = bool(after and iv and iv[0] <= after[0] < iv[1])
        out.append({"pause_id": f"p{i:04d}", "t_ms": p["t_ms"], "source": p["source"],
                    "gap_ms": "" if p["gap_ms"] is None else p["gap_ms"],
                    "label": "continues" if cont else "ended", "annotator": ""})
    return out


def relative(signals: list[dict], pauses: list[dict]) -> tuple[list[dict], list[dict]]:
    """Times from 0 at the session's first event: the order and the gaps are kept, the clock time is not."""
    def first(s: dict) -> int | None:
        return s.get("t_ms", s.get("processed_through_ms", (s.get("window") or [None])[0]))
    t0 = min((t for s in signals if (t := first(s)) is not None), default=0)

    def shift(s: dict) -> dict:
        s = dict(s)
        for k in ("t_ms", "processed_through_ms"):
            if k in s:
                s[k] -= t0
        if "window" in s:
            s["window"] = [s["window"][0] - t0, s["window"][1] - t0]
        if "words" in s:
            s["words"] = [[w, a - t0, b - t0, c] for w, a, b, c in s["words"]]
        return s
    return [shift(s) for s in signals], [{**p, "t_ms": p["t_ms"] - t0} for p in pauses]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("session", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--name", default="s1", help="file name for the output (never the real session id)")
    ap.add_argument("--pauses", action="store_true")
    args = ap.parse_args(argv)
    signals, labels, pauses = convert(archive.read_file(args.session))
    signals, pauses = relative(signals, pauses)
    args.out.mkdir(parents=True, exist_ok=True)
    with open(args.out / f"{args.name}.jsonl", "w", encoding="utf-8") as fh:
        for s in signals:
            fh.write(json.dumps(s, sort_keys=True) + "\n")
    (args.out / f"{args.name}.labels.json").write_text(json.dumps(labels, indent=1) + "\n", encoding="utf-8")
    counts = dict(Counter(s["sig"] for s in signals))
    counts["interventions"] = len(labels["interventions"])
    counts["pauses"] = len(pauses)
    (args.out / f"{args.name}.counts.json").write_text(json.dumps(counts, indent=1, sort_keys=True) + "\n",
                                                       encoding="utf-8")
    if args.pauses:
        with open(args.out / f"{args.name}.pauses.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["pause_id", "t_ms", "source", "gap_ms", "label", "annotator"])
            w.writeheader()
            w.writerows(pauses)
    return 0


if __name__ == "__main__":
    sys.exit(main())
