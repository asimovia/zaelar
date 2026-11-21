"""ONE typed line at the text channel's HTTP door, through the conversation manager (INI-078 F2: the only path).

`run_turn` hands his line to the manager's typed entry (`conversation_host/entry.typed_and_wait`) and returns what the
conversation answered. When the manager may not answer now (its switch says why), the reason is the answer and nothing
else answers.
"""
from __future__ import annotations


async def run_turn(text: str, *, sid: str = "default", ingest: bool = True, model: str = "", execute: bool = False,
                   door: bool = True) -> dict:
    """His line through the conversation manager. `ingest`, `model`, `execute` and `door` are accepted for the HTTP
    face's callers: the manager decides with its own model and its own doors."""
    from nucleo.conversation_host import entry as _conv_entry, switch as _conv_switch
    text = (text or "").strip()
    if not text:
        return {"ok": False, "error": "texto vacío"}
    if not _conv_switch.on():                # it may not answer now: the reason, and nothing else answers
        return {"ok": False, "error": _conv_switch.decide().why or "the conversation cannot answer now"}
    got = await _conv_entry.typed_and_wait(text, dev=f"text:{sid}")
    return {"ok": False, "error": "the conversation could not open"} if (got.get("conv") or {}).get(
        "close") == _conv_entry.NOT_OPENED else got
