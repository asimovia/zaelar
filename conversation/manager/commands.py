"""The model's orders (§5.4). Two are the manager's: `reply(text, claims)` and `no_reply(reason)`. The task orders
(`task.start`, `task.continue`, `task.answer`, `task.cancel`) are tools of the catalog like any other — the manager
does not know the workers. Anything else is refused and said, never guessed."""
from __future__ import annotations

from dataclasses import dataclass, field

from conversation.manager.claims import Claim
from conversation.ports import Command


@dataclass(frozen=True)
class Reply:
    text: str
    claims: tuple[Claim, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class NoReply:
    reason: str


@dataclass(frozen=True)
class Unknown:
    name: str


def parse(cmd: Command) -> Reply | NoReply | Unknown:
    if cmd.name == "reply":
        claims = tuple(Claim.from_args(c) for c in cmd.args.get("claims") or ())
        return Reply(str(cmd.args.get("text", "")), claims)
    if cmd.name == "no_reply":
        return NoReply(str(cmd.args.get("reason", "")))
    return Unknown(cmd.name)
