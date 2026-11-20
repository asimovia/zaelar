"""The model's orders (§5.4). Two are the manager's: `reply(text, claims, complete)` and `no_reply(reason, complete)`. The task orders
(`task.start`, `task.continue`, `task.answer`, `task.cancel`) are tools of the catalog like any other — the manager
does not know the workers. Anything else is refused and said, never guessed.

`complete` is the model's own reading of what it was given (v3.1 §1.6 quater): True — an answerable thought; False —
something seems to be missing. It only sets how long a spoken batch waits before it is published; anything but a
boolean is no field at all, and the fixed graces rule."""
from __future__ import annotations

from dataclasses import dataclass, field

from conversation.manager.claims import Claim
from conversation.ports import Command


@dataclass(frozen=True)
class Reply:
    text: str
    claims: tuple[Claim, ...] = field(default_factory=tuple)
    complete: bool | None = None


@dataclass(frozen=True)
class NoReply:
    reason: str
    complete: bool | None = None


@dataclass(frozen=True)
class Unknown:
    name: str


def _complete(args: dict) -> bool | None:
    v = args.get("complete")
    return v if isinstance(v, bool) else None


def parse(cmd: Command) -> Reply | NoReply | Unknown:
    if cmd.name == "reply":
        claims = tuple(Claim.from_args(c) for c in cmd.args.get("claims") or ())
        return Reply(str(cmd.args.get("text", "")), claims, _complete(cmd.args))
    if cmd.name == "no_reply":
        return NoReply(str(cmd.args.get("reason", "")), _complete(cmd.args))
    return Unknown(cmd.name)
