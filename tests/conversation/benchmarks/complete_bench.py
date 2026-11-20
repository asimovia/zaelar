"""How well the voice's model reads a thought as finished or not (v3.1 §1.6 quater's gate; node 13.51) — live.

    ./.venv/bin/python -m tests.conversation.benchmarks.complete_bench --set v3 [--lang es en] [--incomplete 10]
        [--complete 100] [--samples 3] [--seed 1] [--out FILE]

`--set v3` takes the items from the tester's frozen labelled set (`fixtures/complete/v3`, built to the rule written
before measuring, the agent's name the engine's); without it, from the corpus cut below. Each item is read `--samples`
times and decided by majority (`complete_set.majority`); a provider failure in most samples stays INFRA.

The items come from the frozen corpus, cut where §1.6 quater needs the reading:
  INCOMPLETE  a thought's pieces up to one that ends with a sentence mark while more pieces follow — the person goes
              on after a mark, the case the provider's mark gets wrong
  COMPLETE    a whole thought that needs an answer
Each item is asked alone, as the manager asks it: the real prefix (`conversation_host.prefix`), the item as one
closed voice entry, on the routing table's voice model through the Model port (`FastModel`), with no read offered —
it measures the reading of the thought, not tool behaviour. What is read is the order's `complete`: true, false, or
no field (which counts against). The keys come from the operator's credential store (a bare process has none); a
provider that does not answer most items makes the run INFRA (exit 2), never a silent fail of the gate.

The gate, per language (frozen in the design before measuring): at least 6 of 10 incomplete read as `false` and 85 of
100 complete read as `true`. Short of it, the field is not asked — one line of the prefix — and the fixed graces stay.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
from pathlib import Path

from tests.conversation.tools.corpus import ROOT as CORPUS

MARKS = (".", "?", "!", "…")
GATE = {"incomplete": 0.6, "complete": 0.85}
LANGS = {"es": ("español", "Spanish"), "en": ("English", "English")}


def items(lang: str, n_incomplete: int, n_complete: int, seed: int = 1, version: str = "v1") -> list[dict]:
    """Marked cuts first; when the corpus holds fewer than asked, the rest are cuts after a piece with no mark
    (`cut: unmarked`), reported apart — the corpus was not written for this bench, and that is said, not hidden."""
    marked, unmarked, comp = [], [], []
    for f in sorted((CORPUS / version).glob(f"U*.{lang}.json")):
        for conv in json.loads(f.read_text(encoding="utf-8")):
            for t in conv["turns"]:
                texts = [p["text"].strip() for p in t["pieces"]]
                cuts = [i for i, x in enumerate(texts[:-1]) if x]
                at = next((i for i in cuts if texts[i].endswith(MARKS)), None)
                for i, cut, pool in ((at, "marked", marked), (cuts[0] if cuts else None, "unmarked", unmarked)):
                    if i is not None:
                        pool.append({"id": f"{conv['id']}:{t['thought']}:{i}", "text": " ".join(texts[:i + 1]),
                                     "label": "incomplete", "cut": cut})
                if t.get("needs_answer"):
                    comp.append({"id": f"{conv['id']}:{t['thought']}", "text": " ".join(texts), "label": "complete"})
    rng = random.Random(seed)
    picked = rng.sample(marked, min(n_incomplete, len(marked)))
    seen = {x["id"] for x in picked}
    rest = [x for x in unmarked if x["id"] not in seen]
    picked += rng.sample(rest, min(n_incomplete - len(picked), len(rest)))
    return picked + rng.sample(comp, min(n_complete, len(comp)))


def from_set(lang: str, version: str, n_incomplete: int, n_complete: int) -> list[dict]:
    """The items of a frozen labelled set (`fixtures/complete/<version>`, `tools/complete_set.py`: its loader refuses
    a changed byte), in its own order."""
    from tests.conversation.tools import complete_set
    got = complete_set.load(lang, version)
    return ([x for x in got if x["label"] == "incomplete"][:n_incomplete]
            + [x for x in got if x["label"] == "complete"][:n_complete])


def prompt(text: str, lang: str):
    """The prompt the manager would build for this one closed voice entry."""
    from conversation import envelopes as E
    from conversation.composer import blocks
    from conversation.ports import PromptParts
    from conversation.types import Channel, EnvelopeKind
    from nucleo.conversation_host import prefix, tools_read
    env = E.make(EnvelopeKind.USER_UTTERANCE, E.UtteranceBody("iv_bench", text, terminal=True), producer="ear:bench",
                 producer_id="bench", account="bench", onset_ms=0, sealed_ms=0, channel=Channel.VOICE,
                 refs=E.Refs(intervention_id="iv_bench"))
    native, name = LANGS[lang]
    from genome import persona
    return PromptParts(prefix.build(tools_read.catalog(), native=native, name=name, agent=persona.default_name(lang),
                                    held=prefix.held_acts()), "", (), blocks.input_block((env,)))


async def read(model, text: str, lang: str):
    """The order's `complete` for one item: True, False, None (no field, or no order), or `failed:<why>` when the
    provider never answered — INFRA, never «the model said nothing». No read is offered: the bench measures the
    reading of the thought, not what the model does with a tool."""
    from conversation.ports import Command, Failed
    async for ev in model.stream(prompt(text, lang), [], run_id="bench", model_id=""):
        if isinstance(ev, Failed):
            return f"failed:{ev.reason[:80]}"
        if isinstance(ev, Command) and ev.name in ("reply", "no_reply"):
            v = ev.args.get("complete")
            return v if isinstance(v, bool) else None
    return None


def score(results: list[dict]) -> dict:
    """Per language: the share of each label read right, and the gate."""
    out = {}
    for lang in sorted({r["lang"] for r in results}):
        rs = [r for r in results if r["lang"] == lang]
        row = {}
        for label, want in (("incomplete", False), ("complete", True)):
            mine = [r for r in rs if r["label"] == label]
            row[label] = {"n": len(mine), "right": sum(r["complete"] is want for r in mine),
                          "missing": sum(r["complete"] is None for r in mine),
                          "marked": sum(r.get("cut") == "marked" for r in mine)}
            row[label]["rate"] = round(row[label]["right"] / len(mine), 3) if mine else None
        failed = sum(isinstance(r["complete"], str) for r in rs)
        row["failed"] = failed
        row["infra"] = failed > len(rs) // 2              # the provider, not the model: never a verdict on the field
        row["pass"] = not row["infra"] and all(row[k]["rate"] is not None and row[k]["rate"] >= GATE[k] for k in GATE)
        out[lang] = row
    infra = any(v["infra"] for v in out.values())
    return {"by_lang": out, "infra": infra, "pass": bool(out) and not infra and all(v["pass"] for v in out.values())}


async def read_n(model, text: str, lang: str, samples: int = 1):
    """One reading from `samples` reads: the majority of the answers; failures in most samples are a failure."""
    from tests.conversation.tools import complete_set
    got = [await read(model, text, lang) for _ in range(max(1, samples))]
    failed = [g for g in got if isinstance(g, str)]
    if len(failed) > len(got) // 2:
        return failed[0]
    return got[0] if len(got) == 1 else complete_set.majority([g for g in got if not isinstance(g, str)])


async def run(model, langs: list[str], n_incomplete: int, n_complete: int, seed: int,
              labelled: str | None = None, samples: int = 1) -> list[dict]:
    results = []
    for lang in langs:
        source = (from_set(lang, labelled, n_incomplete, n_complete) if labelled
                  else items(lang, n_incomplete, n_complete, seed))
        for it in source:
            results.append({**it, "lang": lang, "complete": await read_n(model, it["text"], lang, samples)})
    return results


def load_credentials() -> bool:
    """The model keys a bare process does not have: the operator's credential store, from the MAIN checkout (a
    worktree never holds it) — loaded into this process's environment, never printed. False when there is none."""
    from dotenv import load_dotenv
    from tests.platform.sandbox_engine import OPERATOR_STORE
    return OPERATOR_STORE.is_file() and bool(load_dotenv(OPERATOR_STORE, override=False))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", nargs="+", default=["es", "en"])
    ap.add_argument("--incomplete", type=int, default=10)
    ap.add_argument("--complete", type=int, default=100)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--samples", type=int, default=3, help="reads per item, decided by majority")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--set", dest="labelled", default=None,
                    help="a frozen labelled set, `fixtures/complete/<version>` (e.g. v3), instead of the corpus cut")
    a = ap.parse_args(argv)
    load_credentials()
    from nucleo.conversation_host.model import FastModel
    results = asyncio.run(run(FastModel(), a.lang, a.incomplete, a.complete, a.seed, a.labelled, a.samples))
    s = score(results)
    out = a.out or Path(__file__).resolve().parents[2] / "runs" / "conversation" / f"complete-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"score": s, "results": results}, ensure_ascii=False, indent=1))
    print(json.dumps(s, indent=1))
    print(out)
    if s["infra"]:
        print("INFRA: most items got no answer from the provider — keys, quota or network; no verdict on the field")
        return 2
    return 0 if s["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
