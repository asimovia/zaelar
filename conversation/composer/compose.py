"""The composer: a PURE function — (view of the state, batch) → the prompt (§5.4). No store, no clock, no I/O.

`view_from` reads one coherent snapshot of the `Store` into a `View` (the manager calls it once per run); `compose`
turns the view and the batch into `PromptParts`: a `prefix` that is byte-identical between runs (the cache), the
state (NOW · OPEN · the host's blocks), the conversation and the input. Every id appears once in state + input.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from conversation import envelopes as E
from conversation.composer import blocks
from conversation.config import Config
from conversation.ports import Block, PromptParts

ITEMS, TURNS = "items", "turns"


@dataclass(frozen=True)
class View:
    prefix: str
    now_ms: int
    items: tuple[dict, ...] = ()
    turns: tuple[dict, ...] = ()
    tz_offset_min: int = 0
    lang: str = ""
    screen: str | None = None
    voice_endpoint: str | None = None
    memory: tuple[Block, ...] = field(default_factory=tuple)


def view_from(snapshot, *, prefix: str, now_ms: int, **kw) -> View:
    items = tuple(r for _k, r in snapshot.scan(ITEMS))
    turns = tuple(r for _k, r in snapshot.scan(TURNS))
    return View(prefix=prefix, now_ms=now_ms, items=items, turns=turns, **kw)


def compose(view: View, batch: tuple[E.Envelope, ...], cfg: Config) -> PromptParts:
    state = [blocks.now_block(view.now_ms, view.tz_offset_min, view.screen, view.voice_endpoint, view.lang),
             blocks.open_block(list(view.items), cfg.open_budget)]
    for m in view.memory:
        state.append(f"{m.title}\n{m.text}")
    return PromptParts(prefix=view.prefix, state="\n\n".join(state),
                       conversation=blocks.cut_to_heard(list(view.turns), cfg.conversation_turns),
                       input=blocks.input_block(batch))
