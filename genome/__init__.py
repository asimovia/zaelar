"""genome — the agent's DNA has a name, a fingerprint and a generation (V2-859).

The genome is two places that already existed, read as one thing:

  · `nucleo/genesis.json`        — the universal genes (knobs, consent classes, playbook end states, …)
  · `i18n/genesis/<lang>/*.json` — the culture: playbook prose, action aliases, small talk, voice

Nothing moves and nothing is copied. This package adds what was missing:

  · `identity()`  → `{generation, hash, langs}`. The hash is over CANONICAL JSON with every documentation key
    (`_comment`, `_*`) stripped, so a comment edit is not a new genome and a value edit always is.
  · `check()`     → the schema a genome must pass before anything reads it.
  · `genesis()`   → the universal genes for every reader. A file that fails the check is said LOUD and the reader
    gets the LAST generation that passed (a snapshot this install keeps), never a half-read genome. With no
    snapshot yet, the reader gets `{}` and every reader's own code default — still never half a file.
  · `boot()`      → called once at start: identity, snapshot, and absorption when the generation changed.

Three layers, decided by WHERE a value lives (no flag): the factory is these files; the learned layer is the
`source='learned'` rows of the action map and the playbook routes; the personal layer (rules, config, memory,
contacts, library) is never read by anything in this package except the privacy filter, which reads names in
order to DROP them.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from loguru import logger

ENGINE = Path(__file__).resolve().parent.parent
GENESIS = ENGINE / "nucleo" / "genesis.json"
PACKS = ENGINE / "i18n" / "genesis"

#: The sections a genesis must carry, each an object. A reader of one of these may assume a dict.
SECTIONS = ("style", "consent", "library", "errands", "playbooks", "contacts", "circuit", "tasks", "genome")

_cache: dict = {"mtime": None, "data": None, "fallback": False}


def canonical(obj):
    """The value without its documentation: every key that starts with `_` goes, at every depth."""
    if isinstance(obj, dict):
        return {k: canonical(v) for k, v in obj.items() if not str(k).startswith("_")}
    if isinstance(obj, list):
        return [canonical(v) for v in obj]
    return obj


def _dump(obj) -> str:
    return json.dumps(canonical(obj), sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def check(data) -> list[str]:
    """Why this genesis cannot be read, one reason per line; `[]` when it passes."""
    if not isinstance(data, dict):
        return ["genesis is not an object"]
    out = []
    gen = data.get("generation")
    if not isinstance(gen, int) or isinstance(gen, bool) or gen < 1:
        out.append(f"generation must be an integer ≥ 1, got {gen!r}")
    for name in SECTIONS:
        if not isinstance(data.get(name), dict):
            out.append(f"section `{name}` must be an object")
    for name, pb in (data.get("playbooks") or {}).items() if isinstance(data.get("playbooks"), dict) else ():
        if not str(name).startswith("_") and not isinstance(pb, dict):
            out.append(f"playbook `{name}` must be an object")
    return out


def _packs() -> dict[str, dict]:
    """`{lang/file: content}` for every culture pack; an unreadable pack is `None` and fails the check."""
    out: dict[str, dict] = {}
    for f in sorted(PACKS.glob("*/*.json")):
        try:
            out[f"{f.parent.name}/{f.name}"] = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            out[f"{f.parent.name}/{f.name}"] = None
    return out


def _read(path: Path | None = None):
    try:
        return json.loads((path or GENESIS).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return e


def identity(data: dict | None = None, packs: dict | None = None) -> dict:
    """`{generation, hash, langs}` of the genome on disk (or of the given parts)."""
    data = genesis() if data is None else data
    packs = _packs() if packs is None else packs
    h = hashlib.sha256(_dump(data).encode("utf-8"))
    for key in sorted(packs):
        h.update(key.encode("utf-8"))
        h.update(_dump(packs[key]).encode("utf-8"))
    langs = sorted({k.split("/", 1)[0] for k in packs})
    return {"generation": int((data or {}).get("generation") or 0), "hash": h.hexdigest()[:16], "langs": langs}


def _snapshot_path() -> Path:
    from nucleo import workspace as _ws
    return _ws.root() / "config" / "genome" / "last_good.json"


def _last_good() -> dict:
    try:
        snap = json.loads(_snapshot_path().read_text(encoding="utf-8"))
        return snap.get("genesis") if isinstance(snap.get("genesis"), dict) else {}
    except (OSError, ValueError, AttributeError) as e:
        logger.warning(f"genome: no last good generation to fall back to ({e!r})")
        return {}


def _keep(data: dict) -> None:
    """Remember this generation as the last good one. Best effort: a read-only disk only loses the fallback."""
    try:
        p = _snapshot_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"identity": identity(data), "genesis": data}, ensure_ascii=False),
                     encoding="utf-8")
    except OSError as e:
        logger.warning(f"genome: last good generation not kept ({e!r})")


def _refused(why: str) -> None:
    logger.error(f"genome: genesis REFUSED — {why}; reading the last good generation")
    try:
        from voice.observer import emit
        emit("alert", "🧬 genesis refused — last good generation in use", text=why[:300], role="system",
             extra={"cat": "genome", "why": why[:300]})
    except Exception as e:  # noqa: BLE001 — the alert is an instrument; the fallback already happened
        logger.debug(f"genome: alert not emitted ({e!r})")


def genesis() -> dict:
    """The universal genes every reader reads. Re-read when the file changes; never half a file."""
    try:
        mtime = GENESIS.stat().st_mtime_ns
    except OSError:
        mtime = -1
    if _cache["data"] is None or _cache["mtime"] != mtime:
        data = _read()
        why = f"unreadable ({data!r})" if isinstance(data, Exception) else "; ".join(check(data))
        if why:
            _refused(why)
            data = _last_good()
        _cache.update(mtime=mtime, data=data, fallback=bool(why))
    return copy.deepcopy(_cache["data"])


def in_fallback() -> bool:
    genesis()
    return bool(_cache["fallback"])


def boot() -> dict:
    """Once at start: name the genome, keep it as the last good generation, absorb on a generation change."""
    data = genesis()
    ident = identity(data)
    bad = [k for k, v in _packs().items() if not isinstance(v, dict)]
    if bad:
        logger.error(f"genome: culture pack unreadable — {bad}")
    if not in_fallback():
        _keep(data)
    from . import absorb
    absorb.on_boot(ident, data)
    logger.info(f"genome: generation {ident['generation']} · {ident['hash']} · {','.join(ident['langs'])}"
                + (" · FALLBACK" if in_fallback() else ""))
    return ident
