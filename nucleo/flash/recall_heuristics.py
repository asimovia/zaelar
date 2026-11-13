"""nucleo/flash/recall_heuristics.py — the recency trigger (split out of prompt.py, 2026-08-17 modularization pass).
`needs_recent()` decides whether the expanded recent-conversation block rides the turn; `compose_recent_block()`
composes it. The durable recall's regex router (`needs_recall`, ~150 expressions) went in V2-903: the recall starts
beside the brief and the brief decides whether the turn waits for it (`nucleo/turn/recall_ahead`). Both are pure text
classifiers plus one self-contained memory read — no dependency on prompt.py's ESTADO-composition machinery
(state/tools/widgets), which is why the audit that led to this split found them a clean, separable concern.

Its callers (the voice turn's `turn_prompt`, the typed CLI, the benches) import it by name from here."""
from __future__ import annotations

import re as _re
import unicodedata as _ud


def _norm(text: str) -> str:
    n = _ud.normalize("NFKD", text or "")
    n = "".join(c for c in n if not _ud.combining(c)).lower()
    return n.replace("'", "").replace("’", "")


# A THREAD POSITION, not a durable memory — "four messages behind", "previous messages", "ese mensaje".
# fix02 (session 6d19df41): «Can you reveal the tongue? It's four messages behind.» sent the recall tool
# after durable pills for something that lives in the LIVE thread, and the empty result came back
# narrated as no-access («I can't reveal any hidden message... secret information»). Pills can never
# answer a thread position, so composing from their emptiness only manufactures refusals: the recall
# second passes skip the compose there instead (voice asks which message, probe keeps its reply).
# Structural (cardinal/ordinal + message + positional, or a demonstrative message), es/en — never a verb
# list, never the topic (tongues, hotels and restaurants all pass through the same door).
# `anterior(es)?`, never `anteriores?` — the latter is "anteriore"+optional s and can only ever match the
# PLURAL. Measured 2026-09-20 reviewing this guard: «el mensaje anterior», the most natural Spanish way to
# point one message back, fell straight through it while «mensajes anteriores» was caught.
_THREAD_POS_RE = _re.compile(
    r"\b(\d+|one|two|three|four|five|few|couple|un|una|dos|tres|cuatro|cinco|par)\s+"
    r"(messages?|mensajes?)\s+(behind|back|ago|down|before|atras|antes|anterior(?:es)?)\b"
    r"|\b(previous|last|that|those|anterior(?:es)?|es[eo]s?)\s+(messages?|mensajes?)\b"
    r"|\bmensajes?\s+(anterior(?:es)?|previos?|de\s+antes)\b"
    r"|\b(ese|esa|aquel|aquella)\s+mensaje\b", _re.I)


def names_thread_position(text: str) -> bool:
    """True when the turn points at a position in the LIVE message thread — something durable memory
    can never resolve. See `_THREAD_POS_RE` (fix02)."""
    n = _norm(text or "")
    return bool(n.strip()) and bool(_THREAD_POS_RE.search(n))


# Saludos / asentimientos / charla trivial — NUNCA disparan recall (no hay nada que recordar).
_TRIVIAL_RE = _re.compile(
    r"^\s*[¿¡]?\s*("
    r"hola|buenas|buenos dias|buenas tardes|buenas noches|hey|holi|ey|"
    r"que tal( estas| andas| va| te va| todo)?|que pasa|que hay|como estas|como andas|como va( todo)?|todo bien|"
    r"vale|ok|okay|oka|de acuerdo|entendido|perfecto|genial|estupendo|guay|dale|hecho|"
    r"gracias|muchas gracias|mil gracias|gracias tio|de nada|"
    r"si|no|claro|sip|nop|ajam|aja|ya|nada|bueno|"
    r"adios|chao|hasta luego|hasta pronto|hasta manana|nos vemos|buenas noches"
    r")\b[\s!.,¿?¡]*$"
)

