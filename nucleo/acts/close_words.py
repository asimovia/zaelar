"""Does a sentence NEGATE a close or narrate one already done (V2-631/V2-678)? Grammar, not intent (V2-095), read by
the interrupt grammar's close-ALL door. A miss here is not a missed order, it is a destroyed desktop — so a negated or
narrated close never counts as one. (The positive half — «does it order a close» — was the old canvas licence's and
went with it, INI-078 L1.)
"""
from __future__ import annotations

import re as _re

from nucleo.text_norm import _norm_txt

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

    For callers with their OWN close vocabulary — `voice/attention.py`'s close-ALL door knows verbs this module
    does not («limpia el escritorio»), so it needs the veto alone (found by its own test, V2-678).
    """
    n = _norm_txt(text)
    return bool(_NO_CLOSE_RE.search(n) or _NARRATED_CLOSE_RE.search(n))

