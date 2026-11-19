"""The focus of each device: what a bare «yes» could answer there (N2, §7.1).

A question (or a confirmation handle) is a focus candidate only once it was PRESENTED on that device — played there
or painted there. When the person starts speaking on a device, its focus is PINNED: the one open, presented candidate
of that device, or nothing if there are none or several (ambiguous → nothing). While they speak it is never replaced:
a worker's question that appears in the middle cannot steal the «yes». A question presented only on the desktop is
no focus on the phone. The focus is per device, never per channel and never by content.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class _Device:
    presented: dict[str, int] = field(default_factory=dict)      # candidate → when it was presented here
    pinned: str | None = None
    speaking: bool = False


class Focus:
    def __init__(self) -> None:
        self._d: dict[str, _Device] = {}

    def _dev(self, endpoint: str) -> _Device:
        return self._d.setdefault(endpoint, _Device())

    def presented(self, item_id: str, endpoint: str | None, t_ms: int) -> None:
        if endpoint:
            self._dev(endpoint).presented[item_id] = t_ms

    def closed(self, item_id: str) -> None:
        """The question was answered, expired or superseded: no longer a candidate anywhere."""
        for d in self._d.values():
            d.presented.pop(item_id, None)
            if d.pinned == item_id:
                d.pinned = None

    def onset(self, endpoint: str) -> str | None:
        d = self._dev(endpoint)
        if not d.speaking:
            d.speaking = True
            d.pinned = next(iter(d.presented)) if len(d.presented) == 1 else None
        return d.pinned

    def done_speaking(self, endpoint: str) -> None:
        self._dev(endpoint).speaking = False

    def of(self, endpoint: str | None) -> str | None:
        """The pinned focus while speaking or right after; otherwise the device's single candidate, if one."""
        if endpoint is None:
            return None
        d = self._dev(endpoint)
        if d.speaking or d.pinned is not None:
            return d.pinned
        return next(iter(d.presented)) if len(d.presented) == 1 else None
