#
# views/deeper.py — a search the archive cannot answer asks the PLATFORM for that one conversation (V2-936).
#
# The first import copies a bounded stretch of an account (connectors/messaging/history.py); everything older, and
# every conversation outside it, stays where it is until somebody asks. So a search that NAMES a conversation and
# finds nothing is not «it never happened»: the conversation is asked for — that one, a bounded stretch further
# back — and the answer says so, so the same search is repeated a moment later:
#   · a platform that pages its own history silently (mode «walk») is asked through `archive.want`: by the id of
#     the conversation the archive holds, or by the name he used when it holds none of it;
#   · a platform whose history comes from the phone (mode «at_link») is asked for ONE page of a conversation this
#     card already holds, through the card's own `load_more` — each ask is a notification on his phone, so it is
#     never made for a conversation nobody named;
#   · a mailbox is searched where it lives (`mailbox_fill`, in archive.py) and nothing is walked.
#
import logging

_log = logging.getLogger("zaelar.mensajeria.views")

#: How many conversations one search may ask for.
MAX_ASKS = 3


def ask(names: list[str], platform: str | None = None) -> list[dict]:
    """Ask the platforms for the conversations these names are: `[{platform, chat, how}]` for each ask made (`how`:
    «held» — a conversation the archive has, asked further back; «by_name» — one it has nothing of). Never raises."""
    out: list[dict] = []
    wanted = [n for n in (" ".join(str(x or "").split()) for x in names or []) if len(n) >= 2]
    if not wanted:
        return out
    try:
        from connectors.messaging import archive, history
        for plat, mode in history.MODES.items():
            if mode == "on_demand" or (platform and plat != platform):
                continue
            held = archive.chats(plat)
            for name in wanted:
                low = name.casefold()
                hits = [c for c in held if low in str(c.get("name") or "").casefold()][:MAX_ASKS]
                for c in hits:
                    if len(out) >= MAX_ASKS:
                        return out
                    if mode == "walk":
                        archive.want(plat, c["chatId"])
                    else:
                        from widgets import supervisor as _sup
                        _sup.enqueue_from_thread("mensajeria", "load_more",
                                                 {"platform": plat, "chatId": c["chatId"], "limit": 100})
                    out.append({"platform": plat, "chat": c.get("name") or c["chatId"], "how": "held"})
                if not hits and mode == "walk" and len(out) < MAX_ASKS and archive.want(plat, name=name):
                    out.append({"platform": plat, "chat": name, "how": "by_name"})
    except Exception as e:  # noqa: BLE001 — the search still answers with what the archive holds
        _log.warning(f"on-demand history not asked: {type(e).__name__}: {e}")
    return out
