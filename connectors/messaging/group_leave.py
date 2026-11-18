"""group_leave.py — leaving a messaging GROUP, over the bus (the `leave_group` order of the messaging card).

The order `{platform, ref, chats: [{chatId, name}]}` goes out on `msg.group_leave`; that platform's connector leaves
each chat and removes it from his list, then answers `connector.chats_gone` `{platform, ref, chatIds}` with the chats
that are gone, and `msg.send_failed` (the order and the reason) naming the ones that are not. Its own pair of topics,
next to `msg.group` (creating one): a chat that is gone is neither a page of the list nor a message.
"""
from __future__ import annotations

import logging

import bus
from connectors.messaging import ingest

_log = logging.getLogger("zaelar.messaging.group_leave")

TOPIC_GROUP_LEAVE = "msg.group_leave"
TOPIC_CHATS_GONE = "connector.chats_gone"


class GroupLeaveInbox(ingest._PlatformInbox):
    """Per-platform subscription to `msg.group_leave`: the operator leaving groups on this platform."""
    _TOPIC = TOPIC_GROUP_LEAVE


def publish_group_leave(order: dict) -> None:
    try:
        bus.emit_sync(TOPIC_GROUP_LEAVE, dict(order or {}))
    except Exception as e:  # noqa: BLE001
        _log.warning(f"group leave order not published: {type(e).__name__}")


def publish_chats_gone(platform: str, chat_ids, ref: str = "") -> None:
    """A connector telling the card these chats are GONE from his account (he left them, the chat was removed)."""
    try:
        bus.emit_sync(TOPIC_CHATS_GONE, {"platform": platform, "ref": str(ref or ""),
                                         "chatIds": [str(c) for c in chat_ids or []]})
    except Exception as e:  # noqa: BLE001
        _log.warning(f"chats gone not published: {type(e).__name__}")


async def leave_each(platform: str, order: dict, leave_one) -> tuple[list[str], list[str]]:
    """Run one leave order with the connector's own `leave_one(chat_id) -> dict | None` (raises on failure), then
    answer it: the chats that left as `connector.chats_gone`, the ones that did not as ONE `msg.send_failed` naming
    each. Returns `(left ids, failure lines)`."""
    left, failed = [], []
    for c in order.get("chats") or []:
        cid, name = str((c or {}).get("chatId") or "").strip(), str((c or {}).get("name") or "").strip()
        if not cid:
            continue
        try:
            await leave_one(cid)
            left.append(cid)
        except Exception as e:  # noqa: BLE001 — the failure is named in the order's answer
            failed.append(f"«{name or cid}»: {e}")
    if left:
        publish_chats_gone(platform, left, str(order.get("ref") or ""))
    if failed:
        ingest.publish_send_failed(order, "no pude salir de " + "; ".join(failed))
    return left, failed
