"""The CLOSE-order grammar (V2-045/V2-567/V2-600/V2-631/V2-678): does a sentence ORDER a close, negate one or narrate
one already done? Grammar, not intent (V2-095): a closed set of verb forms over the shared normalizer, read by the one
canvas licence (`acts/canvas.close_ordered`, `show_under_close`) and by the interrupt grammar's close-ALL door. A miss
here is not a missed order, it is a destroyed desktop — so a negated or narrated close never counts as one.
"""
from __future__ import annotations

import re as _re

from nucleo.text_norm import _norm_txt

_CLOSE_VERB_RE = _re.compile(r"\b(cierr\w*|cerr\w*|ocult\w*|escond\w*|apag\w*|quit\w*|close|hide|turn\s+off)\b")
_DELETE_VERB_RE = _re.compile(r"\b(borr|elimin|delete|remove|deshaz)\w*")
# Negated close: "no cierres / no lo cierres / don't close" — must not count as close (prevents doing the
# opposite).
#
# V2-678 — the English half was the contraction ALONE, so «Do not close the widgets.» read as a close ORDER,
# and through `hard_interrupt` (which has no negation check of its own) it wiped the canvas. Measured live
# 2026-09-12 (session 352268b5, 10:59:51): «I said reposition widgets. Do not close the widgets.» →
# `✋ interrupción dura atendida` → every card gone, on the sentence that said not to. Reproduced standalone.
# Same asymmetry V2-677 found in the request verbs, now in the guard that exists to prevent damage: a miss
# here is not a missed order, it is a destroyed desktop.
_NO_CLOSE_RE = _re.compile(
    r"\bno\s+(?:me\s+|lo\s+|la\s+|los\s+|las\s+)?(?:cierr\w*|ocult\w*|escond\w*|apagu\w*|quit\w*)\b"
    r"|\b(?:do\s+not|don'?t|never|please\s+do\s*n'?o?t)\s+(?:\w+\s){0,2}?"
    r"(?:close|hide|shut|remove|clear)\b")
# A close VERB FORM that cannot be an order (V2-631). Measured live 2026-09-09 (session 7be94951): the close
# backstop closed the music card TWICE — killing the audio, which lives inside that card — on turns that only
# MENTIONED closing: «¿Van a cerrar anuncios?» (a question about ads; «van a cerrar» has somebody else as its
# subject) and «No sigue sonando porque has cerrado el widget de música.» (a complaint narrating a close that
# already happened — and the guard's True also made the show-under-close rule discard the show_widget the
# model had CORRECTLY called to reopen it). Grammar, not intent (V2-095): a participle after «haber» / «you've»
# narrates the past, and «va(n) a <infinitive>» is third-person — neither can be an order addressed to zaelar.
# These spans are STRIPPED before testing, not used to veto: «has cerrado el widget; ciérralo otra vez» keeps
# its close because the imperative survives the strip.
_NARRATED_CLOSE_RE = _re.compile(
    r"\b(?:has|ha|han|habias?|habian|habeis|hemos)\s+(?:\w+\s)?(?:cerrado|ocultado|escondido|apagado|quitado)\b"
    r"|\b(?:va|van)\s+a\s+(?:cerrar|ocultar|apagar|quitar)\w*\b"
    r"|\byou(?:'?ve| have)\s+(?:closed|hidden)\b|\bthey(?:'?re| are|'?ll| will)\s+(?:going\s+to\s+)?close\b")


def is_negated_or_narrated(text: str) -> bool:
    """True when this text NEGATES a close («do not close the widgets») or NARRATES one already done.

    Exported for callers with their OWN close vocabulary — `voice/attention.py`'s close-ALL door knows
    verbs this module does not («limpia el escritorio»), so it needs the veto WITHOUT the positive half.
    Using `looks_like_close` there would have silently dropped every verb the two lists do not share, which
    is how a guard becomes a regression (found by its own test, V2-678).
    """
    n = _norm_txt(text)
    return bool(_NO_CLOSE_RE.search(n) or _NARRATED_CLOSE_RE.search(n))


def looks_like_close(text: str) -> bool:
    """True if the turn asks to CLOSE (hide) a widget, NOT delete it. EXECUTION GUARD for delete_widget (V2-045,
    V2-017 invariant 'cerrar ≠ borrar'): the non-reasoning model sometimes chooses delete_widget for 'cierra el
    widget de X'; deletion is FOREVER and closing is reversible → with a close verb and NO delete verb, it is a
    close. Deterministic and accent-free (the input is normalized). Ignores NEGATION ('no cierres') and NARRATED
    closes ('has cerrado el widget', '¿van a cerrar anuncios?') — see _NARRATED_CLOSE_RE."""
    n = _norm_txt(text)
    if _DELETE_VERB_RE.search(n) or _NO_CLOSE_RE.search(n):
        return False
    n = _NARRATED_CLOSE_RE.sub(" ", n)
    return bool(_CLOSE_VERB_RE.search(n))


def whole_canvas_close(text: str) -> bool:
    """The hard-interrupt reader's close of the WHOLE canvas («clear everything off the screen») — read by the close
    licence beside `looks_like_close`, which alone vetoed the engine's own close as drag (node 2.925)."""
    try:
        from voice import attention as _att
        return _att.hard_interrupt(text) == "close"
    except Exception as e:  # noqa: BLE001 — an unreadable reader leaves the narrower grammar's verdict as it was
        return __import__("loguru").logger.debug(f"close_words: whole-canvas reader unreadable — {e}") or False
