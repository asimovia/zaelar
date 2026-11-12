"""The FIRST TURN of a session is a system note, and there is ONE text for it (A7, 2026-11-12).

Measured on the operator's own first dialogue: the voice process composed an English greeting
instruction, the admission threw it away for the i18n `kickoff_prompt`, and that second text — «introduce yourself
in one line and ask me my name» — was then kept in the dialog window and in the short-term buffer AS HIS WORDS. On
the second turn the model read the order to introduce itself twice, beside his «pepe», and greeted him again.

So the kickoff is one line of i18n data (`kickoff_prompt`, per language), read here by every piece that needs it:
the voice process that triggers the greeting, the gate that recognises a first turn, the window that must not keep
it as his, and the ledger that must not open an episode with it. What the greeting SAYS is not in this note: the
introduction phase (`nucleo/turn/prompt/packs/introduction.py`) carries that, as a system block.
"""
from __future__ import annotations

_CATALOG: frozenset[str] | None = None


def _norm(s: str) -> str:
    return " ".join(str(s or "").split())


def text(lang=None) -> str:
    """The kickoff note in the session's language (or `lang`'s): the user-role line that opens a session."""
    try:
        if lang is None:
            from i18n import langs as _langs
            lang = _langs.current_language()
        return str(getattr(lang, "kickoff_prompt", "") or "")
    except Exception as e:  # noqa: BLE001 — a session with no readable language still opens
        from loguru import logger
        logger.debug(f"kickoff: no language to read the note from ({e!r})")
        return ""


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


def _reset_for_tests() -> None:
    global _CATALOG
    _CATALOG = None
