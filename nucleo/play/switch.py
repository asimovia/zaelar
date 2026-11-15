"""nucleo/play/switch.py — the behaviour switches of the programme (V2-909): `stage(name) -> bool`.

  · `shadow` — the programme records its steps beside today's path and changes nothing
  · `own`    — the programme is the path of a declared action

Precedence, as `widgets.screen_switch.stage`: the env first and OFF-ONLY (`ZAELAR_PLAY_<NAME>=0` forces the stage
off; no env value can force one on), then `config/v2` section `play`. A name nobody declared, or a store that cannot
be read, is OFF.
"""
from __future__ import annotations

import os

from loguru import logger


def stages() -> tuple[str, ...]:
    """The declared stages: the keys of the `play` section's defaults (one owner of the list)."""
    from config import v2
    return tuple(v2._DEFAULTS["play"])


def stage(name: str) -> bool:
    if name not in stages():
        logger.warning(f"play.switch: unknown stage {name!r} read as off")
        return False
    if (os.getenv(f"ZAELAR_PLAY_{name.upper()}", "") or "").strip().lower() in ("0", "false", "no", "off"):
        return False
    try:
        from config import v2
        return v2.get("play").get(name) is True
    except Exception as e:  # noqa: BLE001 — an unreadable store keeps the stage off
        logger.warning(f"play.switch: config unreadable, stage {name} off ({e!r})")
        return False
