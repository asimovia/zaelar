"""nucleo/self/about.py — the agent answers a question about ITSELF from its own catalogue (V2-932).

Measured 2026-11-17: with the camera's «look at me» ON, the agent said «te veo» and nine seconds later «no tengo cámara».
Nothing in the turn said what the agent is: the mission names it, the tool schemas say what each tool does, a few state
lines say a mode — and a first-time question («what can you do?», «how do I make you listen only to your name?», «can
you see me?», «where do I connect my email?») was answered from whatever the model guessed.

`about_self(topic, question)` is that door, `read_widget`'s sibling in shape: a LIGHT two-pass route resolved in the
turn. The model picks the TOPIC by function call — a closed enum of the catalogue's ids, so any language reaches it and
no word of his sentence is read here — and the second pass answers from the entry's words in his language (the `self`
pack) plus the live facts that entry names (`snapshot.fields`). Nothing is paid on a turn that does not ask: the tool
schema is the only per-turn cost.
"""
from __future__ import annotations

import json
import time
from functools import lru_cache
from pathlib import Path

from loguru import logger

CATALOG = Path(__file__).resolve().parent / "catalog.json"


@lru_cache(maxsize=1)
def catalog() -> tuple[dict, ...]:
    return tuple(json.loads(CATALOG.read_text(encoding="utf-8"))["entries"])


def topics() -> list[str]:
    return [e["id"] for e in catalog()]


def entry(topic: str) -> dict:
    """The entry for `topic`; an id the catalogue does not hold reads as the overview (never an error in a turn)."""
    t = str(topic or "").strip().lower()
    return next((e for e in catalog() if e["id"] == t), catalog()[0])


def declared_needs() -> set[str]:
    return {n for e in catalog() for n in e.get("needs") or ()}


def words(code: str | None = None) -> dict:
    """The `self` pack in his language (a generated language reads English where it has no string yet)."""
    from i18n import langs, packs
    c = (code or getattr(langs.current_language(), "code", "") or packs.BASE).strip().lower()
    return packs.read("self", c) or packs.read("self", packs.BASE) or {}


TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "about_self",
        "description": ("ANTES de contestar cualquier pregunta sobre TI (qué eres o sabes hacer, cómo se hace algo tuyo "
                        "por voz o botón, ¿me ves?, ¿dónde vives?): tu ficha y tu estado reales, en este turno. No "
                        "cambia nada."),
        "parameters": {
            "type": "object",
            "properties": {"topic": {"type": "string", "enum": topics()}, "question": {"type": "string"}},
            "required": ["topic"],
        },
    },
}


def compose_system(lang_lock: str, operator_text: str, topic: str, question: str = "", code: str | None = None) -> str:
    """The second pass's system prompt: the entry's words and its live facts are the ONLY source."""
    from nucleo.self import snapshot
    w = words(code)
    c = w.get("compose") or {}
    e = entry(topic)
    text = ((w.get("topics") or {}).get(e["id"])
            or (words("en").get("topics") or {}).get(e["id"]) or {})
    card = "\n".join(f"{c.get(k) or k}: {text[k]}" for k in ("what", "voice", "button", "not") if text.get(k))
    facts = snapshot.fields(e.get("needs") or ())
    asked = [f"{c.get('his_words') or 'HIS WORDS'}: {operator_text}",
             f"{c.get('asked') or 'LOOKED UP'}: {question}" if question and question != operator_text else ""]
    parts = [(lang_lock or "").rstrip(), str(c.get("task") or ""), "\n".join(x for x in asked if x),
             f"{str(c.get('entry') or '{topic}').format(topic=e['id'])}:\n{card}",
             f"{c.get('live') or 'LIVE'}:\n{snapshot.render(facts)}" if facts else ""]
    return "\n\n".join(p for p in parts if p)


async def prepare(args: dict, operator_text: str, lang_lock: str, emit) -> str:
    """Resolve → read → observe → compose, off the event loop (the readers touch files and the connector registry)."""
    import asyncio
    t0 = time.time()
    topic, question = str(args.get("topic") or ""), str(args.get("question") or "")
    system = await asyncio.to_thread(compose_system, lang_lock, operator_text, topic, question)
    try:
        emit("brain", "🪞 about_self (tool del modelo)", role="system", text=f"{entry(topic)['id']} ← {question or operator_text[:80]}",
             extra={"cat": "flash", "topic": entry(topic)["id"], "asked": topic, "read_ms": round((time.time() - t0) * 1000),
                    "chars": len(system)})
    except Exception as e:  # noqa: BLE001 — the trace never decides the answer
        logger.warning(f"about_self: trace not emitted ({e!r})")
    return system
