"""i18n/kickoff.py — the first-turn note of every language, as ONE catalog both the brain and the memory read.

The first turn is the engine speaking in his language (`kickoff_prompt`) so the model greets him; it lands in the
conversation buffer as a user line, and the memory's ledger of the day must not open an episode with it. Which line
is that note is a fact of the LANGUAGE PACKS, so it lives here: `nucleo/turn/kickoff` and `memory/history` both read
this door, and the memory needs no import of the brain to know it (A7 had put the one catalog in `nucleo/turn`).
"""
from __future__ import annotations

_CATALOG: frozenset[str] | None = None


def _norm(s: str) -> str:
    return " ".join(str(s or "").split())


def catalog() -> frozenset[str]:
    """Every language's kickoff note, whitespace-normalised, cached once per process."""
    global _CATALOG
    if _CATALOG is None:
        try:
            from i18n import langs as _langs
            _CATALOG = frozenset(_norm(sp.kickoff_prompt) for sp in _langs.supported() if sp.kickoff_prompt)
        except Exception:  # noqa: BLE001 — without the catalog nothing is a kickoff
            _CATALOG = frozenset()
    return _CATALOG


def is_kickoff(line: str) -> bool:
    """Is this line the first-turn note (any language)? Exact, whitespace-blind; nothing he can type matches it."""
    t = _norm(line)
    return bool(t) and t in catalog()


def reset_cache() -> None:
    """Forget the cached catalog (a language pack changed; tests)."""
    global _CATALOG
    _CATALOG = None
