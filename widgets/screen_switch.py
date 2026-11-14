"""widgets/screen_switch.py — the behaviour switches of the one screen state (V2-907): `stage(name) -> bool`.

Each phase that changes conduct is built behind one stage and stays OFF until its exit gate is measured:

  · `read`    — readers answer from the screen's document (`widgets/screen_doc.py`)
  · `confirm` — a canvas order is done when its screen acks it (`widgets/screen_orders.py`)
  · `direct`  — a simple order over the app in front acts without the model

Precedence, as `nucleo.actionmap.enabled`: the env first and OFF-ONLY (`ZAELAR_SCREEN_<NAME>=0` forces the stage off;
no env value can force one on), then `config/v2` section `screen`. A name nobody declared, or a store that cannot be
read, is OFF — a stage that is not sure stays as before.
"""
from __future__ import annotations

import os

from loguru import logger


def stages() -> tuple[str, ...]:
    """The declared stages: the keys of the `screen` section's defaults (one owner of the list)."""
    from config import v2
    return tuple(v2._DEFAULTS["screen"])


def stage(name: str) -> bool:
    if name not in stages():
        logger.warning(f"screen_switch: unknown stage {name!r} read as off")
        return False
    if (os.getenv(f"ZAELAR_SCREEN_{name.upper()}", "") or "").strip().lower() in ("0", "false", "no", "off"):
        return False
    try:
        from config import v2
        return v2.get("screen").get(name) is True
    except Exception as e:  # noqa: BLE001 — an unreadable store keeps the stage off
        logger.warning(f"screen_switch: config unreadable, stage {name} off ({e!r})")
        return False
