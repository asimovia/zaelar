"""A `Model` that follows a script keyed by the INPUT's ids — never by text (the replay fixtures are tokens).

`script[key]` is a list of steps; a step is a list of events, where an event is a `ModelEvent` or a callable (run at
that point of the stream: a test injects the person's next sentence or a worker's result exactly between two model events,
which is how a checkpoint is exercised deterministically). The key is the first id of the INPUT block, or the ids
joined by `+` when several came together; the step is how many tool rounds the run already did. Unknown keys get
`default`. Every call is recorded with its prompt and tools.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from conversation.ports import Command, Done, PromptParts, ToolSpec


def input_ids(prompt: PromptParts) -> list[str]:
    """The ids of the INPUT block, as the composer writes them: `[<id> · …]` at the start of each line."""
    return [line[1:].split(" ", 1)[0].rstrip("]") for line in prompt.input.splitlines() if line.startswith("[")]


def reply(text: str, claims: list | None = None, **extra) -> Command:
    """`extra`: the optional fields of the order as the model would send them — `complete`, valid or not."""
    return Command("reply", {"text": text, "claims": claims or [], **extra})


@dataclass
class Call:
    run_id: str
    prompt: PromptParts
    tools: list[ToolSpec]
    key: str


@dataclass
class ScriptedModel:
    script: dict[str, list[list]] = field(default_factory=dict)
    default: Callable[[list[str]], list] = field(default=lambda ids: [reply("ok " + "+".join(ids)), Done()])
    calls: list[Call] = field(default_factory=list)

    async def stream(self, prompt: PromptParts, tools: list[ToolSpec], *, run_id: str, model_id: str):
        ids = input_ids(prompt)
        key = "+".join(ids)
        steps = self.script.get(key) or self.script.get(ids[0] if ids else "")
        self.calls.append(Call(run_id, prompt, list(tools), key))
        events = steps[min(len(prompt.steps), len(steps) - 1)] if steps else self.default(ids)
        for ev in events:
            if hasattr(ev, "__await__"):
                await ev                       # a pause the script imposes (a provider that hangs)
                continue
            if callable(ev) and not isinstance(ev, type):
                ev()
                continue
            yield ev
