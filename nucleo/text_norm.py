"""nucleo/text_norm.py — the text normalisation every deterministic guard runs on.

Extracted from `router_guards.py` (2026-09-02, architecture ratchet) because it is the one piece BOTH halves
of that file need: the reminder/agenda guards that moved to `reminder_guards.py` and the routing guards that
stayed. Keeping it in either one would have made the other import it back, which is a cycle papered over with
a function-local import — the exact debt the ratchet counts.

`delivery.py` was already reaching into `router_guards` for `_norm_txt`, which is the smell that says this was
never a router concern to begin with: it is what «the same words» means in this codebase — accents stripped,
lowercased — so that a guard compares meaning and not typography.

Nothing here decides anything. No I/O, no state, no imports beyond the standard library.
"""
import re as _re


def _norm_txt(text: str) -> str:
    import unicodedata as _ud
    n = _ud.normalize("NFKD", text or "")
    return "".join(c for c in n if not _ud.combining(c)).lower()
_STOPWORDS = frozenset({"el", "la", "los", "las", "un", "una", "de", "del", "al", "que", "y", "a", "en",
                        "mi", "tu", "su", "the", "a", "an", "of", "to", "my", "your"})
_CLAUSE_SPLIT_RE = _re.compile(r"[,;.!?\n]|\sy\s|\sand\s", _re.I)
# The words that only DATE something and never describe it. Needed to answer one question: does this clause say
# anything BESIDES when?
_DATE_ONLY_WORDS = frozenset({
    "lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "manana", "tomorrow", "hoy", "today", "dia", "day", "esta", "este", "proximo", "proxima", "que", "viene",
})