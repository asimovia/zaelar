"""Read a session archive: a folder (or a file) of observer event logs, one JSON event per line.

Two shapes are accepted and normalised to one:

  · the observer's own JSONL (`{"i", "t_ms", "kind", "label", "text", "trace", ...}`), as the local viewer writes it;
  · an exported row (`{"ts_ms", "kind", "label", "corr_id", "payload": "<json string>"}`), whose payload carries the
    observer event; a row without `t_ms` in its payload (interims) takes the row's `ts_ms`.

`Event` keeps what the F0 tools need: time, kind, label, trace, text and the raw payload. Text is read here only so
the converter can turn it into tokens; no tool in this folder writes it out.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator


@dataclass(frozen=True)
class Event:
    t_ms: int
    kind: str
    label: str
    trace: str
    text: str
    payload: dict = field(default_factory=dict)


def _normalise(raw: dict) -> Event | None:
    payload = raw
    if isinstance(raw.get("payload"), str):
        try:
            payload = {**json.loads(raw["payload"] or "{}")}
        except ValueError:
            payload = {}
    elif isinstance(raw.get("extra"), dict):
        payload = {**raw["extra"], **{k: v for k, v in raw.items() if k != "extra"}}
    t = payload.get("t_ms") or raw.get("t_ms") or raw.get("ts_ms")
    kind = payload.get("kind") or raw.get("kind")
    if t is None or not kind:
        return None
    return Event(t_ms=int(t), kind=str(kind), label=str(payload.get("label") or raw.get("label") or ""),
                 trace=str(payload.get("trace") or raw.get("corr_id") or ""), text=str(payload.get("text") or ""),
                 payload=payload)


def read_file(path: Path) -> list[Event]:
    out: list[Event] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                ev = _normalise(json.loads(line))
            except ValueError:
                continue
            if ev is not None:
                out.append(ev)
    out.sort(key=lambda e: e.t_ms)   # stable: equal stamps keep their file order
    return out


def session_files(root: Path) -> Iterator[Path]:
    root = Path(root)
    if root.is_file():
        yield root
        return
    yield from sorted(p for p in root.rglob("*.jsonl") if not p.name.startswith("_"))


def sessions(root: Path) -> Iterable[tuple[str, list[Event]]]:
    for path in session_files(root):
        yield path.stem, read_file(path)
