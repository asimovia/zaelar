#
# backfill.py — copy the PAST of the Telegram account into the communications archive, inside declared bounds.
#
# The policy is shared (connectors/messaging/history.py: mode «walk», text only; the numbers in
# `config/messaging.default.json`). Telegram is the easy case: the account pages its own history exactly
# (`get_messages` with `offset_id`), so a page is asked and answered in one call. Two walks, one page per tick:
#   · the FIRST IMPORT, once — the newest conversations first, each back to the day bound or its message bound,
#     and the whole import stops at its own bound. It never copied «every conversation to its beginning»: measured
#     on one account, that was 168 000 messages back to 2020 for a person who asked about last week.
#   · ON DEMAND — a conversation somebody asked about (`archive.want`, by id or by the name they used) is copied
#     further back, a bounded stretch per ask, whatever the first import left out. It goes first.
# People and groups are walked; broadcast channels are not — a channel is a feed, not a conversation the operator
# has. Each page runs as its own task: a flood wait Telethon sleeps through must not hold up the live loop.
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


WANT_RELIST_S = 30        # an ask for a conversation not listed yet looks at the dialogs again this soon


def _stamp(dialog) -> float:
    try:
        return dialog.date.timestamp()
    except Exception as e:  # noqa: BLE001 — a dialog without a date sorts last and is still walked
        logger.debug(f"telegram backfill: dialog date unreadable: {type(e).__name__}")
        return 0.0


