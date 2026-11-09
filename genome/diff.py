"""genome/diff.py — what this agent learned that its generation does not ship (V2-859 T565).

`python -m genome diff` prints, for this install, the HERITABLE learned genes that differ from the generation it
runs, each with its evidence counts, and what was refused or dropped by kind (never by value). Deterministic,
offline, and it sends nothing: what a deployment does with the output is outside this engine.

Read only from the learned layer (`source='learned'` rows). The personal layer — rules, config, memory, contacts,
the library — is never a source; the privacy filter reads names only to drop the genes that carry one.
"""
from __future__ import annotations

import json


def _same(a, b) -> bool:
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def learned() -> list[dict]:
    """Every learned gene candidate: active learned aliases that differ from the pack, and the learned routes."""
    from memory import api as memory
    from nucleo.actionmap import store as amap

    from . import genes
    out, packs = [], {}
    for row in memory.action_map_learned():
        if row.get("status") != "active":
            continue
        lang = row.get("lang") or ""
        packs.setdefault(lang, amap.factory(lang))
        g = genes.alias(row)
        if not _same(packs[lang].get(row.get("phrase") or ""), g["value"]):
            out.append(g)
    out.extend(genes.routes(memory.routes_learned()))
    return out


def diff(genesis: dict | None = None, particulars: set[str] | None = None) -> dict:
    """`{identity, genes, refused, dropped}` — the heritable difference, sorted, nothing personal in it."""
    import genome

    from . import genes, privacy
    genesis = genome.genesis() if genesis is None else genesis
    ok, refused = [], {}
    for g in learned():
        why = genes.invalid(g, genesis)
        if why:
            refused[why] = refused.get(why, 0) + 1
        else:
            ok.append(g)
    kept, dropped = privacy.keep(ok, particulars)
    kept.sort(key=lambda g: (g["type"], json.dumps(g["key"], sort_keys=True)))
    return {"identity": genome.identity(genesis), "genes": kept, "refused": refused, "dropped": dropped}


def render(d: dict) -> str:
    i = d["identity"]
    lines = [f"genome generation {i['generation']} · {i['hash']} · {','.join(i['langs'])}",
             f"{len(d['genes'])} heritable learned gene(s)"]
    for g in d["genes"]:
        lines.append(json.dumps(g, sort_keys=True, ensure_ascii=False))
    for label, counts in (("refused", d["refused"]), ("dropped (privacy)", d["dropped"])):
        if counts:
            lines.append(f"{label}: " + ", ".join(f"{k} ×{v}" for k, v in sorted(counts.items())))
    return "\n".join(lines)
