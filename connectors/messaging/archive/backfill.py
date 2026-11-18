# History backfill: which chats have been walked back to their beginning, and the anchors the walk needs.
import logging
import time


def oldest(platform: str, chat_id) -> dict | None:
    """The OLDEST message held of one chat — the anchor a backfill asks the platform to go back from."""
    try:
        row = _svc._conn().execute("SELECT msg_id, direction, ts FROM messages WHERE platform=? AND chat_id=? "
                                   "ORDER BY ts LIMIT 1", (str(platform), str(chat_id))).fetchone()
        return dict(row) if row else None
    except Exception as e:  # noqa: BLE001
        logging.getLogger("zaelar.messaging.archive").warning(f"archive oldest unreadable: {type(e).__name__}")
        return None


def count(platform: str, chat_id) -> int:
    try:
        return int(_svc._conn().execute("SELECT COUNT(*) FROM messages WHERE platform=? AND chat_id=?",
                                        (str(platform), str(chat_id))).fetchone()[0])
    except Exception as e:  # noqa: BLE001 — an unreadable count reads as nothing held
        logging.getLogger("zaelar.messaging.archive").warning(f"archive count unreadable: {type(e).__name__}")
        return 0


def backfill_state(platform: str, chat_id) -> dict:
    try:
        row = _svc._conn().execute("SELECT done, pages, updated FROM backfill WHERE platform=? AND chat_id=?",
                                   (str(platform), str(chat_id))).fetchone()
        return dict(row) if row else {"done": 0, "pages": 0, "updated": 0.0}
    except Exception as e:  # noqa: BLE001 — unknown state reads as «not walked yet»
        logging.getLogger("zaelar.messaging.archive").warning(f"backfill state unreadable: {type(e).__name__}")
        return {"done": 0, "pages": 0, "updated": 0.0}


def backfill_mark(platform: str, chat_id, *, done: bool | None = None, page: bool = False) -> None:
    """Record progress on one chat's walk back: one more page arrived, or the walk is over."""
    try:
        with _svc._LOCK:
            conn = _svc._conn()
            with conn:
                conn.execute("INSERT OR IGNORE INTO backfill(platform, chat_id, updated) VALUES (?,?,?)",
                             (str(platform), str(chat_id), time.time()))
                conn.execute("UPDATE backfill SET pages=pages+?, done=COALESCE(?, done), updated=? "
                             "WHERE platform=? AND chat_id=?",
                             (1 if page else 0, None if done is None else (1 if done else 0), time.time(),
                              str(platform), str(chat_id)))
    except Exception as e:  # noqa: BLE001
        logging.getLogger("zaelar.messaging.archive").warning(f"backfill state not saved: {type(e).__name__}")


#: The prefix of a wanted conversation known only by its NAME (the archive holds none of it yet).
BY_NAME = "name:"


def want(platform: str, chat_id="", name: str = "") -> bool:
    """Ask for ONE conversation to be copied further back (V2-936): by its id, or — when the archive holds nothing
    of it — by the name somebody used, which the connector looks up on the platform. Idempotent while pending;
    it also reopens a walk the first import closed. True when the ask was written."""
    key = str(chat_id or "").strip() or (BY_NAME + " ".join(str(name or "").split()).casefold() if str(name or "").strip() else "")
    if not platform or not key:
        return False
    try:
        with _svc._LOCK:
            conn = _svc._conn()
            with conn:
                conn.execute("INSERT OR IGNORE INTO backfill(platform, chat_id, updated) VALUES (?,?,?)",
                             (str(platform), key, time.time()))
                conn.execute("UPDATE backfill SET want=? WHERE platform=? AND chat_id=? AND want=0",
                             (time.time(), str(platform), key))
        return True
    except Exception as e:  # noqa: BLE001
        logging.getLogger("zaelar.messaging.archive").warning(f"history ask not saved: {type(e).__name__}")
        return False


def wanted(platform: str) -> list[dict]:
    """The conversations asked for on demand and not served yet, oldest ask first: `{chat_id, want, name}`
    (`name` set when it was asked by name)."""
    try:
        rows = _svc._conn().execute("SELECT chat_id, want FROM backfill WHERE platform=? AND want>0 ORDER BY want",
                                    (str(platform),)).fetchall()
        return [{"chat_id": r["chat_id"], "want": float(r["want"]),
                 "name": r["chat_id"][len(BY_NAME):] if str(r["chat_id"]).startswith(BY_NAME) else ""} for r in rows]
    except Exception as e:  # noqa: BLE001 — unreadable asks read as none
        logging.getLogger("zaelar.messaging.archive").warning(f"history asks unreadable: {type(e).__name__}")
        return []


def served(platform: str, chat_id) -> None:
    """An on-demand ask is over (served, or nothing to serve it with). An ask by name leaves no row behind."""
    try:
        with _svc._LOCK:
            conn = _svc._conn()
            with conn:
                if str(chat_id).startswith(BY_NAME):
                    conn.execute("DELETE FROM backfill WHERE platform=? AND chat_id=?", (str(platform), str(chat_id)))
                else:
                    conn.execute("UPDATE backfill SET want=0, updated=? WHERE platform=? AND chat_id=?",
                                 (time.time(), str(platform), str(chat_id)))
    except Exception as e:  # noqa: BLE001
        logging.getLogger("zaelar.messaging.archive").warning(f"history ask not closed: {type(e).__name__}")


def held(platform: str, since: float = 0.0) -> int:
    """How many messages of `platform` the archive holds (from `since` on)."""
    try:
        return int(_svc._conn().execute("SELECT COUNT(*) FROM messages WHERE platform=? AND ts>=?",
                                        (str(platform), float(since))).fetchone()[0])
    except Exception as e:  # noqa: BLE001
        logging.getLogger("zaelar.messaging.archive").warning(f"archive chat count unreadable: {type(e).__name__}")
        return 0


def backfill_stats(platform: str) -> dict:
    """How far the walk back has gone: chats finished, chats started, messages held."""
    try:
        c = _svc._conn()
        done = c.execute("SELECT COUNT(*) FROM backfill WHERE platform=? AND done=1", (platform,)).fetchone()[0]
        started = c.execute("SELECT COUNT(*) FROM backfill WHERE platform=? AND chat_id NOT LIKE 'name:%'",
                            (platform,)).fetchone()[0]
        msgs = c.execute("SELECT COUNT(*) FROM messages WHERE platform=?", (platform,)).fetchone()[0]
        return {"done": int(done), "started": int(started), "messages": int(msgs)}
    except Exception:  # noqa: BLE001 — a stats line never breaks its caller
        return {"done": 0, "started": 0, "messages": 0}


# Read back through the facade (V2-778 F1): tests patch `_db_path`/`_conn` there.
from connectors.messaging import archive as _svc  # noqa: E402
