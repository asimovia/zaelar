"""The cadence: pull (idle / active), heartbeat, discover — one `tick(now)` the engine's pulse calls.

| job       | when                                                                   | env                       |
|-----------|------------------------------------------------------------------------|---------------------------|
| pull      | idle every 15 min; every 30 s while an envelope arrived < 10 min ago   | `A2A_POLL_SECS` (0 = wake only + hourly safety pull) |
| heartbeat | hourly                                                                 | —                         |
| discover  | daily, and once per contact event (debounced 60 s); the owner may force it | —                     |
| beat      | one row every `A2A_BEAT_PULLS` empty pulls (the quiet ones are summed) | `A2A_BEAT_PULLS` (96)     |

The three discovery triggers share ONE code path (`A2AAgent.discover`). `stopped` (the ⏻) → nothing runs. After a
restart an overdue job fires once, not once per missed slot.
"""
from __future__ import annotations

import os
import time
from typing import Callable

ACTIVE_S, ACTIVE_WINDOW_S, HOUR, DAY = 30, 600, 3600, 86400
DEBOUNCE_S = 60


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


class Jobs:
    def __init__(self, agent, contacts: Callable[[], list[dict]] = lambda: [], clock=time.time,
                 heartbeat: Callable[[], str] | None = None):
        self.agent, self.contacts, self.clock = agent, contacts, clock
        self._heartbeat = heartbeat
        self.idle_s = _env_int("A2A_POLL_SECS", 900)
        self.beat_every = max(1, _env_int("A2A_BEAT_PULLS", 96))
        self.stopped = False
        self.last = {"pull": 0.0, "heartbeat": 0.0, "discover": 0.0}
        self._pending_contacts: dict[str, float] = {}
        self._last_activity = 0.0
        self._pulls = 0

    def _pull_interval(self, now: float) -> float:
        if now - self._last_activity < ACTIVE_WINDOW_S:
            return ACTIVE_S
        return self.idle_s if self.idle_s > 0 else HOUR

    def pull(self, reason: str) -> int:
        now = self.clock()
        self.last["pull"] = now
        n = self.agent.pull(reason=reason)
        if n:
            self._last_activity = now
        self._pulls += 1
        if self._pulls % self.beat_every == 0:
            empties = self.agent.empty_pulls
            self.agent.emit("beat", pulls=self.beat_every, empty=len(empties),
                            avg_ms=round(sum(empties) / len(empties), 1) if empties else 0,
                            max_ms=round(max(empties), 1) if empties else 0)
            empties.clear()
        return n

    def wake(self) -> int:
        """A verified wake push: one pull now, whatever the cadence (still respects ⏻)."""
        return 0 if self.stopped else self.pull("wake")

    def contact_event(self, cid: str) -> None:
        """A contact was created or edited (email/phone): one debounced lookup for that contact."""
        self._pending_contacts[cid] = self.clock()

    def tick(self) -> list[str]:
        if self.stopped:
            return []
        now, ran = self.clock(), []
        if now - self.last["pull"] >= self._pull_interval(now):
            self.pull("active" if now - self._last_activity < ACTIVE_WINDOW_S else ("boot" if not self.last["pull"]
                                                                                    else "idle"))
            ran.append("pull")
        if now - self.last["heartbeat"] >= HOUR:
            self.last["heartbeat"] = now
            state = "n/a"
            if self._heartbeat:
                try:
                    state = self._heartbeat()
                except Exception:
                    state = "failed"
            self.agent.emit("heartbeat", ok=state != "failed", roster_state=state)
            ran.append("heartbeat")
        if now - self.last["discover"] >= DAY:
            self.last["discover"] = now
            self.agent.discover(self.contacts(), trigger="daily")
            ran.append("discover")
        due = [c for c, t in self._pending_contacts.items() if now - t >= DEBOUNCE_S]
        if due:
            for c in due:
                self._pending_contacts.pop(c, None)
            wanted = [c for c in self.contacts() if c.get("cid") in due]
            if wanted:
                self.agent.discover(wanted, trigger="contact")
                ran.append("discover:contact")
        return ran
