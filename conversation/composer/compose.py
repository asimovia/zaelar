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

ITEMS, INBOX, SAYS, IVS = "items", "inbox", "says", "interventions"
CONTENT = ("user.utterance", "user.text")
#: a discard that is no lost voice of his: the tail of the voice that just closed, and our own voice heard back
NOT_LOST = ("no_voice", "echo")


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
    lost: tuple[tuple[int, str, str], ...] = ()     # (when, intervention, why): his voices that brought nothing whole


def view_from(snapshot, *, prefix: str, now_ms: int, **kw) -> View:
    """The conversation window comes from the person's entries and our lines — the inbox and the says — in the order
    they happened; no table of turns keeps a second copy (the durable pair goes to the host's record)."""
    items = tuple(r for _k, r in snapshot.scan(ITEMS))
    theirs = [(r["accepted"], 0, {"role": "user", "channel": r["env"]["channel"], "text": r["env"]["body"]["text"],
                                  "heard_chars": None, "ref": r["env"]["body"]["intervention_id"]})
              for _k, r in snapshot.scan(INBOX) if r["kind"] in CONTENT and r["state"] == "accounted"]
    ours = [(r["t_ms"], 1, {"role": "agent", "channel": "+".join(r["channels"]), "text": r["text"],
                            "heard_chars": r["heard_chars"], "ref": r["say_id"]})
            for _k, r in snapshot.scan(SAYS)]
    turns = tuple(t for _at, _o, t in sorted(theirs + ours, key=lambda x: (x[0], x[1])))
    lost = [(r["updated_ms"], iv, r.get("reason") or "no_words") for iv, r in snapshot.scan(IVS)
            if r.get("phase") == "discarded" and r.get("reason") not in NOT_LOST]
    lost += [(r["env"]["sealed_ms"], r["env"]["body"]["intervention_id"], r["env"]["body"].get("reason") or "incomplete")
             for _k, r in snapshot.scan(INBOX)
             if r["kind"] == "user.utterance" and r["env"]["body"].get("coverage") == "incomplete"]
    return View(prefix=prefix, now_ms=now_ms, items=items, turns=turns, lost=tuple(sorted(lost)), **kw)


def compose(view: View, batch: tuple[E.Envelope, ...], cfg: Config) -> PromptParts:
    state = [blocks.now_block(view.now_ms, view.tz_offset_min, view.screen, view.voice_endpoint, view.lang),
             blocks.open_block(list(view.items), cfg.open_budget)]
    for m in view.memory:
        state.append(f"{m.title}\n{m.text}")
    if any(e.kind.value == "user.text" for e in batch):              # U44: a text after a voice of his that was lost
        here = {getattr(e.body, "intervention_id", None) for e in batch}          # an id once in state + input
        lost = [x for x in view.lost if view.now_ms - x[0] <= cfg.voice_lost_window_ms and x[1] not in here]
        if lost:
            state.append(blocks.lost_block(view.now_ms, lost))
    return PromptParts(prefix=view.prefix, state="\n\n".join(state),
                       conversation=blocks.cut_to_heard(list(view.turns), cfg.conversation_turns),
                       input=blocks.input_block(batch))
