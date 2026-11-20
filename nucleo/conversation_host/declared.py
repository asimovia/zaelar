"""The host's declared data (V2-941): `declared.json`, read once — the shapes of the model's claims, what a model call's
measurements carry, the reads a switched session offers, its proof's counters and its prefix's lines. Names and
schemas the code reads, never a table of words in it."""
from __future__ import annotations

import functools
import json
from pathlib import Path


@functools.lru_cache(maxsize=1)
def declared() -> dict:
    return json.loads(Path(__file__).with_name("declared.json").read_text(encoding="utf-8"))
