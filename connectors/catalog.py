#
# Connector CATALOG (V2-561, implementing the V2-526 design) — what is merely LISTED, never live.
#
# `connectors/registry.py` is the LIVE inventory: built connectors, their real connection state, redacted
# config. This module is its opposite half: connectors we do NOT have (`state="planned"`) or CANNOT have
# (`state="not-possible"`, with why the door is shut). Declaration is DATA on purpose — a manifest here
# costs zero prompt bytes, zero tool entries and zero imports at startup; only what `registry.py` reports
# as CONNECTED (or a lookup that just ran) costs anything on a turn.
#
# Scope note, same as the design doc: this module is MECHANISM. Which connectors are worth building next
# is not an engine question and is not decided here — the manifests below are a small, illustrative set
# proving the shelf works, not a roadmap.
#
from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

_DIR = Path(__file__).resolve().parent / "catalog"


def load_manifests() -> list[dict]:
    """Every `catalog/*.json`, tolerant of one bad file — same isolation as `registry.py`'s per-family
    reads: a broken manifest must not blank the whole wishlist."""
    out: list[dict] = []
    if not _DIR.is_dir():
        return out
    for p in sorted(_DIR.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("id"):
                out.append(data)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"connectors.catalog: skipping bad manifest {p.name}: {e}")
    return out


def wishlist() -> list[dict]:
    """The NOT-live half of the catalog: `planned` + `not-possible` entries only. A `built` entry's
    manifest exists purely so `search()` can find a connected connector by capability words too — it never
    renders here, `registry.descriptors()` already owns rendering what is actually connected."""
    return [m for m in load_manifests() if m.get("state") in ("planned", "not-possible")]


def _tokens(text: str) -> set[str]:
    return {w for w in "".join(c if c.isalnum() else " " for c in str(text).lower()).split() if w}


def search(query: str, limit: int = 5) -> list[dict]:
    """Lexical, stdlib-only lookup over label+family+capabilities — no embeddings, no model, no network
    (the design's own acceptance test: a lookup must make ZERO model calls). Ranked connected (via the live
    registry) > built > planned > not-possible, ties broken by keyword overlap. At most `limit` hits:
    choosing 1 of 5 is a decision a model makes well, 1 of 10.000 is one it makes badly."""
    q = _tokens(query)
    if not q:
        return []
    try:
        from connectors import registry
        connected_ids = {d.get("id") for d in registry.descriptors() if d.get("connected")}
    except Exception:  # noqa: BLE001
        connected_ids = set()
    rank_by_state = {"built": 1, "planned": 2, "not-possible": 3}
    scored = []
    for m in load_manifests():
        hay = _tokens(" ".join([m.get("label", ""), m.get("family", ""), *m.get("capabilities", [])]))
        overlap = len(q & hay)
        if overlap <= 0:
            continue
        rank = 0 if m.get("id") in connected_ids else rank_by_state.get(m.get("state"), 4)
        scored.append((rank, -overlap, m))
    scored.sort(key=lambda t: (t[0], t[1]))
    return [m for _, __, m in scored[:limit]]


def consent_keys_named(text: str) -> list[str]:
    """The consent keys (`<consent_class>@<id>`) of the channels a sentence NAMES (V2-805).

    Declared data only: a BUILT manifest that declares `consent_class` (the class its sends belong to) is named by
    its own vocabulary — id, label, capabilities — matched as whole words with a short inflection («correos»,
    «whatsapps»). A word two channels share («chats») names neither: doubt about WHICH channel keeps the rule
    global, exactly as it was before a rule could be scoped."""
    import re
    import unicodedata

    def _n(s) -> str:
        s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
        return re.sub(r"[^a-z0-9]+", " ", s).strip()

    t = _n(text)
    if not t:
        return []
    owners: dict[str, set[str]] = {}
    keys: dict[str, str] = {}
    for m in load_manifests():
        cls = str(m.get("consent_class") or "").strip()
        if not cls or m.get("state") != "built":
            continue
        cid = str(m["id"]).strip().lower()
        keys[cid] = f"{cls}@{cid}"
        for w in [cid, m.get("label", "")] + list(m.get("capabilities") or []):
            if _n(w):
                owners.setdefault(_n(w), set()).add(cid)
    named = {next(iter(ids)) for w, ids in owners.items()
             if len(ids) == 1 and re.search(rf"\b{re.escape(w)}\w{{0,2}}\b", t)}
    return sorted(keys[c] for c in named)
