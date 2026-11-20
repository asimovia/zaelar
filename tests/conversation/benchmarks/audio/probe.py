"""Level 3a: audio scenarios through the REAL Flux in real time, then the conversation ear and manager, scored.

    ./.venv/bin/python -m tests.conversation.benchmarks.audio.probe --hand                 # the five hand scenarios
    ./.venv/bin/python -m tests.conversation.benchmarks.audio.probe --strata 1             # every cell, the plan's size
    ./.venv/bin/python -m tests.conversation.benchmarks.audio.probe --strata 0.25 --langs es --conditions pauses
    ./.venv/bin/python -m tests.conversation.benchmarks.audio.probe --strata 1 --reuse-flux --proof ear300
    ./.venv/bin/python -m tests.conversation.benchmarks.audio.probe --list

Flux is recorded ONCE per flow; the recording then runs through the conversation ear and manager (the P2 replay with
its scripted model) at each model latency of the plan (0.3, 0.8 and 1.5 s). The verdict is §5.3 of the test plan on
the prompts the manager actually built (`score.prompt_score`): false cut (R2 by the tolerant 70 % alignment of every
span, the last one deciding — the exact alignment is reported beside it — or R3: a line of ours before the thought's
last span ended), false merge (two of the person's
thoughts in one prompt), wait (the true end → the close of the intervention), exposure (stranger spans in a prompt,
by kind: narration or question). Flux's own turns and the ear's interventions are scored as units too, for
diagnosis only.

Per CELL (a condition × language; in the pauses, each length its own cell), profile A of the plan (§6): with
n ≥ 30 thoughts, the Wilson 95 % upper bound of false cuts and of false merges ≤ 7 %, the point rate ≤ 5 %, the wait
p95 ≤ 600 ms and nothing left open; evaluated at the three latencies, the worst decides. n < 30 is reported only.

The instrument proves itself (`--proof`): `ear300` runs the ear with a 300 ms close cap and its pauses strata must
go red; `shift2s` scores against labels moved 2 s and must go red. A proof that stays green means the bench does
not count.

Writes under `tests/runs/conversation/audio/`: the WAVs and labels, `flux/<id>.raw.jsonl`, `report-<stamp>.json`.
Flows stream concurrently (`--concurrency`), each at real time. The Deepgram key is read from the credential store
into memory, never printed. Nothing is played.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import time
from pathlib import Path

from tests.conversation.benchmarks import flux_probe
from tests.conversation.benchmarks.audio import compose as C
from tests.conversation.benchmarks.audio import flux as F
from tests.conversation.benchmarks.audio import score as SC
from tests.conversation.benchmarks.audio import strata as ST
from tests.conversation.benchmarks.audio.scenarios import SCENARIOS

OUT = C.V.ROOT / "tests" / "runs" / "conversation" / "audio"
DETECTORS = ("flux", "ear", "batch")
PROFILE_A = {"n_min": 30, "wilson_upper": 0.07, "rate": 0.05, "wait_p95_ms": 600}
#: A pause cell whose «goes on» pieces come with a sentence mark more than this share of the time informs and does not
#: decide (plan §5.2): the pieces sound finished, which is not what a person's mid-sentence pause sounds like.
INFORMATIVE_SHARE = 0.5


def _manager(sig: list[dict], config=None, think_ms: int = 800) -> dict:
    """Feed the signals through the whole manager (the P2 replay, without its synthetic watermark beats: Flux's own
    silent updates are the watermark here) and read the ear's interventions and the model's batches off it."""
    from conversation.replay import Replay
    rep = Replay(sig, think_ms=think_ms, config=config) if config is not None else Replay(sig, think_ms=think_ms)
    rep.queue = list(sig)
    rep.run()
    ev = rep.tel.events
    env_iv: dict[str, str] = {}
    for k, _lab, p in ev:
        refs = p.get("refs") or {}
        if k == "conv_inbox" and refs.get("env") and refs.get("iv"):
            env_iv.setdefault(refs["env"], refs["iv"])
    spans = rep.conv.ear.spans
    ear_units = [{"id": p["refs"]["iv"], "state": lab, "end_ms": p["t_ms"],
                  "words": [[w[0], w[1], w[2]] for w in spans.words(p["refs"]["iv"])]}
                 for k, lab, p in ev if k == "conv_ear" and lab in ("closed", "incomplete")]
    runs = [(p["refs"]["run"], p["t_ms"], tuple(env_iv.get(e) for e in p.get("batch_envs") or []))
            for k, lab, p in ev if k == "conv_run" and lab == "started"]
    final_run: dict[str, tuple] = {}
    for run in runs:
        for iv in run[2]:
            if iv:
                final_run[iv] = run
    batch_units = []
    for run in sorted(set(final_run.values()), key=lambda r: r[1]):
        ivs = [iv for iv in dict.fromkeys(run[2]) if iv]
        batch_units.append({"id": run[0], "ivs": ivs, "end_ms": run[1],
                            "words": [[w[0], w[1], w[2]] for iv in ivs for w in spans.words(iv)]})
    count = lambda kind, lab: sum(1 for k, l, _ in ev if k == kind and l == lab)   # noqa: E731
    text_of = {p["refs"]["run"]: p.get("text") or [] for k, lab, p in ev if k == "conv_run" and lab == "input"}
    prompt_runs = [{"run": r[0], "t_ms": r[1], "text": [t for t in text_of.get(r[0], []) if t]} for r in runs]
    return {"ear": ear_units, "batch": batch_units, "runs_text": prompt_runs,
            "says_ms": [p["t_ms"] for k, lab, p in ev if k == "conv_mouth" and lab == "say"],
            "says": [{"t_ms": p["t_ms"], "run": (p.get("refs") or {}).get("run")} for k, lab, p in ev
                     if k == "conv_mouth" and lab == "say"],
            "runs": {"started": len(runs), "held": count("conv_run", "held"),
                     "superseded": count("conv_run", "superseded"), "cancelled": count("conv_run", "cancelled")},
            "ear_events": {lab: count("conv_ear", lab) for lab in ("opened", "tentative", "extended", "closed",
                                                                   "incomplete", "discarded")}}


def _shift(labels: dict, ms: int) -> dict:
    out = json.loads(json.dumps(labels))
    for seg in out["segments"]:
        seg["start_ms"] += ms
        seg["end_ms"] += ms
        seg["words"] = [[w, a + ms, b + ms] for w, a, b in seg["words"]]
    for t in out["turns"]:
        t["start_ms"] += ms
        t["end_ms"] += ms
    return out


def _sha(path: Path) -> str:
    import hashlib
    return hashlib.sha1(path.read_bytes()).hexdigest()


def _meta(raw: Path) -> Path:
    return raw.with_name(raw.name.replace(".raw.jsonl", ".raw.meta.json"))


def _recorded_from(raw: Path) -> str | None:
    """The sha1 of the WAV a recording was made from, or None for a recording older than this check. A recording of
    another WAV under the same id (the scenario changed) is never reused: it would score the old audio against the new
    labels."""
    m = _meta(raw)
    return json.loads(m.read_text(encoding="utf-8")).get("wav_sha1") if m.is_file() else None


async def _flux_all(jobs: list[tuple[Path, Path]], key: str, concurrency: int) -> None:
    sem = asyncio.Semaphore(concurrency)

    async def one(wav: Path, out: Path) -> None:
        async with sem:
            tmp = out.with_suffix(".part")
            import wave
            with wave.open(str(wav), "rb") as w:
                limit = w.getnframes() / w.getframerate() + 30.0     # the stream at real time, its tail, a margin
            for attempt in (1, 2):                                   # a network stall must not hang the whole bench
                try:
                    await asyncio.wait_for(flux_probe.raw(wav, tmp, key=key, cut_at_s=None, tail_s=6.0), limit)
                    break
                except (asyncio.TimeoutError, OSError) as e:
                    print(f"flux: {out.name} attempt {attempt} failed ({type(e).__name__})", flush=True)
                    tmp.unlink(missing_ok=True)
            else:
                return
            tmp.replace(out)
            _meta(out).write_text(json.dumps({"wav_sha1": _sha(wav)}), encoding="utf-8")

    await asyncio.gather(*(one(w, o) for w, o in jobs))


LATENCIES_MS = (300, 800, 1500)      # the scripted model's thinking time (plan §5.2): the worst decides


def score_flow(spec: dict, wav: Path, lab: Path, raw: Path, *, config=None, shift_ms: int = 0) -> dict:
    labels = json.loads(lab.read_text(encoding="utf-8"))
    rawm = F.load_raw(raw)
    edges = F.vad_edges(wav)
    playback = [(g["start_ms"], g["end_ms"]) for g in labels["segments"] if g["role"] == "echo"]
    sig = F.signals(rawm, edges, playback=playback)
    truth = _shift(labels, shift_ms) if shift_ms else labels
    flux_units = [{"id": f"flux{t['seq']}", "words": t["words"], "end_ms": t["end_ms"]}
                  for t in F.flux_turns(rawm) if t["words"]]
    heard = [w for t in F.flux_turns(rawm) for w in t["words"]]
    out = {"stratum": spec.get("stratum", "hand"), "description": labels["description"],
           "truth_turns": len(labels["turns"]), "vad_edges": edges, "flux": SC.score(truth, flux_units), "by_latency": {},
           "alignment": SC.label_alignment(truth, heard), "end_marks": SC.flux_end_marks(truth, rawm)}
    out["infra"] = not out["alignment"]["ok"]
    for think in LATENCIES_MS:
        m = _manager(sig, config, think)
        if think == 800:
            out["ear"], out["batch"] = SC.score(truth, m["ear"]), SC.score(truth, m["batch"])
            out["manager"] = {**m["runs"], "ear_events": m["ear_events"]}
        out["by_latency"][str(think)] = {**SC.prompt_score(truth, m["runs_text"], m["says_ms"], m["ear"], m["says"]),
                                         "runs": m["runs"]}
    return out


def _wilson_upper(k: int, n: int, z: float = 1.96) -> float:
    if n == 0:
        return 1.0
    p = min(1.0, k / n)
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (centre + margin) / (1 + z * z / n)


def _pct(xs: list[int], q: float) -> int | None:
    if not xs:
        return None
    s = sorted(xs)
    return s[min(len(s) - 1, int(math.ceil(q * len(s))) - 1)]


def _decide(n: int, cuts: int, merges: int, waits: list[int], unclosed: int) -> dict:
    d = {"n": n, "cuts": cuts, "merges": merges, "unclosed": unclosed,
         "cut_rate": cuts / n if n else None, "merge_rate": merges / n if n else None,
         "cut_wilson": _wilson_upper(cuts, n), "merge_wilson": _wilson_upper(merges, n),
         "wait_p50": _pct(waits, 0.5), "wait_p95": _pct(waits, 0.95)}
    if n == 0:
        d["verdict"] = "INFRA"                   # zero cases evaluated is never a green (plan §2.4)
    elif n < PROFILE_A["n_min"]:
        d["verdict"] = "n<30"
    else:
        ok = (d["cut_rate"] <= PROFILE_A["rate"] and d["cut_wilson"] <= PROFILE_A["wilson_upper"]
              and d["merge_rate"] <= PROFILE_A["rate"] and d["merge_wilson"] <= PROFILE_A["wilson_upper"]
              and (d["wait_p95"] or 0) <= PROFILE_A["wait_p95_ms"] and unclosed == 0)
        d["verdict"] = "PASS" if ok else "FAIL"
    return d


def aggregate(flows: dict) -> dict:
    """Per cell: profile A on the prompts at each model latency (the worst decides), exposure by stranger kind, and
    the unit-based cut rate of Flux's own turns and of the ear's interventions as diagnostics."""
    acc: dict = {}
    for f in flows.values():
        c = acc.setdefault(f["stratum"], {"lat": {}, "diag": {"flux": [0, 0], "ear": [0, 0]}, "infra": 0,
                                         "marks": {"goes_on": 0, "goes_on_terminal": 0}, "infra_thoughts": 0,
                                         "exposure": {"narration": [0, 0], "question": [0, 0], "echo": [0, 0]}})
        if f.get("infra"):                       # the labels do not sit on the audio: nothing on it is scored
            c["infra"] += 1
            continue
        for k in ("goes_on", "goes_on_terminal"):
            c["marks"][k] += (f.get("end_marks") or {}).get(k, 0)
        for lat, r in f["by_latency"].items():
            a = c["lat"].setdefault(lat, {"n": 0, "cuts": 0, "merges": 0, "waits": [], "unclosed": 0, "says": [],
                                          "why": {"half": 0, "previous_late": 0, "r2": 0}, "cuts_strict": 0})
            for row in r["thoughts"]:
                if row.get("infra"):                 # a cut of the one-utterance mode that was not clean
                    if lat == "800":
                        c["infra_thoughts"] += 1
                    continue
                a["n"] += 1
                a["cuts"] += row["cut"]
                if row["cut"]:
                    a["why"][row.get("cut_why") or "r2"] += 1
                a["cuts_strict"] += (not row.get("r2_strict", row.get("r2", not row["cut"]))) or row.get("spoke_during", 0) > 0
                a["merges"] += row["merged"]
                a["unclosed"] += row["unclosed"]
                if row["wait_ms"] is not None and row["kind"] == "complete" and not row["unclosed"]:
                    a["waits"].append(row["wait_ms"])
                if row.get("say_after_end_ms") is not None and not row["cut"]:
                    a["says"].append(row["say_after_end_ms"])
            if lat == "800":
                for k, (e, t) in r["exposure_by_kind"].items():
                    c["exposure"][k][0] += e
                    c["exposure"][k][1] += t
        for det in ("flux", "ear"):
            for row in f[det]["turns"]:
                c["diag"][det][0] += len(row["units"]) > 1
                c["diag"][det][1] += 1
    out = {}
    for cell, c in acc.items():
        lat = {k: {**_decide(a["n"], a["cuts"], a["merges"], a["waits"], a["unclosed"]),
                   "say_p50": _pct(a["says"], 0.5), "say_p95": _pct(a["says"], 0.95), "cut_why": a["why"],
                   "cut_rate_strict": a["cuts_strict"] / a["n"] if a["n"] else None}
               for k, a in c["lat"].items()}
        verdicts = [d["verdict"] for d in lat.values()] or ["INFRA"]
        worst = next(v for v in ("FAIL", "INFRA", "n<30", "PASS") if v in verdicts)
        go = c["marks"]["goes_on"]
        share = c["marks"]["goes_on_terminal"] / go if go else None
        if "pauses" in cell and share is not None and share > INFORMATIVE_SHARE:
            worst = f"INFORMATIVE ({worst})"         # its pieces sound finished: it informs, it does not decide
        out[cell] = {"by_latency": lat, "verdict": worst, "exposure": c["exposure"], "infra_flows": c["infra"],
                     "terminal_share_goes_on": share, "goes_on_ends": go, "infra_thoughts": c["infra_thoughts"],
                     "diag_unit_cut_rate": {k: (v[0] / v[1] if v[1] else None) for k, v in c["diag"].items()}}
    return out


def run(specs: list[dict], *, reuse_flux: bool, store: Path | None, concurrency: int = 8, proof: str = "") -> dict:
    sub = "scenarios" if all(s.get("stratum") is None for s in specs) else "strata"
    (OUT / "flux").mkdir(parents=True, exist_ok=True)
    composed = {s["id"]: C.compose(s, OUT / sub) for s in specs}
    raws = {s["id"]: OUT / "flux" / f"{s['id']}.raw.jsonl" for s in specs}
    todo = [(composed[i][0], raws[i]) for i in raws if not (reuse_flux and raws[i].is_file()
                                                            and _recorded_from(raws[i]) in (None, _sha(composed[i][0])))]
    if todo:
        key = flux_probe._key(store)
        if not key:
            raise SystemExit("no DEEPGRAM_API_KEY")
        asyncio.run(_flux_all(todo, key, concurrency))
    lost = [i for i in raws if not raws[i].is_file()]
    if lost:                                         # recorded twice and stalled twice: reported, never scored
        print(f"flux: {len(lost)} flow(s) without a recording, left out: {', '.join(lost[:10])}", flush=True)
        specs = [s for s in specs if s["id"] not in lost]
    config, shift = None, 0
    if proof == "ear300":
        from conversation.config import Config
        config = Config(close_cap_ms=300)
    elif proof == "shift2s":
        shift = 2000
    flows = {s["id"]: score_flow(s, *composed[s["id"]], raws[s["id"]], config=config, shift_ms=shift) for s in specs}
    report = {"stamp": time.strftime("%Y%m%d-%H%M%S"), "proof": proof or None, "flux_config": flux_probe.ear_config(),
              "profile_a": PROFILE_A, "strata": aggregate(flows), "flows": flows}
    path = OUT / f"report-{report['stamp']}{'-' + proof if proof else ''}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    report["path"] = str(path)
    return report


def table(report: dict) -> str:
    pc = lambda x: "—" if x is None else f"{100 * x:.0f}"   # noqa: E731
    lines = [f"{'cell':20} {'lat':>4} {'n':>3} {'cut%':>5} {'W95':>4} {'mrg%':>5} {'W95':>4} {'open':>4} "
             f"{'wait p50/p95':>12} {'verdict':>7} | flux/ear unit cut% · exposure narr/quest/echo"]
    for cell, c in sorted(report["strata"].items()):
        for i, (lat, d) in enumerate(sorted(c["by_latency"].items(), key=lambda kv: int(kv[0]))):
            w = f"{d['wait_p50'] if d['wait_p50'] is not None else '—'}/{d['wait_p95'] if d['wait_p95'] is not None else '—'}"
            tail = ""
            if i == 0:
                dg, ex = c["diag_unit_cut_rate"], c["exposure"]
                tail = (f" | {pc(dg['flux'])}/{pc(dg['ear'])} · {ex['narration'][0]}/{ex['narration'][1]} "
                        f"{ex['question'][0]}/{ex['question'][1]} echo {ex['echo'][0]}/{ex['echo'][1]}"
                        f"  → {c['verdict']}")
            lines.append(f"{cell if i == 0 else '':20} {lat:>4} {d['n']:>3} {pc(d['cut_rate']):>5} "
                         f"{pc(d['cut_wilson']):>4} {pc(d['merge_rate']):>5} {pc(d['merge_wilson']):>4} "
                         f"{d['unclosed']:>4} {w:>12} {d['verdict']:>7}{tail}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").partition("\n")[0])
    ap.add_argument("--hand", action="store_true", help="the five hand-written scenarios")
    ap.add_argument("--strata", type=float, default=0, help="scale of the cells (1 = the plan's size)")
    ap.add_argument("--langs", nargs="*", default=list(ST.LANGS))
    ap.add_argument("--conditions", nargs="*", default=list(ST.CONDITIONS))
    ap.add_argument("--pauses", nargs="*", type=int, default=list(ST.PAUSE_GRID_MS))
    ap.add_argument("--reuse-flux", action="store_true")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--proof", choices=("ear300", "shift2s"), default="")
    ap.add_argument("--store", type=Path, help="credential store file (the key is read in memory)")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args(argv)
    if args.list:
        for s in SCENARIOS:
            print(f"{s['id']:28} {s['description']}")
        print(f"strata: {', '.join(ST.LANGS)} × {', '.join(ST.CONDITIONS)}")
        return 0
    specs = list(SCENARIOS) if args.hand else []
    if args.strata:
        specs += ST.strata(args.strata, langs=args.langs, conditions=args.conditions, pauses=args.pauses)
    if not specs:
        ap.error("--hand or --strata N")
    store = args.store
    if store is None:
        from tests.platform.sandbox_engine import OPERATOR_STORE
        store = OPERATOR_STORE if OPERATOR_STORE.is_file() else None
    report = run(specs, reuse_flux=args.reuse_flux, store=store, concurrency=args.concurrency, proof=args.proof)
    print(table(report))
    print(report["path"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
