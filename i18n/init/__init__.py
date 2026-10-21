"""
i18n.init — the INITIALIZATION side of the multilingual subsystem (V2-089).

Everything here PREPARES a language: it may call an LLM, can take a while, and runs only at boot / first-run /
language-switch / upgrade — behind the 'preparing language' veil. It is strictly separated from i18n.runtime and
i18n.langs (the hot path that just reads already-prepared packs).

`prepare(code)` is THE single idempotent entry: it walks `i18n.packs.PACKS` in order and makes every pack of the
language complete. `pending(code)` says, with file reads only, which of them still have work — the preparing
screen's denominator, and the reason it shows nothing at all for a language that is already ready.
"""
from __future__ import annotations

from loguru import logger

from i18n import packs as _packs
from i18n.init.ensure import ensure_language, ensure_pack, missing


def _has(name: str, code: str) -> bool:
    return bool(_packs.generated(name, code))


def pending(code: str) -> list[str]:
    """The packs `code` still has to generate (empty for a shipped language or a complete one)."""
    code = (code or "").strip().lower()
    if code in _packs.PRESET:
        return []
    out = []
    for p in _packs.PACKS:
        if p.name in ("smalltalk", "aliases"):
            if not _has(p.name, code):
                out.append(p.name)
        elif missing(code, p.name):
            out.append(p.name)
    return out


async def _generate(code: str, name: str) -> dict:
    if name == "smalltalk":
        from i18n.init.smalltalk import ensure_smalltalk
        return await ensure_smalltalk(code)
    if name == "aliases":
        from i18n.init.aliases import ensure_aliases
        return await ensure_aliases(code)
    return await ensure_pack(code, name)


async def prepare(code: str, on_step=None) -> dict:
    """Make every pack of `code` ready, in `PACKS` order. Idempotent — a no-op for presets and complete languages.
    `on_step(name)` is called after each pack that HAD work. Returns {code, packs: {name: result}}."""
    code = (code or _packs.BASE).strip().lower()
    todo = pending(code)
    results: dict = {}
    for name in todo:
        try:
            results[name] = await _generate(code, name)
        except Exception as e:  # noqa: BLE001 — one pack failing must not leave the others ungenerated
            logger.warning(f"i18n.init: '{code}' {name} failed: {str(e)[:160]}")
            results[name] = {"error": str(e)[:160]}
        if on_step:
            on_step(name)
    if todo:
        try:
            from i18n import langs as _langs, runtime as _rt
            _langs.invalidate()
            _rt.invalidate()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"i18n.init: could not drop the language caches: {e}")
    return {"code": code, "packs": results}


__all__ = ["prepare", "pending", "ensure_language", "ensure_pack"]
