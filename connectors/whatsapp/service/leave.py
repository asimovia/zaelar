#
# leave.py — LEAVING a group (`msg.group_leave`, the messaging card's `leave_group`): each chat of the order is left
# through the bridge, which also removes it from his list; the order is answered by `group_leave.leave_each`.
#
from loguru import logger

from connectors.messaging import group_leave
from connectors.whatsapp import client
from connectors.whatsapp import service as _svc

PLATFORM = _svc.PLATFORM


async def _leave_one(chat_id: str) -> None:
    got = await client.leave_group(chat_id) or {}
    if not got.get("left"):
        raise RuntimeError("the bridge did not say it left")
    if not got.get("deleted"):      # he is out of the group; only the chat on his phone could not be deleted
        logger.warning(f"WhatsApp: left {chat_id}, its chat was not deleted on the phone ({got.get('why') or '?'})")


async def _drain_group_leaves() -> None:
    """Leave the groups the operator asked to leave. Told once on failure, never retried."""
    if _svc._group_leave_inbox is None:
        return
    for order in _svc._group_leave_inbox.drain():
        left, failed = await group_leave.leave_each(PLATFORM, order, _leave_one)
        logger.info(f"WhatsApp: left {len(left)} group(s), {len(failed)} failed")
        if failed:
            _svc._note(f"[SISTEMA] No pude salir de {'; '.join(failed)} en WhatsApp. Díselo al operador.")
