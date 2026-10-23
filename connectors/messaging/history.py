#
# history.py — how each messaging platform's PAST reaches the communications archive (archive.py).
#
# Two modes, declared here once, because the platforms are not alike:
#   * walk       — the conversation's history lives where only a slow, paged request reaches it (the WhatsApp
#                  phone) or is cheap to page exactly (Telegram). Every chat is walked back to its beginning ONCE,
#                  text only, and from then on the archive grows with what arrives live. A question about two
#                  years ago is answered locally.
#   * on_demand  — the provider keeps everything and searches it well (an IMAP mailbox). Copying a whole mailbox
#                  would be gigabytes of mail nobody asked about, so nothing is walked: a search the archive cannot
#                  answer is asked of the mailbox, and only what it returns is archived.
# In neither mode is the media of the past downloaded: its type travels, the bytes stay at the source. What a
# connector downloads live is kept for the operator's window (widgets/mensajeria/media.py).
#
import os

MODES = {"whatsapp": "walk", "telegram": "walk", "email": "on_demand"}
MAX_PER_CHAT = 20000          # a chat holding this many messages is left where it is
_ENV = {"whatsapp": "WA_BACKFILL", "telegram": "TG_BACKFILL"}


def mode(platform: str) -> str:
    return MODES.get(platform, "on_demand")


def walk_enabled(platform: str) -> bool:
    """A walk-mode platform walks unless its power-user switch (`WA_BACKFILL=0` / `TG_BACKFILL=0`) says not."""
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