class Walker:
    def __init__(self):
        self.queue: list = []
        self.dialogs: list = []
        self.listed_at = 0.0
        self.task: asyncio.Task | None = None
        self.last = 0.0
        self.deep: dict[str, int] = {}          # ask → messages copied for it so far
        self.full = False                       # the first import reached its message bound

    async def _list(self, client) -> None:
        p = history.policy()
        seen = []
        async for d in client.iter_dialogs(limit=MAX_DIALOGS):
            if d.is_channel and not d.is_group:
                continue
            seen.append(d)
        # Newest conversation first — Telegram floats pinned ones to the top whatever their age.
        seen.sort(key=_stamp, reverse=True)
        self.dialogs = seen
        cut, chats = history.horizon(), int(p["initial_chats"] or 0)
        first = seen[:chats] if chats else seen
        self.queue = [d for d in first if (not _stamp(d) or not cut or _stamp(d) >= cut)
                      and not archive.backfill_state(PLATFORM, str(d.id)).get("done")]
        self.listed_at = time.time()

    def _asked(self) -> tuple | None:
        """The oldest on-demand ask and its dialog, or None. An ask no dialog answers is closed."""
        for w in archive.wanted(PLATFORM):
            key, name = w["chat_id"], w["name"]
            if name:
                hits = [d for d in self.dialogs if str(getattr(d, "name", "") or "").casefold() == name] \
                    or [d for d in self.dialogs if name in str(getattr(d, "name", "") or "").casefold()]
                d = hits[0] if len(hits) == 1 else None
            else:
                d = next((x for x in self.dialogs if str(x.id) == key), None)
            if d is not None:
                return key, d
            if time.time() - self.listed_at < WANT_RELIST_S:        # looked just now: nobody is called that
                archive.served(PLATFORM, key)
            else:
                self.listed_at = 0.0                                 # look at the dialogs again first
                return None
        return None

    async def _fetch(self, client, dialog, limit: int) -> tuple[list, list]:
        from connectors.telegram import service as _svc
        cid = str(dialog.id)
        o = archive.oldest(PLATFORM, cid)
        offset = (_svc._tg_msg_id(o.get("msg_id")) or 0) if o else 0
        msgs = await client.get_messages(dialog.entity, limit=limit, offset_id=offset)
        entries = [e for e in [await _svc._history_entry(m, dialog.id) for m in msgs or []] if e.get("ts")]
        return list(msgs or []), entries

    async def _page(self, client, dialog) -> None:
        """One page of the FIRST import for one conversation: inside the day bound and its message bound."""
        p = history.policy()
        cid, name = str(dialog.id), dialog.name or ""
        held = archive.count(PLATFORM, cid)
        cap = int(p["initial_per_chat"] or 0) or history.MAX_PER_CHAT
        total = int(p["initial_messages"] or 0)
        room = total - archive.held(PLATFORM, history.horizon()) if total else PAGE
        if room <= 0:
            self.full, self.queue = True, []
            logger.info(f"Telegram first import: its message bound is reached ({total}) — the rest is copied on demand")
            return
        if held >= min(cap, history.MAX_PER_CHAT):
            self._close(cid, name, "its message bound")
            return
        ask = min(PAGE, cap - held, room)
        msgs, entries = await self._fetch(client, dialog, ask)
        keep = history.within_first_import(entries, held)
        archive.record(PLATFORM, cid, keep, chat_name=name, is_group=bool(dialog.is_group))
        archive.backfill_mark(PLATFORM, cid, page=bool(keep))
        if len(msgs) < ask:
            self._close(cid, name, "its beginning")
        elif len(keep) < len(entries):
            self._close(cid, name, "the day bound")

    def _close(self, cid: str, name: str, why: str) -> None:
        archive.backfill_mark(PLATFORM, cid, done=True)
        self.queue = [d for d in self.queue if str(d.id) != cid]
        logger.info(f"Telegram first import: {name or cid} reached {why} ({archive.count(PLATFORM, cid)} messages held)")

    async def _deeper(self, client, key: str, dialog) -> None:
        """One page of an ON-DEMAND ask: further back than anything held, until the ask's stretch is copied."""
        p = history.policy()
        cid, name = str(dialog.id), dialog.name or ""
        msgs, entries = await self._fetch(client, dialog, PAGE)
        archive.record(PLATFORM, cid, entries, chat_name=name, is_group=bool(dialog.is_group))
        archive.backfill_mark(PLATFORM, cid, page=bool(entries))
        got = self.deep[key] = self.deep.get(key, 0) + len(entries)
        if len(msgs) < PAGE or got >= int(p["deep_messages"] or PAGE) \
                or archive.count(PLATFORM, cid) >= int(p["deep_per_chat"] or history.MAX_PER_CHAT):
            archive.served(PLATFORM, key)
            self.deep.pop(key, None)
            logger.info(f"Telegram on demand: {name or cid} — {got} older message(s) copied "
                        f"({archive.count(PLATFORM, cid)} held)")

    async def _run(self, client, dialog, key: str = "") -> None:
        try:
            if key:
                await self._deeper(client, key, dialog)
            else:
                await self._page(client, dialog)
        except Exception as e:  # noqa: BLE001 — one chat's failure must not stop the walk
            logger.warning(f"Telegram backfill: {dialog.name or dialog.id}: {type(e).__name__}: {e}")
            self.queue = [d for d in self.queue if d.id != dialog.id]
            if key:
                archive.served(PLATFORM, key)

    async def tick(self, client) -> None:
        if client is None or not history.walk_enabled(PLATFORM):
            return
        if self.task is not None and not self.task.done():
            return
        now = time.time()
        if now - self.last < GAP_S:
            return
        asks = bool(archive.wanted(PLATFORM))
        if not asks and (self.full or not self.queue) and now - self.listed_at < RELIST_S:
            return
        if not self.dialogs or now - self.listed_at > RELIST_S or (asks and not self.listed_at):
            await self._list(client)
        ask = self._asked() if asks else None
        if ask is None and asks and not self.listed_at:
            await self._list(client)             # an ask for a conversation not listed: look once more
            ask = self._asked()
        if ask is None and (self.full or not self.queue):
            return
        self.last = now
        self.task = asyncio.create_task(self._run(client, ask[1], ask[0]) if ask
                                        else self._run(client, self.queue[0]))


walker = Walker()
