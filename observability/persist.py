"""observability/persist.py — what of the agent's events may be STORED, and in what form (V2-875).

Capture never stops (`voice/observer.emit`, the bus): the person's own screens and the product subscribers keep their
live feed. This module only decides what reaches disk — the timeline and session files, the `events` table, the
prompt capture — from the person's switches (`config.privacy`):

  · `observability` off → nothing is stored;
  · `obfuscate` on (default) → a stored payload carries tags instead of personal data (`observability.pii`).

Called off the voice thread (the observer's writer thread, the bus log's sink), because tagging reads the agent's
known names. Never raises: on any failure the record is not stored rather than stored raw.
"""
from __future__ import annotations

import json

from loguru import logger

from config import privacy
from observability import pii


def storing() -> bool:
    return privacy.observability()


def tagged(obj):
    return pii.tag_obj(obj) if privacy.obfuscate() else obj


def line(ev: dict) -> str | None:
    """The JSONL line to store for `ev`, or None when nothing may be stored."""
    if not storing():
        return None
    try:
        return json.dumps(tagged(ev), ensure_ascii=False) + "\n"
    except Exception as e:  # noqa: BLE001 — not stored rather than stored raw
        logger.debug(f"persist: event not stored ({e!r})")
        return None
