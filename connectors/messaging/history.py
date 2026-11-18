#
# history.py — how each messaging platform's PAST reaches the communications archive (archive.py).
#
# Two modes, declared here once, because the platforms are not alike:
#   * walk       — the account pages its own history exactly and silently (Telegram): the newest conversations are
#                  walked back ONCE, text only, inside the first import's bounds (`policy`, below); from then on
#                  the archive grows with what arrives live, and a conversation somebody asks about is walked
#                  further on demand (`archive.want`).
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

# How MUCH of the past is copied, and how much media stays (V2-936): `config/messaging.default.json` holds the
# numbers and why each; these are the same values, for an install whose file cannot be read.
_DEFAULTS = {"initial_days": 90, "initial_chats": 150, "initial_per_chat": 300, "initial_messages": 30000,
             "deep_messages": 1000, "deep_per_chat": MAX_PER_CHAT,
             "media_file_mb": 20, "media_budget_mb": 4096, "media_disk_ratio": 0.15}
_POLICY: dict = {}


def _files() -> list[str]:
    here = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config")
    return [os.path.join(here, n) for n in ("messaging.default.json", "messaging.json")]


def policy() -> dict:
    """The declared bounds: the repo default, then the deployment's own `config/messaging.json` over it. Read at
    most every few seconds — the walk asks once per page."""
    import json
    import time
    if _POLICY and time.time() - _POLICY["at"] < 5.0:
        return _POLICY["v"]
    out = dict(_DEFAULTS)
    for path in _files():
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                out.update({k: v for k, v in json.load(fh).items() if k in _DEFAULTS and isinstance(v, (int, float))})
        except Exception as e:  # noqa: BLE001 — a broken file says so and the defaults hold
            import logging
            logging.getLogger("zaelar.messaging.history").warning(f"{path} unreadable ({e!r}) — the defaults hold")
    _POLICY.update({"v": out, "at": time.time()})
    return out


def horizon(now: float | None = None) -> float:
    """The instant the FIRST import goes back to (`initial_days`); 0.0 when that bound is off."""
    import time
    days = float(policy()["initial_days"] or 0)
    return (now or time.time()) - days * 86400 if days > 0 else 0.0


def within_first_import(entries: list[dict], held: int = 0, now: float | None = None, *, per_chat: bool = True) -> list[dict]:
    """The entries of ONE conversation the first import keeps: inside the day bound, and the newest that still fit
    under `initial_per_chat` given the `held` already copied. Order is kept. `per_chat=False` keeps the day bound
    alone — for a history the platform hands over once and cannot be asked again for quietly."""
    cut = horizon(now)
    keep = [e for e in entries or [] if not cut or float(e.get("ts") or 0) >= cut]
    cap = int(policy()["initial_per_chat"] or 0) if per_chat else 0
    if cap and len(keep) + held > cap:
        room = max(0, cap - held)
        newest = sorted(keep, key=lambda e: float(e.get("ts") or 0), reverse=True)[:room]
        ids = {id(e) for e in newest}
        keep = [e for e in keep if id(e) in ids]
    return keep


def media_cap_bytes() -> int:
    """The largest file a connector downloads by itself (`media_file_mb`); 0 = no cap."""
    return int(float(policy()["media_file_mb"] or 0) * 1024 * 1024)


def media_budget_bytes(folder: str) -> int:
    """What downloaded media may take in `folder`: the smaller of `media_budget_mb` and `media_disk_ratio` of the
    disk that holds it (a bound that is 0 is off); 0 = no budget."""
    p = policy()
    bounds = []
    if float(p["media_budget_mb"] or 0) > 0:
        bounds.append(int(float(p["media_budget_mb"]) * 1024 * 1024))
    if float(p["media_disk_ratio"] or 0) > 0:
        try:
            import shutil
            bounds.append(int(shutil.disk_usage(folder).total * float(p["media_disk_ratio"])))
        except OSError:
            pass                       # the disk cannot be measured: the absolute bound alone
    return min(bounds) if bounds else 0
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
            row["first_import_days"] = int(policy()["initial_days"] or 0)   # what «not found» may still be behind
        out[p] = row
    return out
