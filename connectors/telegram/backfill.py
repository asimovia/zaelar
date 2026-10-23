#
# backfill.py — walk every Telegram conversation back to its beginning, ONCE, into the communications archive.
#
# The policy is shared with WhatsApp (connectors/messaging/history.py: mode «walk», text only). Telegram is the
# easy case: the account pages its own history exactly (`get_messages` with `offset_id`), so a page is asked and
# answered in one call. People and groups are walked; broadcast channels are not — a channel is a feed, not a
# conversation the operator has, and some hold years of posts nobody asked to keep. Each page runs as its own
# task: a flood wait Telethon sleeps through must not hold up the live loop.
#
import asyncio
import time

from loguru import logger

from connectors.messaging import archive, history

PLATFORM = "telegram"
PAGE = 100
GAP_S = 3                 # between pages, paced well under Telegram's limits
RELIST_S = 900
MAX_DIALOGS = 500


class Walker:
    def __init__(self):
        self.queue: list = []
        self.listed_at = 0.0
        self.task: asyncio.Task | None = None
        self.last = 0.0

    async def _list(self, client) -> None:
        q = []
        async for d in client.iter_dialogs(limit=MAX_DIALOGS):
            if d.is_channel and not d.is_group:
                continue
            if not archive.backfill_state(PLATFORM, str(d.id)).get("done"):
                q.append(d)
        self.queue, self.listed_at = q, time.time()

    async def _page(self, client, dialog) -> None:
        from connectors.telegram import service as _svc
        cid = str(dialog.id)
        if archive.count(PLATFORM, cid) >= history.MAX_PER_CHAT:
            archive.backfill_mark(PLATFORM, cid, done=True)
            return
        o = archive.oldest(PLATFORM, cid)
        offset = (_svc._tg_msg_id(o.get("msg_id")) or 0) if o else 0
        msgs = await client.get_messages(dialog.entity, limit=PAGE, offset_id=offset)
        entries = [e for e in [await _svc._history_entry(m, dialog.id) for m in msgs or []] if e.get("ts")]
        archive.record(PLATFORM, cid, entries, chat_name=dialog.name or "", is_group=bool(dialog.is_group))
        archive.backfill_mark(PLATFORM, cid, page=bool(entries))
        if len(msgs or []) < PAGE:
            archive.backfill_mark(PLATFORM, cid, done=True)
            self.queue = [d for d in self.queue if str(d.id) != cid]
            logger.info(f"Telegram backfill: {dialog.name or cid} reached its beginning "
                        f"({archive.count(PLATFORM, cid)} messages held)")

    async def _run(self, client, dialog) -> None:
        try:
            await self._page(client, dialog)
        except Exception as e:  # noqa: BLE001 — one chat's failure must not stop the walk
            logger.warning(f"Telegram backfill: {dialog.name or dialog.id}: {type(e).__name__}: {e}")
            self.queue = [d for d in self.queue if d.id != dialog.id]

    async def tick(self, client) -> None:
        if client is None or not history.walk_enabled(PLATFORM):
            return
        if self.task is not None and not self.task.done():
            return
        now = time.time()
        if now - self.last < GAP_S:
            return
        if not self.queue and now - self.listed_at < RELIST_S:
            return
        if not self.queue or now - self.listed_at > RELIST_S:
            await self._list(client)
            if not self.queue:
                logger.info(f"Telegram backfill: every conversation walked — {archive.backfill_stats(PLATFORM)}")
                return
        self.last = now
        self.task = asyncio.create_task(self._run(client, self.queue[0]))


walker = Walker()
