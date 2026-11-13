"""nucleo/flash/spoken_lang.py — what the MOUTH says to him goes in the session's language (V2-781).

A widget's refusal copy, a worker's note or a composed delivery line can come out in the other product language
(«Ya está en tu pantalla…» to an English session). These readers ask whether a line WE are about to say reads as
the other of the two product languages, and translate it once. Only es↔en is told apart; too few words to tell is
left alone. Never raises.

What LEAVES the machine is never read here (V2-903 P1-1): a text his yes approved, or his own dictated words, reach
the card's door byte-identical — CRIT-T2e «his words, in order». The send-door translation that lived in this module
as `outgoing_lang.in_session_language` (demo pass 106) was retired: it rewrote an irreversible act after consent.
"""
from __future__ import annotations

import re

_MARKERS = {
    "es": {"el", "la", "los", "las", "que", "de", "del", "y", "con", "para", "por", "ya", "estamos", "así", "una",
           "un", "es", "está", "nos", "vemos", "hola", "oye", "mañana", "hora", "adelante", "reserva", "gracias",
           # V2-781: what a widget's refusal is made of («No encuentro ese vídeo en la lista» had one marker)
           "ese", "esa", "hay", "más", "nada", "encuentro", "dime", "qué", "cuál", "vídeo", "vídeos", "lista",
           "vacía", "puedo", "tengo"},
    "en": {"the", "and", "we", "we're", "already", "to", "of", "is", "are", "it", "you", "with", "for", "see",
           "tomorrow", "hey", "hi", "thanks", "please", "go", "ahead", "book", "our", "your", "at"},
}
_MIN_MARKERS = 2


def language_of(text: str) -> str:
    """"es", "en", or "" when the text does not say."""
    words = re.findall(r"[a-záéíóúñü']+", str(text or "").lower())
    es = sum(w in _MARKERS["es"] for w in words)
    en = sum(w in _MARKERS["en"] for w in words)
    if max(es, en) < _MIN_MARKERS or es == en:
        return ""
    return "es" if es > en else "en"


#: Off inside the suite (tests/conftest.py), like `spoken_delivery.LIVE`: a reply door must not reach the network.
LIVE = True


async def _translate(text: str, lang_name: str) -> str:
    if not LIVE:
        return ""
    from nucleo.llm.fast_client import FastClient
    out = await FastClient().complete(
        [{"role": "system", "content": f"Translate the message into {lang_name}. Keep names, numbers, times and the "
                                       f"tone. Answer with the translated message only."},
         {"role": "user", "content": text}],
        max_tokens=300, no_thinking=True)
    return str(out or "").strip().strip("«»\"")


def foreign_to_session(text: str) -> bool:
    """True when `text` reads as the OTHER product language — the synchronous check, so a caller whose await points
    matter (the proactive delivery queue) only yields when there is something to translate."""
    try:
        from i18n import langs as _lg
        code = str(_lg.current_code() or "").lower()[:2]
        return code in _MARKERS and language_of(text) not in ("", code)
    except Exception:  # noqa: BLE001
        return False


async def said_in_session_language(text: str) -> str:
    """`text` (a reply or a spoken notice) in the session's language — «I'm in Madrid» turned an English session
    Spanish (V2-781). Only es↔en, too few words to tell is left alone."""
    try:
        from i18n import langs as _lg
        code = str(_lg.current_code() or "").lower()[:2]
        if code in _MARKERS and language_of(text) not in ("", code):
            t = await _translate(text, _lg.spec(code).name)
            if t and language_of(t) != language_of(text):
                _note("reply", "say", text, t)
                return t
    except Exception as e:  # noqa: BLE001
        _note("reply", "say", "", f"translation skipped: {type(e).__name__}")
    return text


def _note(widget_id: str, action: str, before: str, after: str) -> None:
    try:
        from voice.observer import emit
        emit("brain", "🌐 lo que se dice, en el idioma de la sesión", role="system", text=f"{before[:80]} → {after[:80]}",
             extra={"cat": "flash", "id": widget_id, "action": action})
    except Exception as e:  # noqa: BLE001
        from loguru import logger
        logger.debug(f"spoken_lang note: {e}")
