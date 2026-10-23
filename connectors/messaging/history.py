#
# history.py — how each messaging platform's PAST reaches the communications archive (archive.py).
#
# Two modes, declared here once, because the platforms are not alike:
#   * walk       — the account pages its own history exactly and silently (Telegram): every chat is walked back
#                  to its beginning ONCE, text only, and from then on the archive grows with what arrives live.
#   * at_link    — the history reaches a linked device only from the PHONE (WhatsApp), and every request for more
#                  is a notification on it. So the past is what the phone sends when the device is paired, archived
#                  once (bridge GET /sync), and live after that — never a walk.
#   * on_demand  — the provider keeps everything and searches it well (an IMAP mailbox). Copying a whole mailbox
#                  would be gigabytes of mail nobody asked about, so nothing is walked: a search the archive cannot
#                  answer is asked of the mailbox, and only what it returns is archived.
# In neither mode is the media of the past downloaded: its type travels, the bytes stay at the source. What a
# connector downloads live is kept for the operator's window (widgets/mensajeria/media.py).
#
import os

# WhatsApp is NOT walked: every on-demand history request makes the phone show a «sync finished» notification,
# so a walk of a whole account is a notification every few seconds (reported by the operator, 2026-10-23). Its past
# arrives the way the phone itself offers it — the history sync at pairing (`at_link`) — and live after that.
MODES = {"whatsapp": "at_link", "telegram": "walk", "email": "on_demand"}
MAX_PER_CHAT = 20000          # a chat holding this many messages is left where it is
_ENV = {"telegram": "TG_BACKFILL"}


def mode(platform: str) -> str:
    return MODES.get(platform, "on_demand")


def walk_enabled(platform: str) -> bool:
    """A walk-mode platform walks unless its power-user switch (`TG_BACKFILL=0`) says not."""
    if mode(platform) != "walk":
        return False
    return os.getenv(_ENV.get(platform, ""), "1") != "0"


def coverage() -> dict:
    """Per platform: its mode and, for a walk, how far it has got — what a search answer tells the model so
    «nothing found» is never said over a past that was simply not walked yet."""
    from connectors.messaging import archive
    out = {}
    for p, m in MODES.items():
        row = {"mode": m}
        if m == "walk":
            row.update(archive.backfill_stats(p))
        out[p] = row
    return out
