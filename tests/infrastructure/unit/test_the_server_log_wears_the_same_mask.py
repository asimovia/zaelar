"""The server log wears the same mask as the stored events (V2-875 / INI-063 D13).

A record written while his `obfuscate` switch is on carries tags where the stored event would: an email, a phone, a
name the agent knows. With the switch off the line is untouched. The masker never recurses and never raises.
Disarm: drop `logger.configure(patcher=…)` from `server/__main__.py` or make `masked` return its input → red.
"""
from __future__ import annotations

import re
from pathlib import Path

from loguru import logger

from observability import log_mask, pii

ENGINE = Path(__file__).resolve().parents[3]


def _sink():
    seen: list[str] = []
    sid = logger.add(lambda m: seen.append(m.record["message"]), level="DEBUG", format="{message}")
    return seen, sid


def test_a_masked_record_carries_tags_not_his_data(monkeypatch):
    from config import privacy
    monkeypatch.setattr(privacy, "obfuscate", lambda: True)
    monkeypatch.setattr(pii, "known", lambda ttl_s=60.0: {"raquel": "[PERSON]"})
    seen, sid = _sink()
    try:
        logger.configure(patcher=log_mask.patch)
        logger.info("heard: «escríbele a Raquel a raquel@example.com, su móvil es +34 612 345 678»")
    finally:
        logger.remove(sid)
        logger.configure(patcher=None)
    line = seen[-1]
    assert "raquel@example.com" not in line and "612 345 678" not in line and "Raquel" not in line, line
    assert "[PERSON]" in line and re.search(r"\[(EMAIL|PHONE)\]", line), line


def test_with_the_switch_off_the_line_is_untouched(monkeypatch):
    from config import privacy
    monkeypatch.setattr(privacy, "obfuscate", lambda: False)
    seen, sid = _sink()
    try:
        logger.configure(patcher=log_mask.patch)
        logger.info("heard: «escríbele a Raquel a raquel@example.com»")
    finally:
        logger.remove(sid)
        logger.configure(patcher=None)
    assert seen[-1] == "heard: «escríbele a Raquel a raquel@example.com»"


def test_the_masker_never_raises_and_never_recurses(monkeypatch):
    from config import privacy
    monkeypatch.setattr(privacy, "obfuscate", lambda: True)

    def boom(text, names=None):
        logger.debug("pii: tag failed (boom)")    # the tagger's own line, while the masker is on
        raise RuntimeError("boom")
    monkeypatch.setattr(pii, "tag", boom)
    seen, sid = _sink()
    try:
        logger.configure(patcher=log_mask.patch)
        logger.info("Raquel at raquel@example.com")
    finally:
        logger.remove(sid)
        logger.configure(patcher=None)
    assert "[WITHHELD]" in seen and "pii: tag failed (boom)" in seen, seen


def test_the_boot_installs_the_patcher():
    src = (ENGINE / "server" / "__main__.py").read_text(encoding="utf-8")
    assert "logger.configure(patcher=_log_mask.patch)" in src
