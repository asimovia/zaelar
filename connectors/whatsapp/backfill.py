#
# backfill.py — walk every WhatsApp chat back to its beginning, ONCE, into the communications archive.
#
# WhatsApp keeps a conversation's history on the PHONE. A linked device gets a recent slice at pairing and then
# only what happens live, and the only way to the rest is to ask the phone, one page of at most 50 messages
# older than a message we already hold (`fetchMessageHistory`). So a question about something said two years
# ago cannot be answered by asking at that moment: the walk has to have happened before. This walks each chat,
# newest chat first, one page at a time and one request in flight, until the phone has nothing older; what
# lands goes straight to `connectors/messaging/archive.py` (the canonical store every search reads), never to
# the widget's conversations or the inbox — the past must not interrupt anybody. Live messages keep arriving
# through the ordinary path, so after one walk the archive simply grows.
#
# The phone being offline looks exactly like a chat with nothing older: no answer. So a chat is only marked
# finished for having produced nothing when the phone has proved it is answering; a run of silences with no
# answer anywhere PAUSES the walk instead, and the chats it would have written off are left to retry.
#
import time

from loguru import logger

from connectors.messaging import archive, history
from connectors.whatsapp import client, config

PLATFORM = "whatsapp"
PAGE = 50                 # the most the phone serves per request
WAIT_S = 40               # how long a page may take before the request counts as unanswered
GAP_S = 4                 # between requests: one walk, paced like a person scrolling
OWN_S = 180               # scrollback for a chat asked this recently is the walk's, not the widget's
RELIST_S = 600            # the chat book is re-read this often for chats that appeared since
MAX_PER_CHAT = history.MAX_PER_CHAT
SILENT_BEFORE_PAUSE = 3   # this many unanswered first requests with no answer anywhere = the phone is away
PAUSE_S = 1800


class Walker:
    def __init__(self):
        self.queue: list[dict] = []
        self.listed_at = 0.0
        self.chat: str | None = None
        self.asked_at = 0.0
        self.anchor_ts = 0.0
        self.progress = False
        self.recent: dict[str, float] = {}
        self.answered_at = 0.0          # last time the phone answered ANY page
        self.silent: list[str] = []     # chats written off since the phone last answered
        self.paused_until = 0.0

    def owns(self, chat_id) -> bool:
        """Is scrollback for this chat the walk's? (A page can arrive after the walk has moved on.)"""
        return time.time() < self.recent.get(str(chat_id), 0.0)

    def landed(self, chat_id, entries: list[dict], *, name: str = "", is_group=None) -> int:
        """Scrollback the phone sent for the walk: archive it and note whether it went further back."""
        cid = str(chat_id)
        # A message without its own time would be filed as «now» — a two-year-old line posing as today's.
        entries = [e for e in entries if e.get("ts")]
        n = archive.record(PLATFORM, cid, entries, chat_name=name, is_group=is_group)
        o = archive.oldest(PLATFORM, cid)
        if cid == self.chat and o and float(o["ts"]) < self.anchor_ts:
            archive.backfill_mark(PLATFORM, cid, page=True)
            self.progress = True
            self.answered_at = time.time()
            for c in self.silent:                # written off before the phone had proved it answers
                archive.backfill_mark(PLATFORM, c, done=False)
            if self.silent:
                self.listed_at = 0.0             # relisted on the next tick, so they come back
            self.silent = []
            self.chat = None                     # the next tick asks the next page of the same chat
        return n

    async def _list(self) -> None:
        got = await client.get_chats(None, 2000)
        rows = [c for c in got.get("chats") or [] if c.get("id")]
        self.queue = [c for c in rows if not archive.backfill_state(PLATFORM, c["id"]).get("done")]
        self.listed_at = time.time()

    def _anchor(self, row: dict) -> dict | None:
        o = archive.oldest(PLATFORM, row["id"])
        if o and o.get("msg_id") and not str(o["msg_id"]).startswith("h:"):
            return {"id": str(o["msg_id"]), "ts": float(o["ts"]), "fromMe": o.get("direction") == "out",
                    "include": False}
        if row.get("lastId"):
            return {"id": str(row["lastId"]), "ts": float(row.get("ts") or 0), "fromMe": bool(row.get("fromMe")),
                    "include": True}
        return None

    def _finish(self, cid: str, why: str) -> None:
        archive.backfill_mark(PLATFORM, cid, done=True)
        self.queue = [c for c in self.queue if c.get("id") != cid]
        logger.info(f"WhatsApp backfill: {cid} {why} ({archive.count(PLATFORM, cid)} messages held)")

    def _unanswered(self, cid: str) -> None:
        st = archive.backfill_state(PLATFORM, cid)
        if st.get("pages"):
            self._finish(cid, "reached its beginning")
            return
        if self.answered_at and time.time() - self.answered_at < RELIST_S:
            self._finish(cid, "has nothing older on the phone")
            return
        self.silent.append(cid)
        self._finish(cid, "gave no answer")
        if len(self.silent) >= SILENT_BEFORE_PAUSE:
            for c in self.silent:                # not written off: the phone was simply not answering
                archive.backfill_mark(PLATFORM, c, done=False)
            logger.warning(f"WhatsApp backfill: the phone is not answering — paused {PAUSE_S // 60} min")
            self.silent, self.queue, self.listed_at = [], [], 0.0
            self.paused_until = time.time() + PAUSE_S

    async def tick(self) -> None:
        if not config.backfill_enabled():
            return
        now = time.time()
        if now < self.paused_until:
            return
        if self.chat is not None:
            if now - self.asked_at < WAIT_S:
                return
            cid, self.chat = self.chat, None
            self._unanswered(cid)
        if now - self.asked_at < GAP_S:
            return
        if not self.queue or now - self.listed_at > RELIST_S:
            await self._list()
        while self.queue:
            row = self.queue[0]
            cid = row["id"]
            if archive.count(PLATFORM, cid) >= MAX_PER_CHAT:
                self._finish(cid, "is past the per-chat cap")
                continue
            anchor = self._anchor(row)
            if anchor is None:
                # Nothing to go back FROM yet (a group seeded by name, silent since pairing). Not finished: the
                # first message it gets is the anchor, and the next listing picks it up.
                self.queue.pop(0)
                continue
            ack = await client.fetch_history(cid, anchor["id"], anchor["ts"], PAGE,
                                             oldest_from_me=anchor["fromMe"], include_anchor=anchor["include"])
            self.asked_at = time.time()
            if not (ack or {}).get("available"):
                logger.warning(f"WhatsApp backfill: the bridge cannot ask for history: {(ack or {}).get('error')}")
                self.paused_until = self.asked_at + PAUSE_S
                return
            self.chat, self.anchor_ts, self.progress = cid, anchor["ts"], False
            self.recent[cid] = self.asked_at + OWN_S
            return
        if not self.queue and self.listed_at:
            stats = archive.backfill_stats(PLATFORM)
            logger.info(f"WhatsApp backfill: every chat walked — {stats}")
            self.listed_at = time.time()
            self.paused_until = time.time() + RELIST_S       # new chats are picked up on the next listing


walker = Walker()
