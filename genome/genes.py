"""genome/genes.py — the CLOSED set of heritable gene shapes (V2-859 T564).

A gene that may cross from this agent to another is one of four typed shapes; anything else cannot be exported,
because there is no constructor for it and `invalid()` refuses it:

  | type             | key                       | value                         | scope        | evidence (genesis)  |
  |------------------|---------------------------|-------------------------------|--------------|---------------------|
  | `alias`          | {lang, phrase}            | a DECLARED action (executor)  | one language | agree > disagree,   |
  |                  |                           |                               |              | hits ≥ alias_hits   |
  | `route`          | {domain}                  | ordered channel ids           | universal    | closures ≥ k        |
  | `nothing_serves` | {domain, channel}         | null                          | universal    | empty answers ≥ k   |
  | `threshold`      | {knob}                    | a number inside its bounds    | universal    | measured            |

PROSE IS NEVER A GENE. A playbook's brief and method are written by people in the genome and reviewed; a third
party's message can teach this agent nothing that later reaches every agent's prompt as text. A route carries the
channel KIND (`connector`, `mesh`, `browser`, `worker`), never the `target` — a target names a site, a company or
an agent, which is exactly what a playbook never names.
"""
from __future__ import annotations

import json
import re

TYPES = ("alias", "route", "nothing_serves", "threshold")

#: A route's domain is a key from `nucleo/routes/domains.py` (`restaurant`, `transport.taxi`, …): lowercase words.
_DOMAIN = re.compile(r"^[a-z][a-z_]*(?:\.[a-z][a-z_]*)*$")


def channels() -> tuple[str, ...]:
    from nucleo.routes import store
    return (store.CH_CONNECTOR, store.CH_MESH, store.CH_BROWSER, store.CH_WORKER)


def _need(genesis: dict, name: str, default: int) -> int:
    try:
        return int(((genesis.get("genome") or {}).get("evidence") or {}).get(name, default))
    except (TypeError, ValueError):
        return default


def alias(row: dict) -> dict:
    """A learned action-map row as a gene. The action is parsed; an unparsable one is refused by `invalid()`."""
    try:
        action = json.loads(row.get("action") or "")
    except (TypeError, ValueError):
        action = None
    return {"type": "alias", "key": {"lang": row.get("lang") or "", "phrase": row.get("phrase") or ""},
            "value": action, "evidence": {"hits": int(row.get("hits") or 0), "agree": int(row.get("agree") or 0),
                                          "disagree": int(row.get("disagree") or 0)}}


def routes(rows: list[dict]) -> list[dict]:
    """Learned route rows as genes: one `route` per domain (its active channels by rank), one `nothing_serves` per
    empty (domain, channel). The row's `target` never enters a gene."""
    out: list[dict] = []
    by_domain: dict[str, list[dict]] = {}
    for r in rows:
        by_domain.setdefault(str(r.get("domain") or ""), []).append(r)
    for domain, rs in sorted(by_domain.items()):
        live = sorted((r for r in rs if r.get("status") == "active"), key=lambda r: int(r.get("rank") or 0))
        if live:
            out.append({"type": "route", "key": {"domain": domain}, "value": [r.get("channel") for r in live],
                        "evidence": {"closures": len(live) + sum(int(r.get("hits") or 0) for r in live)}})
        for r in rs:
            if r.get("status") == "none":
                out.append({"type": "nothing_serves", "key": {"domain": domain, "channel": r.get("channel")},
                            "value": None, "evidence": {"answers": 1 + int(r.get("hits") or 0)}})
    return out


def invalid(gene: dict, genesis: dict) -> str:
    """'' when the gene is one of the closed shapes with the evidence it needs here, else why it is not."""
    if not isinstance(gene, dict) or gene.get("type") not in TYPES:
        return f"unknown gene type {gene.get('type') if isinstance(gene, dict) else gene!r}"
    t, key, value, ev = gene["type"], gene.get("key") or {}, gene.get("value"), gene.get("evidence") or {}
    if t == "alias":
        from nucleo.actionmap import executor
        why = executor.validate(value) if key.get("lang") and key.get("phrase") else "alias without lang/phrase"
        if why:
            return f"alias: {why}"
        if not (ev.get("agree", 0) > ev.get("disagree", 0) and ev.get("hits", 0) >= _need(genesis, "alias_hits", 3)):
            return "alias: not enough evidence"
        return ""
    if t in ("route", "nothing_serves"):
        if not _DOMAIN.match(str(key.get("domain") or "")):
            return f"{t}: domain is not a key"
        chans = value if t == "route" else [key.get("channel")]
        if not isinstance(chans, list) or not chans or any(c not in channels() for c in chans):
            return f"{t}: a channel that is not declared"
        need, have = (("route_closures", ev.get("closures", 0)) if t == "route"
                      else ("nothing_serves_answers", ev.get("answers", 0)))
        return "" if have >= _need(genesis, need, 1) else f"{t}: not enough evidence"
    bounds = ((genesis.get("genome") or {}).get("thresholds") or {}).get(str(key.get("knob") or ""))
    if not (isinstance(bounds, list) and len(bounds) == 2):
        return "threshold: a knob that is not declared heritable"
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not bounds[0] <= value <= bounds[1]:
        return "threshold: value outside its declared bounds"
    return "" if ev.get("measured") else "threshold: not measured"
