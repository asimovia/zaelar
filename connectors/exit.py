"""connectors/exit.py — the ONE door a message crosses on its way out of this machine.

A message to somebody outside leaves in two steps: an order is put in the messaging card's outbound queue, and the
card's owner publishes it on the bus, where the platform's connector drains it and sends. Many roads lead to the
queue — the message owner of the conversation, his own hand on the card, a worker, an errand that wakes when the
other party answers, the autoresponder, a calendar invitation — and each of them used to publish, or queue, in its
own way. This module is the last step they all share:

    leave(kind, order)   the only caller of the four bus publishers (`msg.send`, `msg.reply`, `msg.group`,
                         `msg.group_leave`). It reads the order's LANE, counts it, records one event, and either
                         publishes it or answers `msg.send_failed` with the reason it was held.
    check(kind, lane)    the same question asked EARLY by the road itself, before it queues or promises anything, so
                         a held act is said at once instead of failing after his yes.
    held(lane)           the pure rule behind both.

A LANE is who asked for the exit. It is a closed set (`LANES`), written into the order by the code of the road that
queued it — never by a model, never read from a payload a model filled: on a payload it travels as a `Stamp`, a type
only `stamp()` makes. An order whose lane is missing or unknown is `unlabelled`: it is held and counted, so a road
nobody declared cannot send.

The switch is one environment variable, read at every use:

    ZAELAR_HOLD_OUTBOUND=            nothing is held
    ZAELAR_HOLD_OUTBOUND=all         every outside write is held (also `1`, `true`, `yes`, `on`)
    ZAELAR_HOLD_OUTBOUND=errand,mandate   only those lanes are held
    ZAELAR_HOLD_OUTBOUND=all,-owner      every lane is held but the ones named with a minus (a lane added later is
                                         held too: what is let go is named, never what is kept)

A value that names something that is not a lane holds EVERYTHING: a typo in a safety switch must not read as «off».

What is recorded is numbers and names — the kind, the lane, the outcome, the order's own reference and platform —
never the text of a message nor who it is for.
"""
from __future__ import annotations

import os
import threading

from loguru import logger

#: The variable that holds outside writes on this install.
ENV = "ZAELAR_HOLD_OUTBOUND"

#: Who may ask for an exit. One name per road, declared once.
OWNER = "owner"                # the conversation's message owner: his words, one confirmation he heard
HAND = "hand"                  # his own hand on the card
WORKER = "worker"              # a worker's act he said yes to at the worker's exit door
MANDATE = "mandate"            # a worker's act an errand's standing mandate covers, with no question
ERRAND = "errand"              # an errand's or a stream's own reply when the other party writes
AUTORESPOND = "autorespond"    # the «I am away» reply
INVITE = "invite"              # a calendar invitation, or the answer to one
A2A = "a2a"                    # a message to a contact's agent
CLUSTER = "cluster"            # a message into a peer cluster
MESH = "mesh"                  # a request to an agent that serves it
BROWSER = "browser"            # a form submitted on a web page
LANES = frozenset({OWNER, HAND, WORKER, MANDATE, ERRAND, AUTORESPOND, INVITE, A2A, CLUSTER, MESH, BROWSER})

#: The orders `leave` publishes, each on its own bus topic.
SEND, REPLY, GROUP, GROUP_LEAVE = "send", "reply", "group", "group_leave"
KINDS = (SEND, REPLY, GROUP, GROUP_LEAVE)

#: Why an exit was held (`held`).
UNLABELLED, SWITCH, LANE_HELD = "unlabelled", "switch", "lane"
#: What happened to an exit (`counters`).
OUT, HELD = "out", "held"



class Stamp(str):
    """A lane as CODE names it on a payload that travels to the card. A payload a model wrote can carry the same
    letters but never this type, and any copy through text or JSON loses it — so a lane that is not a `Stamp` is no
    lane (`stamped`), and the act is held as unlabelled."""
    __slots__ = ()


def stamp(lane: str) -> Stamp:
    """The lane a door of ours puts on a payload. Only a declared lane can be stamped."""
    if lane not in LANES:
        raise ValueError(f"exit.stamp: {lane!r} is not a lane")
    return Stamp(lane)


def by(lane: str, payload):
    """`payload` as the door of `lane` hands it on: the same fields, with the lane stamped under `_lane`."""
    return {**payload, "_lane": stamp(lane)} if isinstance(payload, dict) else payload


def stamped(value) -> str:
    """The lane a payload value carries when our code put it there; '' for anything else."""
    return str(value) if isinstance(value, Stamp) else ""


_counts: dict[tuple[str, str, str], int] = {}
_lock = threading.Lock()