# CIRCUITO DE CORTO PLAZO (C, 2026-07-14): el turno referencia la INTERACCIÓN RECIENTE (no un dato durable de
# memoria — eso es el recall durable, `nucleo/turn/recall_ahead`), p. ej. "lo que te dije antes", "de qué hablábamos", "repite eso", "hace un
# rato", "vuelve a lo de antes". Dispara el 2º pase de CORTO que inyecta el buffer conversacional AMPLIADO
# (verbatim, más turnos que la ventana normal) fuera del event loop. es/en, determinista.
_RECENT_RE = _re.compile(
    r"\b(antes|hace\s+(un\s+)?(rato|momento|un\s+momento|nada|poco)|hace\s+un\s+par\s+de|anteriormente|"
    r"reci[eé]n|dec[ií]amos|dec[ií]as|dije|dijiste|dijimos|hablamos|habl[aá]bamos|coment[eé]|comentaste|"
    r"mencion[eé]|mencionaste|lo\s+de\s+antes|eso\s+[uú]ltimo|lo\s+[uú]ltimo|retoma|retomamos|vuelve\s+a\s+lo|"
    r"como\s+te\s+dije|como\s+dec[ií]a|rep[ií]te(lo|melo)?|otra\s+vez\s+(eso|lo)|"
    r"earlier|a\s+moment\s+ago|(just|right)\s+now|we\s+(were\s+)?(talking|said|discussed)|"
    r"(you|i)\s+said|as\s+i\s+said|repeat\s+that|go\s+back\s+to|"
    # V2-865 — «I did explain that some messages ago today» fired nothing: the English side knew «earlier» and
    # «you said» but not a span of messages, minutes or hours, nor «explained / told you / asked you».
    r"(some|a\s+few|\d+)\s+(messages?|turns?|minutes?|hours?)\s+ago|(some\s+time|a\s+while|ages)\s+ago|"
    r"(i|we)\s+(did\s+)?(explain(ed)?|told|ask(ed)?)|"
    r"told\s+you|asked\s+you|te\s+(ped[ií]|expliqu[eé]|cont[eé]|coment[eé])|"
    r"te\s+he\s+(dicho|pedido|contado|explicado)|hace\s+(unas\s+)?horas|hace\s+(unos\s+)?minutos|"
    # «the one you found yesterday evening» (2026-11-09): a part of the day named, or what zaelar itself found.
    r"yesterday|last\s+night|this\s+(morning|afternoon|evening)|you\s+(found|played|searched|looked\s+up)|"
    r"ayer|anoche|esta\s+(mañana|tarde|noche)|(que\s+)?(encontraste|pusiste|buscaste))\b", _re.I
)


def needs_recent(text: str) -> bool:
    """True si el turno referencia la INTERACCIÓN RECIENTE (corto plazo) más allá de lo que ya cabe en la ventana
    → dispara `compose_recent_block` (2º pase, fuera del loop). Distinto del recall durable (dato DURABLE por
    significado, vía embeddings): esto es "de qué hablábamos / lo que te dije antes / repite eso". Sesga a NO
    disparar en charla trivial (coste de FP: una lectura directa µs que el modelo ignora)."""
    n = _norm(text or "")
    if not n.strip() or _TRIVIAL_RE.match(n):
        return False
    return bool(_RECENT_RE.search(n))


def compose_recent_block(limit: int = 20, max_chars: int = 2200) -> str:
    """2º PASE DE CORTO PLAZO: el buffer conversacional AMPLIADO (más turnos/chars que la ventana normal de 10),
    verbatim, para cuando el operador referencia algo reciente ("de qué hablábamos", "lo que te dije antes").
    Lectura DIRECTA (µs, sin LLM ni retriever) desde `memory.recent_window`. Devuelve un bloque etiquetado listo
    para el prompt, o '' si no hay conversación. El llamador lo corre FUERA del event loop (respeta V2-011)."""
    try:
        from memory import api as memory
        turns = memory.recent_window(limit=limit, max_chars=max_chars)
    except Exception:
        return ""
    if not turns:
        return ""
    lines = []
    for t in turns:
        who = "Operador" if t.get("role") == "user" else "zaelar"
        c = (t.get("content") or "").strip().replace("\n", " ")
        if c:
            lines.append(f"· {who}: {c}")
    if not lines:
        return ""
    return ("── CONTEXTO RECIENTE AMPLIADO (lo que habéis hablado hace un rato; el operador se refiere a esto) ──\n"
            + "\n".join(lines))
