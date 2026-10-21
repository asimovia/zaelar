"""
i18n.store — persistence of the GENERATED `ui` pack (V2-089), on top of `i18n.packs`.

Preset UI strings (en/es) are DATA in the repo at i18n/genesis/<code>/ui.json. GENERATED ones (any other language
the LLM produced) are RUNTIME data in the workspace — `<workspace>/i18n/generated/<code>/ui.json` — written by
i18n.init and read by i18n.runtime. The paths themselves are `i18n.packs`'s, the one place that knows them.

A generated pack on disk (every pack, not only this one):
  {"version": <manifest version it was built at>,
   "strings": {key: translated-text},
   "src":     {key: the ENGLISH text it was translated FROM}}   ← lets the upgrade diff detect changed sources
"""
from __future__ import annotations

from pathlib import Path

from i18n import packs as _packs


def _path(code: str) -> Path:
    return _packs.generated_path(code, "ui")


def read(code: str, name: str = "ui") -> dict:
    """The generated pack for `code` (or {} if it hasn't been generated yet)."""
    return _packs.generated(name, code)


def save(code: str, version: int, strings: dict, src: dict, name: str = "ui") -> None:
    """Persist a generated pack atomically so a crash mid-write can't corrupt it."""
    _packs.write_json(_packs.generated_path(code, name), {"version": version, "strings": strings, "src": src})


def codes() -> list[str]:
    """Language codes that have something generated on disk."""
    return _packs.generated_codes()
