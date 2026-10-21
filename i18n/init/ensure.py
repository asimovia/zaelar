"""
i18n.init.ensure — the idempotent readiness check of a TRANSLATED pack (V2-089; every pack since 2026-10-21).

ONE function, run at boot / after a language switch / after an upgrade: does the language have every string of
the English pack at its CURRENT English source? If yes → instant no-op. If not (brand-new language, or new keys
shipped in an update), translate JUST the missing/changed strings with the LLM and persist them. First-run and
upgrade take the exact same path — the difference is only how many strings are missing.

A pack is flattened to its string leaves («mute_lines.2», «chat.send») so the UI table and the agent's spoken
table go through the same diff and the same translator; what is not a string (flags, numbers) is never sent.

This is INITIALIZATION, not execution: it may call an LLM and take a few seconds, so callers gate it behind the
'preparing language' veil. The hot path (i18n.runtime, i18n.langs) never touches this.
"""
from __future__ import annotations

from loguru import logger

from i18n import packs as _packs, runtime as _rt, store as _store


def manifest(name: str) -> dict[str, str]:
    """The English strings of a pack, flat: {path: english}."""
    return _rt.manifest() if name == "ui" else _packs.texts(name, _packs.preset(name, _packs.BASE))


def missing(code: str, name: str) -> list[str]:
    """Strings `code` still needs in pack `name`: absent, or whose English changed since it was translated."""
    code = (code or _packs.BASE).strip().lower()
    if code in _packs.PRESET:
        return []
    man = manifest(name)
    gen = _store.read(code, name)
    strings, src = gen.get("strings") or {}, gen.get("src") or {}
    return [k for k, en in man.items() if k not in strings or src.get(k) != en]


async def ensure_pack(code: str, name: str) -> dict:
    """Make pack `name` of `code` complete against English. Returns {code, pack, generated, total, missing_before}."""
    code = (code or _packs.BASE).strip().lower()
    man = manifest(name)
    todo = missing(code, name)
    if not todo:
        return {"code": code, "pack": name, "generated": 0, "total": len(man), "missing_before": 0}

    logger.info(f"i18n.init: '{code}' {name} missing {len(todo)}/{len(man)} strings — generating…")
    from i18n.init import generate
    translated = await generate.translate(code, {k: man[k] for k in todo},
                                          register="ui" if name == "ui" else "speech")
    gen = _store.read(code, name)
    strings, src = dict(gen.get("strings") or {}), dict(gen.get("src") or {})
    for k, v in (translated or {}).items():
        if isinstance(v, str) and v.strip():
            strings[k] = v
            src[k] = man[k]                       # snapshot the English we translated FROM (upgrade diff)
    _store.save(code, _rt.MANIFEST_VERSION, strings, src, name=name)
    logger.info(f"i18n.init: '{code}' {name} generated {len(translated or {})} strings.")
    return {"code": code, "pack": name, "generated": len(translated or {}), "total": len(man),
            "missing_before": len(todo)}


async def ensure_language(code: str) -> dict:
    """The UI pack — the historical name every caller of the first version still uses."""
    return await ensure_pack(code, "ui")
