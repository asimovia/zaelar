"""P3, full profile: the seeded bombardment at 100,000 cases (by request, not in the gate).

    ./.venv/bin/python -m tests.conversation.benchmarks.bombardment --cases 100000 --seed-base <n> --out report.json

Seeds rotate from `--seed-base` (default: a number derived from the date, written in the report so any red replays).
Each case is `conversation.testing.generate.run_case(seed, actions)`; the report holds the counts, the time, the
violations by invariant with their seeds — never more than `--keep` examples per invariant. Exit code 1 on any
violation.
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
import time
from collections import Counter

from conversation.testing.generate import run_case


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cases", type=int, default=100_000)
    ap.add_argument("--actions", type=int, default=14)
    ap.add_argument("--seed-base", type=int, default=int(datetime.date.today().strftime("%Y%m%d")) * 1_000_000)
    ap.add_argument("--keep", type=int, default=5)
    ap.add_argument("--out", help="write the JSON report here")
    args = ap.parse_args(argv)
    t0 = time.monotonic()
    by_inv: Counter = Counter()
    examples: dict[str, list] = {}
    bad_cases = 0
    for i in range(args.cases):
        seed = args.seed_base + i
        violations = run_case(seed, args.actions)
        if violations:
            bad_cases += 1
            for v in violations:
                inv = v.split(":", 1)[0]
                by_inv[inv] += 1
                if len(examples.setdefault(inv, [])) < args.keep:
                    examples[inv].append({"seed": seed, "violation": v})
        if (i + 1) % 10_000 == 0:
            print(f"{i + 1} cases · {bad_cases} with violations · {time.monotonic() - t0:.0f} s", file=sys.stderr)
    report = {"cases": args.cases, "actions_per_case": args.actions, "seed_base": args.seed_base,
              "seconds": round(time.monotonic() - t0, 1), "cases_with_violations": bad_cases,
              "violations_by_invariant": dict(by_inv), "examples": examples}
    text = json.dumps(report, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text)
    return 1 if bad_cases else 0


if __name__ == "__main__":
    sys.exit(main())
