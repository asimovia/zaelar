"""How well the voice's model reads a thought as finished or not (v3.1 §1.6 quater's gate; node 13.51) — live.

    ./.venv/bin/python -m tests.conversation.benchmarks.complete_bench [--lang es en] [--incomplete 10]
        [--complete 100] [--seed 1] [--out FILE]

The items come from the frozen corpus, cut where §1.6 quater needs the reading:
  INCOMPLETE  a thought's pieces up to one that ends with a sentence mark while more pieces follow — the person goes
              on after a mark, the case the provider's mark gets wrong
  COMPLETE    a whole thought that needs an answer
Each item is asked alone, as the manager asks it: the real prefix (`conversation_host.prefix`), the item as one
closed voice entry, the read catalogue, on the routing table's voice model through the Model port (`FastModel`); a
read the model wants first gets an empty result, once. What is read is the order's `complete`: true, false, or no
field (which counts against).

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
    """The order's `complete` for one item: True, False, or None (no field, no order)."""
    from conversation.ports import Command, PromptParts, ToolCall, ToolResult
    from nucleo.conversation_host import tools_read
    parts, steps = prompt(text, lang), []
    for _round in range(2):
        called = None
        async for ev in model.stream(PromptParts(parts.prefix, parts.state, parts.conversation, parts.input,
                                                 tuple(steps)), tools_read.catalog(), run_id="bench", model_id=""):
            if isinstance(ev, Command) and ev.name in ("reply", "no_reply"):
                v = ev.args.get("complete")
                return v if isinstance(v, bool) else None
            if isinstance(ev, ToolCall) and called is None:
                called = ev
        if called is None:
            return None
        steps.append((called, ToolResult("ok", {"note": "no data in this bench"})))
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
        row["pass"] = all(row[k]["rate"] is not None and row[k]["rate"] >= GATE[k] for k in GATE)
        out[lang] = row
    return {"by_lang": out, "pass": bool(out) and all(v["pass"] for v in out.values())}


async def run(model, langs: list[str], n_incomplete: int, n_complete: int, seed: int) -> list[dict]:
    results = []
    for lang in langs:
        for it in items(lang, n_incomplete, n_complete, seed):
            results.append({**it, "lang": lang, "complete": await read(model, it["text"], lang)})
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", nargs="+", default=["es", "en"])
    ap.add_argument("--incomplete", type=int, default=10)
    ap.add_argument("--complete", type=int, default=100)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    from nucleo.conversation_host.model import FastModel
    results = asyncio.run(run(FastModel(), a.lang, a.incomplete, a.complete, a.seed))
    s = score(results)
    out = a.out or Path(__file__).resolve().parents[2] / "runs" / "conversation" / f"complete-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"score": s, "results": results}, ensure_ascii=False, indent=1))
    print(json.dumps(s, indent=1))
    print(out)
    return 0 if s["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
