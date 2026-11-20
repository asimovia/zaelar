"""A whole manager over a real store with the package's own doubles, and a speaker that talks in ear signals."""
from __future__ import annotations

import asyncio
import dataclasses

from conversation import build
from conversation.config import Config
from conversation.ear import signals as S
from conversation.testing.fakes import AckingMouth, FakeClock, FakeOwed, ListTelemetry, NoMemory, RecordingTools
from conversation.testing.scripted_model import ScriptedModel

ACCT = "acct-test"


class Harness:
    def __init__(self, store, *, script: dict | None = None, config: Config | None = None, prefix: str = "RULES",
                 tasks=None, grace: bool = True, prefs=None) -> None:
        """The product's configuration, graces on. `grace=False` opts out, explicitly: the publication graces of a
        closed thought are zero and the reply goes out as soon as it is ready — for a test whose subject is not when a
        reply may go out."""
        config = config or Config()
        if not grace:
            config = dataclasses.replace(config, nonterminal_start_ms=0, nonterminal_grace_ms=0, terminal_grace_ms=0,
                                         complete_grace_ms=0, incomplete_grace_ms=0)
        self.clock, self.tel = FakeClock(t0_ms=0), ListTelemetry()   # signal times ARE the wall clock
        self.model, self.tools, self.mouth = ScriptedModel(script or {}), RecordingTools(), AckingMouth()
        self.store, self.owed = store, FakeOwed()
        self.conv = build(account=ACCT, owner="test", model=self.model, tools=self.tools, store=store,
                          memory=NoMemory(), clock=self.clock, mouth=self.mouth, telemetry=self.tel,
                          config=config, prefix=prefix, owed=self.owed, tasks=tasks, prefs=prefs)
        self.mouth.ack = self.conv.ack
        self.conv.device("d1", voice_live=True, speaker_open=True)
        self._seq = 0
        self.live = True

    def at(self, ms: int) -> "Harness":
        self.clock.mono = max(self.clock.mono, ms)
        return self

    def hear(self, *sigs) -> None:
        """Feed signals as they come; the manager runs whatever becomes ready in between, as the live loop would."""
        for s in sigs:
            for one in (s if isinstance(s, list) else [s]):
                t = getattr(one, "t_ms", None) or getattr(one, "processed_through_ms", None) or (
                    one.window[1] if isinstance(one, S.WordSpan) else None)
                if t is not None:
                    self.at(t)
                self.conv.hear(one)
                if self.live and (self.conv.current is None or self.conv.pumpable):
                    self.pump()

    def pump(self) -> int:
        return asyncio.run(self.conv.pump())

    def settle(self, ms: int = 6000, step: int = 100) -> "Harness":
        """Time passes on the live timer (a pump every `step`) until every grace has run out."""
        end = self.clock.mono + ms
        while self.clock.mono < end:
            self.at(min(end, self.clock.mono + step)).pump()
        return self

    # speech in the ear's terms: one provider turn per sentence part, eager / resumed / end as Flux sends them
    def words(self, toks, t0, step=200):
        return tuple((w, t0 + i * step, t0 + (i + 1) * step - 20, 1.0) for i, w in enumerate(toks))

    def beats(self, t0, t1, ep="d1"):
        return [S.Watermark(ep, t) for t in range(t0, t1 + 1, 240)]

    def utter(self, parts: list[tuple[list[str], int]], *, ep: str = "d1", mid: str = "eager_resumed",
              end_pause: int = 300, terminal: bool | None = None, at: int | None = None) -> int:
        """Say `parts` (tokens, pause after) as ONE provider turn; returns the time of the end of turn. Between parts
        the provider sends an eager hint and, when the person goes on, a resumed one (or `mid='end'`: an end of turn, then a
        new provider turn — the cut Flux made at a 900 ms pause in the adapter probe)."""
        self._seq += 1
        seq, rev, t, said = self._seq, 0, (self.clock.mono if at is None else at) + 10, []
        self.hear(S.VadEdge(ep, "rise", t))
        for i, (toks, pause) in enumerate(parts):
            ws = self.words(toks, t)
            said.extend(ws)
            rev += 1
            last = i == len(parts) - 1
            end_t = ws[-1][2]
            self.hear(S.WordSpan(ep, seq, rev, last or mid == "end", tuple(said), (said[0][1], end_t)),
                      self.beats(end_t, end_t + 100, ep))
            if last:
                break
            if mid == "end":
                self.hear(S.VadEdge(ep, "fall", end_t + 10), self.beats(end_t + 100, end_t + 300, ep),
                          S.EotHint(ep, "flux", "end", .71, end_t + 300))
                self._seq += 1
                seq, rev, said = self._seq, 0, []
                self.hear(self.beats(end_t + 300, end_t + pause, ep), S.VadEdge(ep, "rise", end_t + pause))
            else:
                self.hear(S.EotHint(ep, "flux", "eager", .55, end_t + 250), self.beats(end_t + 250, end_t + pause, ep),
                          S.EotHint(ep, "flux", "resumed", .1, end_t + pause))
            t = end_t + pause
        end_t = said[-1][2]
        self.hear(S.VadEdge(ep, "fall", end_t + 10), self.beats(end_t + 100, end_t + end_pause, ep),
                  S.EotHint(ep, "flux", "end", .9, end_t + end_pause, terminal))
        return end_t + end_pause

    def typed(self, text: str, t: int, ep: str = "d2", cid: str | None = None) -> None:
        self._seq += 1
        self.hear(S.TypedSubmit(ep, cid or f"c{self._seq}", text, t))

    def closes(self) -> list[tuple[str, dict]]:
        return [(lab, p) for k, lab, p in self.tel.events if k == "conv_close"]