def _switch() -> tuple[bool, frozenset]:
    """The switch as it stands NOW: `(everything, lanes)`. A token that is not a lane holds everything."""
    raw = str(os.environ.get(ENV) or "").strip().lower()
    if not raw:
        return False, frozenset()
    tokens = {t.strip() for t in raw.replace(";", ",").split(",") if t.strip()}
    freed = {t[1:].strip() for t in tokens if t.startswith("-")}
    rest = tokens - {t for t in tokens if t.startswith("-")}
    if freed and freed <= LANES and rest and not rest & LANES:   # `all,-owner`: every lane but those let go
        return False, LANES - frozenset(freed)
    if not tokens <= LANES:           # `all`, `1`, `on`, a typo, a minus over no lane… hold everything
        return True, frozenset()
    return False, frozenset(tokens)


def held(lane: str) -> str:
    """'' when an exit asked by `lane` may leave; else why it may not: `unlabelled` · `switch` · `lane`."""
    lane = str(lane or "")
    if lane not in LANES:
        return UNLABELLED
    everything, lanes = _switch()
    if everything:
        return SWITCH
    return LANE_HELD if lane in lanes else ""


def reason(why: str, lane: str = "") -> str:
    """The reason as it travels with a failed order — a code for the record, never a sentence for him."""
    return f"held:{why}" + (f":{lane}" if lane and why == LANE_HELD else "")


def is_held(text) -> bool:
    """Is this failure reason (or error code) one of ours?"""
    return str(text or "").startswith("held")


def _count(kind: str, lane: str, outcome: str) -> None:
    with _lock:
        key = (kind, lane, outcome)
        _counts[key] = _counts.get(key, 0) + 1


def counters() -> dict[str, int]:
    """Every exit this process has seen, as `{"<kind>/<lane>/<out|held>": n}`."""
    with _lock:
        return {"/".join(k): n for k, n in sorted(_counts.items())}


def _record(kind: str, lane: str, outcome: str, why: str = "", order: dict | None = None) -> None:
    lane = lane if lane in LANES else UNLABELLED
    _count(kind, lane, outcome)
    facts = {"door": "exit", "exit": kind, "lane": lane, "outcome": outcome}
    if why:
        facts["why"] = why
    for k in ("ref", "platform"):
        v = (order or {}).get(k)
        if isinstance(v, str) and v:
            facts[k] = v[:80]
    line = f"exit: {kind} by {lane} — {outcome}" + (f" ({why})" if why else "")
    (logger.warning if outcome == HELD else logger.info)(line)
    try:
        from voice.observer import emit
        emit("consequence", f"{'🛑' if outcome == HELD else '📤'} {line}", role="system", extra=facts)
    except Exception as e:  # noqa: BLE001 — the record never takes the exit it describes down
        logger.debug(f"exit: event not written — {e!r}")


def check(kind: str, lane: str, order: dict | None = None) -> str:
    """The road's own early question: '' when the act may go on; else the reason (`reason(...)`), counted and
    recorded once as a held exit. Ask it BEFORE queueing, asking him or promising — and answer with it."""
    why = held(lane)
    if not why:
        return ""
    _record(str(kind or "act"), str(lane or ""), HELD, why, order)
    return reason(why, str(lane or ""))


def _publish(kind: str, order: dict) -> None:
    from connectors.messaging import group_leave, ingest
    {SEND: ingest.publish_send, REPLY: ingest.publish_reply, GROUP: ingest.publish_group,
     GROUP_LEAVE: group_leave.publish_group_leave}[kind](order)


def leave(kind: str, order: dict) -> bool:
    """Publish ONE order for its connector — or hold it. True = it went out.

    The lane is the order's own (`order["lane"]`). A held order is answered on `msg.send_failed` with its reason, so
    whatever waits on it — the card's outbox row, an errand, the owner's receipt — settles as «not sent» and says so;
    it is never requeued."""
    if kind not in KINDS:
        raise ValueError(f"exit.leave: unknown kind {kind!r}")
    order = dict(order or {})
    lane = str(order.get("lane") or "")
    why = held(lane)
    if why:
        _record(kind, lane, HELD, why, order)
        if order.get("ref"):                 # something waits on it: its outbox row, an errand, a receipt
            try:
                from connectors.messaging import ingest
                ingest.publish_send_failed(order, reason(why, lane))
            except Exception as e:  # noqa: BLE001
                logger.warning(f"exit: a held {kind} could not be answered — {e!r}")
        return False
    _publish(kind, order)
    _record(kind, lane, OUT, "", order)
    return True


def _reset_counters() -> None:
    """For tests: a clean count."""
    with _lock:
        _counts.clear()
