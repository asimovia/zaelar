"""The agent's default name — a per-language catalogue in the genome, read here and nowhere else.

`nucleo/genesis.json › persona` carries two things:

  · `name`     — `{lang: name, "*": fallback}`. An install is born with the name of its language's row, or the `*` row.
                 Another language gets its own name by adding a row: data, never code.
  · `heard_as` — `{name: [spellings]}`: what a speech recogniser writes when it hears that name, in the languages the
                 engine ships. While the agent goes by that name, every spelling is also its wake word — the name is
                 chosen for how it SOUNDS, so the spelling the STT happens to pick must not decide whether it answers.

A name the operator gives the agent is personal (`state.assistant_name`, memory) and always wins; this module only says
what the agent is called when nobody has named it. `LEGACY_DEFAULT` is the default an older install had stamped into
its state before this catalogue existed: it was never chosen, so it reads as «not named».
"""
from __future__ import annotations

import unicodedata

#: What every reader falls back to when the genome cannot be read at all — the same value the `*` row ships.
FALLBACK = "Johnny"
#: The factory default before the catalogue (stamped into every older state row by `memory.state.write`).
LEGACY_DEFAULT = "Zaelar"

_memo: dict = {"mtime": None, "persona": {}}


def _persona() -> dict:
    """The `persona` section, re-read only when genesis.json changes (it is asked on hot paths)."""
    from . import GENESIS, genesis
    try:
        mtime = (str(GENESIS), GENESIS.stat().st_mtime_ns)
    except OSError:
        mtime = (str(GENESIS), -1)
    if _memo["mtime"] != mtime:
        sec = (genesis() or {}).get("persona")
        _memo.update(mtime=mtime, persona=sec if isinstance(sec, dict) else {})
    return _memo["persona"]


def norm(text: str) -> str:
    """Lowercase, accent-free — the same normalisation the wake-word gate applies."""
    s = unicodedata.normalize("NFD", str(text or "")).encode("ascii", "ignore").decode("ascii")
    return s.lower().strip()


def default_name(lang: str | None = None) -> str:
    """The name an install in `lang` (default: the active language) is born with."""
    if lang is None:
        try:
            from i18n import langs as _langs
            lang = _langs.current_code()
        except Exception:  # noqa: BLE001 — no readable language: the `*` row
            lang = ""
    base = str(lang or "").split("-")[0].lower()
    names = _persona().get("name")
    names = names if isinstance(names, dict) else {}
    return str(names.get(base) or names.get("*") or FALLBACK).strip() or FALLBACK


def is_default(name: str | None, lang: str | None = None) -> bool:
    """Is `name` the agent's unnamed state — empty, the catalogue's name, or the legacy default?"""
    n = norm(name or "")
    return not n or n in (norm(default_name(lang)), norm(LEGACY_DEFAULT))


def chosen(name: str | None) -> str:
    """The stored name if somebody CHOSE it, else '' — the legacy default was never a choice."""
    n = str(name or "").strip()
    return "" if not n or norm(n) == norm(LEGACY_DEFAULT) else n


def heard_as(name: str) -> tuple[str, ...]:
    """The spellings an STT produces for `name`, normalised (the name itself first). Unknown name → just itself."""
    key = norm(name)
    if not key:
        return ()
    table = _persona().get("heard_as")
    table = table if isinstance(table, dict) else {}
    out = [key]
    for k, spellings in table.items():
        if norm(k) == key and isinstance(spellings, list):
            out.extend(norm(s) for s in spellings if norm(s) and norm(s) not in out)
    return tuple(out)


def wake_table() -> dict[str, list[str]]:
    """`{name: [spellings]}`, normalised — what a client-side ear needs to answer to every spelling of a name."""
    table = _persona().get("heard_as")
    table = table if isinstance(table, dict) else {}
    return {norm(k): list(heard_as(k)[1:]) for k in table if norm(k)}
