"""The ONE way a search test names a recorded sheet under `fixtures/sheets/`.

A sheet's file name is `<case>__<lang>__results--<run>[-junk|-mixed|-offsubject].json`, so a bare case prefix
can match a clean run AND its adversarial twin. `next(glob(prefix))` then returns whichever the filesystem
lists first: the clean sheet on macOS, the junk one on Linux — green on the laptop, red in CI, with nothing
in the test saying which file it read. This resolves a pattern to EXACTLY one sheet and fails by name otherwise.
"""
from __future__ import annotations

import json
from pathlib import Path

SHEETS = Path(__file__).resolve().parent / "fixtures" / "sheets"


def sheet_path(pattern: str) -> Path:
    """`pattern` is a glob without the `.json` suffix; it must match one sheet and only one."""
    hits = sorted(SHEETS.glob(pattern + "*.json"))
    if len(hits) != 1:
        names = ", ".join(p.name for p in hits) or "none"
        raise LookupError(f"sheet pattern {pattern!r} must match exactly one file, matched: {names}")
    return hits[0]


def sheet(pattern: str) -> dict:
    return json.loads(sheet_path(pattern).read_text(encoding="utf-8"))
