"""A ride's trackpoints, one JSON line each, in the app's own data directory (V2-901).

They are kept OUT of `state.json` on purpose: a three-hour ride is ~2,000 points, and `state.json` is rewritten on
every save. One file per ride (`rides/<id>.jsonl`), appended while riding, read whole for the detail and the
segment matcher, rewritten only when reconstructed points are merged in.
"""
from __future__ import annotations

import json
import os

from .. import store

WID = "cycling"


def _dir() -> str:
    d = os.path.join(store.data_dir(WID), "rides")
    os.makedirs(d, exist_ok=True)
    return d


def path(ride_id) -> str:
    return os.path.join(_dir(), f"{int(ride_id)}.jsonl")


def append(ride_id, points: list) -> int:
    if not points:
        return 0
    with open(path(ride_id), "a", encoding="utf-8") as f:
        for p in points:
            f.write(json.dumps(p, separators=(",", ":")) + "\n")
    return len(points)


def load(ride_id) -> list:
    """Every trackpoint of a ride in time order; a torn last line (a write cut short) is skipped, never fatal."""
    try:
        with open(path(ride_id), encoding="utf-8") as f:
            out = []
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except (OSError, ValueError, TypeError):
        return []
    from .engine import ts_ms
    out.sort(key=lambda p: ts_ms(p.get("ts")))
    return out


def merge(ride_id, points: list) -> int:
    """Add points to a closed ride (reconstructed gaps) keeping the file in time order."""
    if not points:
        return 0
    allp = load(ride_id) + list(points)
    from .engine import ts_ms
    allp.sort(key=lambda p: ts_ms(p.get("ts")))
    tmp = path(ride_id) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for p in allp:
            f.write(json.dumps(p, separators=(",", ":")) + "\n")
    os.replace(tmp, path(ride_id))
    return len(points)


def delete(ride_id) -> None:
    try:
        os.remove(path(ride_id))
    except (OSError, ValueError, TypeError):
        pass
