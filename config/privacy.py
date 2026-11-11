"""config/privacy.py — the person's permission switches (V2-875), cheap enough for every event.

The switches live in `config/v2` section `privacy` (`location`, `files`, `observability`, `obfuscate`), written by the
config dialogs through `POST /api/config/v2`. The hot paths (every persisted event) read them here: the section is
re-read only when the store file's stamp changes, so a flip applies on the next event without a JSON parse per event.
A store that cannot be read gives the defaults — the documented, privacy-first values.
"""
from __future__ import annotations

from config import v2

_cache: dict = {"stamp": False, "val": None}


def _section() -> dict:
    try:
        st = v2._PATH.stat()
        stamp = (st.st_mtime_ns, st.st_size)
    except OSError:
        stamp = None
    if stamp != _cache["stamp"] or _cache["val"] is None:
        try:
            _cache["val"] = v2.get("privacy")
        except Exception:  # noqa: BLE001 — unreadable store: the defaults
            _cache["val"] = dict(v2._DEFAULTS["privacy"])
        _cache["stamp"] = stamp
    return _cache["val"]


def _on(key: str) -> bool:
    return bool(_section().get(key, v2._DEFAULTS["privacy"][key]))


def location() -> bool:
    return _on("location")


def files() -> bool:
    return _on("files")


def observability() -> bool:
    return _on("observability")


def obfuscate() -> bool:
    return _on("obfuscate")
