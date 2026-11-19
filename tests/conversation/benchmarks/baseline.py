"""F0 baseline: what the turn path of today does, counted over a session archive. Numbers only.

    ./.venv/bin/python -m tests.conversation.benchmarks.baseline <archive-dir|file.jsonl> [--json out.json]
        [--map map.json]

The archive is a folder of observer event logs (see `tests/conversation/tools/archive.py`). Every metric is read
through ONE vocabulary, `tests/conversation/tools/today.py`, so the numbers and the P2 converter agree on what an
event means. The output holds counts, milliseconds and percentiles keyed `s1..sN`; no text, no session id. `--map`
writes the `sN ↔ file` correspondence to a separate file for whoever keeps it (it is never committed).

What each metric is:
  eager            eager end-of-turn hints (the model starting on a pause), per session and per final sentence
  resumed          an eager hint after which the person went on: a partial with new words before the next final
  split_sentences  a run of the person's finals between two agent lines that holds more than one final (one sentence, cut)
  turns_cancelled  a turn in flight cancelled by a longer sentence
  dropped / held   fragments thrown away / held back by the accumulator
  unreadable_asks  turns answered with «say that again?»
  loop_nudges      anti-loop nudges injected
  deciders_per_turn  decision calls around the model, per prompt
  final_to_prompt  ms from the final sentence to the model's prompt; `not_reached_10s` counts those that never got there
  first_audio      ms from the end of the speech to the first audio (p50/p95/p99)
  stop_to_silence  ms from an attended stop to the agent going idle
  loop_stalls      host loop held > 100 ms and > 500 ms (count, total ms)
  forced_source    answers whose source the code imposed (a forced read of a card, a rail)
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from tests.conversation.tools import archive, today

RESUME_HORIZON_MS = 10_000   # an eager hint is judged against what is said in the next 10 s, not the rest of the day
PROMPT_HORIZON_MS = 10_000   # a final that has no prompt in 10 s did not reach the model (§10.1)


def percentiles(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    vs = sorted(values)

    def at(q: float) -> float:
        return vs[min(len(vs) - 1, max(0, math.ceil(q * len(vs)) - 1))]   # nearest rank

    return {"n": len(vs), "p50": at(0.50), "p95": at(0.95), "p99": at(0.99), "max": vs[-1]}


def resumed_eagers(tagged: list[tuple[str, archive.Event]]) -> int:
    """An eager hint is RESUMED when, before the next final sentence, a partial arrives with words the hint did not
    have (Flux's TurnResumed reaches today's engine as a partial)."""
    n = 0
    for i, (sig, ev) in enumerate(tagged):
        if sig != "eager":
            continue
        for sig2, ev2 in tagged[i + 1:]:
            if ev2.t_ms - ev.t_ms > RESUME_HORIZON_MS or sig2 == "user_final":
                break
            if sig2 == "user_interim" and ev2.text.strip() != ev.text.strip():
                n += 1
                break
    return n


def split_sentences(tagged: list[tuple[str, archive.Event]]) -> int:
    n, run = 0, 0
    for sig, _ev in tagged:
        if sig == "user_final":
            run += 1
        elif sig == "agent_line":
            n += run > 1
            run = 0
    return n + (run > 1)


def _next_after(tagged, i: int, want: str, horizon_ms: int) -> int | None:
    t0 = tagged[i][1].t_ms
    for sig, ev in tagged[i + 1:]:
        if ev.t_ms - t0 > horizon_ms:
            return None
        if sig == want:
            return ev.t_ms - t0
    return None


def session_metrics(events: list[archive.Event]) -> dict:
    tagged = [(s, e) for e in events if (s := today.classify(e))]
    count = {s: 0 for s in today.SIGNALS}
    for s, _e in tagged:
        count[s] += 1
    to_prompt, unreached, stop_ms = [], 0, []
    for i, (sig, _ev) in enumerate(tagged):
        if sig == "user_final":
            d = _next_after(tagged, i, "prompt", PROMPT_HORIZON_MS)
            if d is None:
                unreached += 1
            else:
                to_prompt.append(d)
        elif sig == "stop_attended":
            d = _next_after(tagged, i, "agent_idle", PROMPT_HORIZON_MS)
            if d is not None:
                stop_ms.append(d)
    stalls = [m for s, e in tagged if s == "loop_stall" and (m := today.stall_ms(e)) is not None]
    first_audio = [m for s, e in tagged if s == "first_audio" and (m := today.first_audio_ms(e)) is not None]
    finals = count["user_final"]
    return {
        "eager": count["eager"],
        "eager_per_final": round(count["eager"] / finals, 3) if finals else None,
        "resumed": resumed_eagers(tagged),
        "finals": finals,
        "split_sentences": split_sentences(tagged),
        "turns_cancelled": count["turn_cancelled"],
        "dropped": count["fragment_dropped"],
        "held": count["held"],
        "unreadable_asks": count["unreadable_ask"],
        "loop_nudges": count["loop_nudge"],
        "prompts": count["prompt"],
        "deciders": count["decider"],
        "deciders_per_turn": round(count["decider"] / count["prompt"], 3) if count["prompt"] else None,
        "final_to_prompt_ms": to_prompt,
        "not_reached_10s": unreached,
        "first_audio_ms": first_audio,
        "stop_to_silence_ms": stop_ms,
        "loop_stalls_100": sum(m > 100 for m in stalls),
        "loop_stalls_500": sum(m > 500 for m in stalls),
        "loop_stall_total_ms": round(sum(stalls)),
        "forced_source": count["forced_source"],
        "typed": count["typed"],
    }


_LISTS = ("final_to_prompt_ms", "first_audio_ms", "stop_to_silence_ms")


def run(root: Path) -> tuple[dict, dict]:
    per, mapping = {}, {}
    for n, (stem, events) in enumerate(archive.sessions(root), start=1):
        key = f"s{n}"
        mapping[key] = stem
        per[key] = session_metrics(events)
    totals: dict = {}
    for m in per.values():
        for k, v in m.items():
            if k in _LISTS:
                totals.setdefault(k, []).extend(v)
            elif isinstance(v, int):
                totals[k] = totals.get(k, 0) + v
    for k in _LISTS:
        totals[k] = percentiles(totals.get(k, []))
    if totals.get("finals"):
        totals["eager_per_final"] = round(totals["eager"] / totals["finals"], 3)
    if totals.get("prompts"):
        totals["deciders_per_turn"] = round(totals["deciders"] / totals["prompts"], 3)
    report = {"sessions": len(per), "totals": totals,
              "per_session": {k: {kk: (percentiles(vv) if kk in _LISTS else vv) for kk, vv in m.items()}
                              for k, m in per.items()}}
    return report, mapping


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("archive", type=Path)
    ap.add_argument("--json", type=Path, help="write the report here (numbers only)")
    ap.add_argument("--map", type=Path, help="write the sN ↔ file correspondence here (private; never commit it)")
    args = ap.parse_args(argv)
    report, mapping = run(args.archive)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.json:
        args.json.write_text(text + "\n", encoding="utf-8")
    else:
        sys.stdout.write(text + "\n")
    if args.map:
        args.map.write_text(json.dumps(mapping, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
