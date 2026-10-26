"""rules/notes.py — the rules the MODEL reads: `pref` rows whose key is `note` (V2-806).

A note is a sentence of his that no code applies («en la agenda, las reuniones siempre de 30 minutos»). It is a
row like any other — scoped, listed, removable by id — and the model reads it only on the surfaces its scope
reaches:

  · "voice"       → `global` + `voice`        (how the voice turn behaves; a widget's note rides in its own row)
  · "worker"      → `global` + `widget:*`      (a manner of speaking means nothing to a browser errand)
  · "widget:<id>" → that widget's notes
  · anything else → every note

The notes that lived as sentences in the memory state (`state.rules` + `state.rule_scopes`) are imported once
(`migrate_memory_state`) and the memory state forgets them.
"""
from __future__ import annotations

import hashlib
import time

from . import cascade as _cascade
from . import scope as _scope
from . import store as _store

NOTE = _cascade.NOTE


def _carries(surface: str, sc: str) -> bool:
    if surface == "voice":
        return sc in (_scope.GLOBAL, _scope.VOICE)
    if surface == "worker":
        return sc == _scope.GLOBAL or sc.startswith("widget:")
    if surface.startswith("widget:"):
        return sc == surface
    return True


def rows(surface: str = "", *, now: float | None = None) -> list[dict]:
    """The live note rows this surface carries, oldest first."""
    migrate_memory_state()
    surface = _scope.norm(surface) if surface else ""
    out = [r for r in _store.rows() if r["key"] == NOTE and _cascade.live(r, now)]
    if surface:
        out = [r for r in out if _carries(surface, r["scope"])]
    return sorted(out, key=lambda r: float(r.get("created_at") or 0.0))


def for_surface(surface: str) -> list[str]:
    return [text_of(r) for r in rows(surface)]


def by_widget() -> dict:
    """{widget id: [note texts]} for every note scoped to a widget (or one of its actions)."""
    out: dict = {}
    for r in rows():
        if r["scope"].startswith("widget:"):
            out.setdefault(r["scope"].split(":", 1)[1].split("/", 1)[0], []).append(text_of(r))
    return out


def text_of(row: dict) -> str:
    return str(row.get("text") or row.get("value") or "").strip()


def add(text: str, scope: str = _scope.GLOBAL, **kw) -> dict | None:
    """Store a sentence of his as a note at `scope` (an identical note at that scope is replaced)."""
    import rules
    t = str(text or "").strip().rstrip(".")
    if not t:
        return None
    return rules.add(scope, "pref", NOTE, t, text=t, **kw)


def remove_matching(text: str) -> str:
    """Remove the note his words best match (moved verbatim from the memory state's fuzzy remover; F3 of V2-806
    replaces it with removal BY ID through the rule's understood scope). Returns the removed text, or ''."""
    import difflib

    import rules
    cand = rows()
    if not cand:
        return ""
    key = _legacy_key(text)
    key_toks = {w for w in key.split() if len(w) > 3}
    best, best_score = None, 0.0
    for r in cand:
        rn = _legacy_key(text_of(r))
        score = difflib.SequenceMatcher(None, key, rn).ratio()
        if key_toks & {w for w in rn.split() if len(w) > 3}:
            score = max(score, 0.6)
        if score > best_score:
            best, best_score = r, score
    if best is None or best_score < 0.45:
        return ""
    rules.remove(best["id"])
    return text_of(best)


def _note_id(text: str) -> str:
    return "m_note_" + hashlib.sha1(" ".join(text.lower().split()).encode("utf-8")).hexdigest()[:12]


def migrate_memory_state() -> int:
    """Move the sentences the memory state held into the table, ONCE per database, then clear them from the
    state. Deterministic ids: a second run inserts nothing. Returns how many rows were inserted."""
    marker = "migrated:state.rules"
    if _store.once_done(marker):
        return 0
    n = 0
    try:
        from memory import api as _mem
        st = _mem.state() or {}
    except Exception as e:  # noqa: BLE001 — memory unreadable: nothing moves, and it is retried next process
        import logging
        logging.getLogger("zaelar.rules").warning(f"rules: memory state unreadable ({e}) — notes not migrated")
        return 0
    texts = [str(r).strip() for r in (st.get("rules") or []) if isinstance(r, str) and str(r).strip()]
    scopes = st.get("rule_scopes") if isinstance(st.get("rule_scopes"), dict) else {}
    base = time.time() - len(texts)
    for i, t in enumerate(texts):
        sc = _scope.norm(scopes.get(_legacy_key(t), _scope.GLOBAL))
        if _store.insert_new({"id": _note_id(t), "scope": sc, "kind": "pref", "key": NOTE, "value": t, "text": t,
                              "source": "user", "created_at": base + i, "origin": "state.rules"}):
            n += 1
    if texts or scopes:
        _mem.set_state({"rules": [], "rule_scopes": {}})
    _store.mark_done(marker)
    return n


def _legacy_key(text: str) -> str:
    """The key `state.rule_scopes` used: lower-case, no accents, no punctuation, blanks collapsed."""
    import re
    import unicodedata
    n = unicodedata.normalize("NFKD", (text or "").strip().lower())
    n = "".join(c for c in n if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w\s]", " ", n).split())
