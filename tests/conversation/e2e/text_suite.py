"""The manager's end-to-end text suite (V2-941, B7; the F1 plan §9; node 13.50) — live, by request.

    ./.venv/bin/python -m tests.conversation.e2e.text_suite --port <sandbox> --lang es [--repeat 3] [--cases T1 T3]

On a sandbox from `tests.conversation.e2e.sandbox` (switch on, every outside write held, Rowan seeded). Each case of
the frozen suite (`fixtures/suite/text.v1.json`, T1–T12 in Spanish and English, the corpus's format) is driven by the
corpus's own schedule (`corpus_drive.drive_conversation`: pieces in bursts without waiting, the next thought after the
answer), in its own session, `--repeat` times. Judged per thought on the manager's path, from what the text channel
answers (the request's close, the reads its run made, the reads refused) and the session's proof:

  close      each thought's request closed once — `answered`, or `silent` where the thought needs no answer; never
             stalled, never left open
  answers    one answer per thought that needs one (a thought typed in pieces is answered once)
  route      the expected families read, no family the case forbids (the suite's own labels); 100 % where the case exists
             for its route (T3 agenda, T7 refused act, T10 about itself), a rate elsewhere (T1, T8: the model's)
  no effect  an act asked for is refused or never called; no task row left; the proof's `effects_outside_read` 0
  one owner  the proof (`/api/debug/conversation/me`) passes: the manager ran, nothing else opened a turn
  language   each answer in the conversation's language

Coherence and latency are reported, not gated, here: the judge reads the transcripts this writes.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from tests.conversation.tools.corpus_drive import Engine, drive_conversation, families, lang_of

SUITE = Path(__file__).resolve().parents[1] / "fixtures" / "suite" / "text.v1.json"
OUT = Path(__file__).resolve().parents[2] / "runs" / "conversation" / "text_suite"
#: the cases that exist for their route: there the route is a gate; elsewhere it is a rate (the model's choice)
ROUTE_GATED = ("T3", "T7", "T10")


def load(cases: list[str] | None = None, langs: list[str] | None = None) -> list[dict]:
    suite = json.loads(SUITE.read_text(encoding="utf-8"))
    return [c for c in suite["conversations"] if (not cases or c["case"] in cases) and (not langs or c["lang"] in langs)]


def judge(rec: dict) -> dict:
    """The manager's path, per thought; a conversation passes when every gated check of every thought passes."""
    out = []
    for row in rec["thoughts"]:
        t, ans = row["turn"], row["answers"]
        said = [a for a in ans if str(a.get("reply") or "").strip()]
        closes = [((a.get("conv") or {}).get("close")) for a in ans]
        called = set().union(*[families(c) for a in ans for c in a.get("tool_calls") or []]) if ans else set()
        refused = [c for a in ans for c in a.get("refused_calls") or []]
        expect = set() if t["act_refused"] else set(t["expect_tools"])     # the suite's own labels, by hand
        forbid = set(t["forbid_tools"])
        r = {"thought": t["thought"], "pieces": len(t["pieces"]), "answers": len(said), "closes": closes,
             "called": sorted(called), "refused": len(refused),
             "close": bool(closes) and all(c in (("answered",) if t["needs_answer"] else ("answered", "silent"))
                                           for c in closes[-1:]) and "no_close_yet" not in closes,
             "answers_ok": len(said) == 1 if t["needs_answer"] else len(said) <= 1,
             "route": expect <= called and not (called & forbid),
             "no_effect": not ({"messaging", "screen"} & called) and not rec.get("new_tasks")}
        if rec["lang"] in ("es", "en") and said:
            r["language"] = all(lang_of(a["reply"]) in (rec["lang"], "?") for a in said)
        gated = ("close", "answers_ok", "no_effect", "language") + (("route",) if rec["case"] in ROUTE_GATED else ())
        r["pass"] = all(r[k] for k in gated if k in r)
        out.append(r)
    proof = rec.get("proof") or {}
    owner = bool(proof.get("passes")) and not (proof.get("counters") or {}).get("effects_outside_read")
    return {"thoughts": out, "one_owner": owner, "pass": owner and all(r["pass"] for r in out)}


def summary(recs: list[dict]) -> dict:
    """Per case: runs and passes; the gate is every run of every case passing, the route of T1/T8 as a rate."""
    by: dict = {}
    for rec in recs:
        c = by.setdefault(rec["id"], {"runs": 0, "pass": 0, "route_rate": [0, 0]})
        c["runs"] += 1
        c["pass"] += rec["verdict"]["pass"]
        for r in rec["verdict"]["thoughts"]:
            c["route_rate"][0] += r["route"]
            c["route_rate"][1] += 1
    return {"cases": by, "pass": bool(by) and all(c["pass"] == c["runs"] for c in by.values())}


async def run(eng, convs: list[dict], repeat: int, out: Path) -> dict:
    recs = []
    with open(out / "runs.jsonl", "a", encoding="utf-8") as fh:
        for conv in convs:
            for n in range(repeat):
                rec = await drive_conversation(eng, conv)
                rec["case"], rec["repeat"] = conv["case"], n
                rec["proof"] = eng._req("GET", "/api/debug/conversation/me", timeout=30)
                rec["verdict"] = judge(rec)
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fh.flush()
                recs.append(rec)
                print(f"{conv['id']} #{n + 1}: {'PASS' if rec['verdict']['pass'] else 'fail'}", flush=True)
    return summary(recs)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--lang", nargs="+", default=["es", "en"])
    ap.add_argument("--cases", nargs="*", default=None)
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    out = a.out or OUT / time.strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    s = asyncio.run(run(Engine(a.port), load(a.cases, a.lang), a.repeat, out))
    (out / "summary.json").write_text(json.dumps(s, indent=1))
    print(json.dumps(s, indent=1))
    print(out)
    return 0 if s["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
