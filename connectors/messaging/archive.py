#
# archive.py — the CANONICAL communications store (V2-628 F0). Append-only, catalogued, cross-platform.
#
# The design rule it exists to serve (operator directive, 2026-09-09): every domain has exactly ONE canonical
# store. Before this module, every message body was written TWICE and kept NOWHERE: the thread store expires
# (KEEP=40/chat · 14 d · 80 threads — its correct behavior as a replay cache) and the `kind='msg'` pill in
# central memory decays in ~2 days (its correct behavior as recall salience). A question about a message from
# a month ago was unanswerable from any store we control. This log is the permanent home; both existing
# surfaces stay what they are — bounded, EXPIRING views over it.
#
# What it is NOT: not a widget store (no UI state, no queues), not memory (nothing here is a personal fact —
# the heart keeps distilling those through its own door), and not an index of the past (nothing is backfilled
# by default; the log grows forward from the same seams that feed the views, including the on-demand
# `fetch_now`/`load_more` landings, per the V2-624 directive).
#
# Own SQLite file in the domain's data dir, WAL, FTS5 external-content kept in sync by an AFTER INSERT
# trigger — append-only means insert is the only write, so triggers cover the whole contract. Every public
# entry point is best-effort and returns instead of raising: the archive must never break the UI store or a
# connector drain (the same stance `store._to_memory` already takes).
#
import hashlib
import logging
import os
import sqlite3
import threading
import time

_LOCK = threading.RLock()
_CONN: sqlite3.Connection | None = None
_PATH: str | None = None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages(
  id        INTEGER PRIMARY KEY,
  platform  TEXT NOT NULL,
  chat_id   TEXT NOT NULL,
  chat_name TEXT NOT NULL DEFAULT '',
  is_group  INTEGER NOT NULL DEFAULT 0,
  sender    TEXT NOT NULL DEFAULT '',
  direction TEXT NOT NULL CHECK(direction IN ('in','out')),
  ts        REAL NOT NULL,
  body      TEXT NOT NULL,
  media_type TEXT NOT NULL DEFAULT '',
  msg_id    TEXT NOT NULL,
  UNIQUE(platform, chat_id, msg_id)
);
CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(platform, chat_id, ts);
CREATE INDEX IF NOT EXISTS idx_messages_ts   ON messages(ts);
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
  body, sender, chat_name, content='messages', content_rowid='id');
CREATE TABLE IF NOT EXISTS backfill(
  platform  TEXT NOT NULL,
  chat_id   TEXT NOT NULL,
  done      INTEGER NOT NULL DEFAULT 0,
  pages     INTEGER NOT NULL DEFAULT 0,
  updated   REAL NOT NULL DEFAULT 0,
  PRIMARY KEY(platform, chat_id)
);
CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
  INSERT INTO messages_fts(rowid, body, sender, chat_name)
  VALUES (new.id, new.body, new.sender, new.chat_name);
END;
"""


def _db_path() -> str:
    from widgets import store as _wstore
    return os.path.join(_wstore.data_dir("mensajeria"), "archive.db")


def _conn() -> sqlite3.Connection:
    global _CONN, _PATH
    path = _db_path()
    with _LOCK:
        if _CONN is not None and _PATH == path:
            return _CONN
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.executescript(_SCHEMA)
        _CONN, _PATH = conn, path
        return conn


def reset() -> None:
    """Forget the cached connection (tests move the data dir between cases)."""
    global _CONN, _PATH
    with _LOCK:
        if _CONN is not None:
            try:
                _CONN.close()
            except Exception:  # noqa: BLE001
                pass
        _CONN, _PATH = None, None


def _msg_id(m: dict, platform: str, chat_id, ts: float, body: str) -> str:
    """The platform's own id when it gave one; a content hash otherwise. Some transports hand us rows with no
    id (a fetched mail grouped by sender) — those must still be idempotent on a re-fetch, and hashing what
    identifies the message (where, when, what) is exactly that."""
    for k in ("messageId", "id"):
        v = m.get(k)
        if v is not None and str(v).strip():
            return str(v)
    raw = f"{platform}|{chat_id}|{ts:.0f}|{body}"
    return "h:" + hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()[:16]


def _norm(m: dict, platform: str, chat_id, *, direction: str | None, chat_name: str, is_group) -> tuple | None:
    """One archive row from EITHER shape this system speaks: an inbox item (`from`/`body`/`ts`/`messageId`/
    `isGroup`/`group`) or a thread message (`who`/`body`/`ts`/`dir`/`id`). Empty bodies are not archived —
    a media-only row still lands, carrying its media_type."""
    body = str(m.get("body") or "").strip()
    media = str(m.get("mediaType") or "")
    if not body and not media:
        return None
    try:
        ts = float(m.get("ts") or m.get("timestamp") or time.time())
    except (TypeError, ValueError):
        ts = time.time()
    d = direction or ("out" if m.get("dir") == "out" else "in")
    sender = str(m.get("from") or m.get("who") or m.get("senderName") or "")
    name = str(chat_name or m.get("group") or "")
    grp = bool(is_group) if is_group is not None else bool(m.get("isGroup"))
    return (str(platform), str(chat_id), name, 1 if grp else 0, sender, d, ts, body, media,
            _msg_id(m, platform, chat_id, ts, body))


def record(platform: str, chat_id, msgs: list[dict], *, direction: str | None = None,
           chat_name: str = "", is_group=None) -> int:
    """Append messages of one chat. Idempotent by (platform, chat_id, msg_id) — a connector retry, a
    re-fetch of the same window or a thread echo inserts nothing twice. Returns how many rows are new."""
    if not msgs:
        return 0
    try:
        rows = [r for r in (_norm(m, platform, chat_id, direction=direction, chat_name=chat_name,
                                  is_group=is_group) for m in msgs if isinstance(m, dict)) if r]
        if not rows:
            return 0
        with _LOCK:
            conn = _conn()
            with conn:
                # NOT total_changes: the FTS trigger fires per new row and doubles that count. rowcount
                # counts only the statement's own inserts, and OR IGNORE keeps skipped rows out of it.
                cur = conn.executemany(
                    "INSERT OR IGNORE INTO messages"
                    " (platform, chat_id, chat_name, is_group, sender, direction, ts, body, media_type, msg_id)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
                return max(0, cur.rowcount)
    except Exception:  # noqa: BLE001 — the archive must never break the store that feeds it
        return 0


def record_items(items: list[dict]) -> int:
    """The inbound-triage seam: inbox items carry their platform/chat per item."""
    n = 0
    for it in items or []:
        if isinstance(it, dict):
            n += record(str(it.get("platform") or "?"), it.get("chatId") or "?", [it], direction="in")
    return n


def search(q: str | None = None, *, sender: str | None = None, chat: str | None = None,
           platform: str | None = None, since: float | None = None, until: float | None = None,
           direction: str | None = None, limit: int = 20) -> list[dict]:
    """The catalogued lookup the platforms never gave us. `q` walks the FTS index; every other argument is a
    structured filter (sender/chat match by substring, case-insensitive — the operator says «the school», not
    an exact display name). Newest first."""
    try:
        conn = _conn()
        where, args = [], []
        if q and str(q).strip():
            fts = " ".join('"' + t.replace('"', "") + '"' for t in str(q).split())
            where.append("m.id IN (SELECT rowid FROM messages_fts WHERE messages_fts MATCH ?)")
            args.append(fts)
        for field, val in (("sender", sender), ("chat_name", chat)):
            if val and str(val).strip():
                where.append(f"m.{field} LIKE ? COLLATE NOCASE")
                args.append(f"%{val}%")
        if platform:
            where.append("m.platform = ?"); args.append(str(platform))
        if direction in ("in", "out"):
            where.append("m.direction = ?"); args.append(direction)
        if since is not None:
            where.append("m.ts >= ?"); args.append(float(since))
        if until is not None:
            where.append("m.ts <= ?"); args.append(float(until))
        sql = "SELECT m.* FROM messages m"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY m.ts DESC LIMIT ?"
        args.append(max(1, min(int(limit or 20), 200)))
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    except Exception:  # noqa: BLE001
        return []


def _fts_term(t: str) -> str:
    return '"' + str(t).replace('"', "") + '"'


def doc_count(term: str) -> int:
    """How many archived messages contain `term` (FTS) — how COMMON a word is here. 0 on any failure."""
    try:
        conn = _conn()
        return int(conn.execute("SELECT count(*) FROM messages_fts WHERE messages_fts MATCH ?",
                                (_fts_term(term),)).fetchone()[0])
    except Exception:  # noqa: BLE001
        return 0


def ranked(terms: list[str], *, platform: str | None = None, limit: int = 8) -> list[dict]:
    """Messages matching ANY of `terms`, best first by BM25 — the free-text question's lookup.

    `search()` ANDs every word, which is right for a structured `q` and wrong for a sentence: «has inworld sent
    any email recently» matches nothing, because no message holds all seven words. BM25 over an OR weighs each
    word by how rare it is here, so the one that names the sender outranks «email» and «any» without anybody
    having to list which words are filler — in any language."""
    terms = [t for t in (str(x).strip() for x in (terms or [])) if t][:12]
    if not terms:
        return []
    try:
        conn = _conn()
        named = _naming_terms(conn, terms)
        if named:
            return _ranked_by_name(conn, named, platform=platform, limit=limit)
        sql = ("SELECT m.*, bm25(messages_fts) AS score FROM messages_fts JOIN messages m ON m.id = messages_fts.rowid"
               " WHERE messages_fts MATCH ?")
        args: list = [" OR ".join(_fts_term(t) for t in terms)]
        if platform:
            sql += " AND m.platform = ?"
            args.append(str(platform))
        sql += " ORDER BY score LIMIT ?"
        args.append(max(1, min(int(limit or 8), 50)))
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    except Exception:  # noqa: BLE001
        return []


def _naming_terms(conn, terms: list[str]) -> list[str]:
    """The words of a question that NAME a sender or a chat: they appear in the sender/chat_name column, and they
    are among the less common words of the question here (a group called «The …» must not make «the» a name).

    Demo pass 35 (2026-09-29, E1): «Is there any email from Inworld (inworld.ai) in the inbox? What is it about and
    when did it arrive?» ranked four long Telegram posts first — BM25 over the OR of thirteen words adds up the
    filler, and a trading channel holds a lot of it. No list of filler words, in any language: the column says
    who is a sender, and the counts say which words are common."""
    df = {t: doc_count(t) for t in terms}
    seen = sorted(n for n in df.values() if n > 0)
    if not seen:
        return []
    median = seen[len(seen) // 2]
    # …or rare in the ARCHIVE as a whole (demo pass 46, 2026-09-29): «inworld» had grown to 21 messages — every
    # earlier forward of the receipt mentions it — past the question's median word (10), and stopped being read
    # as a sender. A word in under 2% of everything we hold is not filler whatever the question around it.
    try:
        total = int(conn.execute("SELECT count(*) FROM messages").fetchone()[0])
    except Exception:  # noqa: BLE001
        total = 0
    out = []
    for t in terms:
        if not df[t] or (df[t] > median and not (total and df[t] <= 0.02 * total)):
            continue
        hit = conn.execute("SELECT count(*) FROM messages_fts WHERE messages_fts MATCH ?",
                           ("{sender chat_name}: " + _fts_term(t),)).fetchone()[0]
        if hit:
            out.append(t)
    return out


def _ranked_by_name(conn, named: list[str], *, platform: str | None, limit: int) -> list[dict]:
    """Rows from the named sender/chat first, then rows that only mention the name — each group by BM25 over the
    naming words alone, so filler never weighs in."""
    q = " OR ".join(_fts_term(t) for t in named)
    lim = max(1, min(int(limit or 8), 50))
    base = ("SELECT m.*, bm25(messages_fts) AS score FROM messages_fts JOIN messages m ON m.id = messages_fts.rowid"
            " WHERE messages_fts MATCH ?")
    tail = (" AND m.platform = ?" if platform else "") + " ORDER BY score LIMIT ?"
    out, ids = [], set()
    for match in ("{sender chat_name}: (" + q + ")", q):
        args: list = [match] + ([str(platform)] if platform else []) + [lim]
        for r in conn.execute(base + tail, args).fetchall():
            if r["id"] not in ids and len(out) < lim:
                ids.add(r["id"])
                out.append(dict(r))
    return out


def replied(platform: str, chat_id, after_ts: float) -> dict | None:
    """«Did we ever answer it?» — the first OUT row in that chat after the instant. A JOIN, not a memory."""
    try:
        row = _conn().execute(
            "SELECT * FROM messages WHERE platform=? AND chat_id=? AND direction='out' AND ts>? "
            "ORDER BY ts LIMIT 1", (str(platform), str(chat_id), float(after_ts))).fetchone()
        return dict(row) if row else None
    except Exception:  # noqa: BLE001
        return None


def chats(platform: str, limit: int = 600) -> list[dict]:
    """Every conversation of `platform` this log has a message of, newest first, with its LAST message — the
    chat list's memory of what the connector can no longer enumerate (WhatsApp tells a device its chats once)."""
    try:
        rows = _conn().execute(
            "SELECT m.chat_id, m.chat_name, m.is_group, m.ts, m.body, m.media_type, m.direction, m.msg_id "
            "FROM messages m JOIN (SELECT chat_id, MAX(ts) ts FROM messages WHERE platform=? GROUP BY chat_id) l "
            "ON m.chat_id=l.chat_id AND m.ts=l.ts WHERE m.platform=? ORDER BY m.ts DESC LIMIT ?",
            (str(platform), str(platform), int(limit))).fetchall()
    except Exception as e:  # noqa: BLE001
        import logging
        logging.getLogger("zaelar.messaging.archive").warning(f"archive chats unreadable: {type(e).__name__}")
        return []
    out, seen = [], set()
    for r in rows:
        if r["chat_id"] in seen:
            continue
        seen.add(r["chat_id"])
        out.append({"chatId": r["chat_id"], "name": r["chat_name"] or "",
                    "kind": "group" if r["is_group"] else "person", "ts": float(r["ts"] or 0),
                    "preview": (r["body"] or "")[:160], "mediaType": r["media_type"] or "",
                    "fromMe": r["direction"] == "out", "lastId": r["msg_id"] or ""})
    return out


# ── history backfill: which chats have been walked back to their beginning ─────────────────────────────
def oldest(platform: str, chat_id) -> dict | None:
    """The OLDEST message held of one chat — the anchor a backfill asks the platform to go back from."""
    try:
        row = _conn().execute("SELECT msg_id, direction, ts FROM messages WHERE platform=? AND chat_id=? "
                              "ORDER BY ts LIMIT 1", (str(platform), str(chat_id))).fetchone()
        return dict(row) if row else None
    except Exception as e:  # noqa: BLE001
        import logging
        logging.getLogger("zaelar.messaging.archive").warning(f"archive oldest unreadable: {type(e).__name__}")
        return None


def count(platform: str, chat_id) -> int:
    try:
        return int(_conn().execute("SELECT COUNT(*) FROM messages WHERE platform=? AND chat_id=?",
                                   (str(platform), str(chat_id))).fetchone()[0])
    except Exception as e:  # noqa: BLE001 — an unreadable count reads as nothing held
        import logging
        logging.getLogger("zaelar.messaging.archive").warning(f"archive count unreadable: {type(e).__name__}")
        return 0


def backfill_state(platform: str, chat_id) -> dict:
    try:
        row = _conn().execute("SELECT done, pages, updated FROM backfill WHERE platform=? AND chat_id=?",
                              (str(platform), str(chat_id))).fetchone()
        return dict(row) if row else {"done": 0, "pages": 0, "updated": 0.0}
    except Exception:  # noqa: BLE001 — unknown state reads as «not walked yet»
        return {"done": 0, "pages": 0, "updated": 0.0}


def backfill_mark(platform: str, chat_id, *, done: bool | None = None, page: bool = False) -> None:
    """Record progress on one chat's walk back: one more page arrived, or the walk is over."""
    try:
        with _LOCK:
            conn = _conn()
            with conn:
                conn.execute("INSERT OR IGNORE INTO backfill(platform, chat_id, updated) VALUES (?,?,?)",
                             (str(platform), str(chat_id), time.time()))
                conn.execute("UPDATE backfill SET pages=pages+?, done=COALESCE(?, done), updated=? "
                             "WHERE platform=? AND chat_id=?",
                             (1 if page else 0, None if done is None else (1 if done else 0), time.time(),
                              str(platform), str(chat_id)))
    except Exception as e:  # noqa: BLE001
        import logging
        logging.getLogger("zaelar.messaging.archive").warning(f"backfill state not saved: {type(e).__name__}")


def backfill_stats(platform: str) -> dict:
    """How far the walk back has gone: chats finished, chats started, messages held."""
    try:
        c = _conn()
        done = c.execute("SELECT COUNT(*) FROM backfill WHERE platform=? AND done=1", (platform,)).fetchone()[0]
        started = c.execute("SELECT COUNT(*) FROM backfill WHERE platform=?", (platform,)).fetchone()[0]
        msgs = c.execute("SELECT COUNT(*) FROM messages WHERE platform=?", (platform,)).fetchone()[0]
        return {"done": int(done), "started": int(started), "messages": int(msgs)}
    except Exception:  # noqa: BLE001 — a stats line never breaks its caller
        return {"done": 0, "started": 0, "messages": 0}


def stats() -> dict:
    """Row count and time span — the health line a brief or a doctor can print."""
    try:
        r = _conn().execute("SELECT COUNT(*) n, MIN(ts) lo, MAX(ts) hi FROM messages").fetchone()
        return {"messages": r["n"], "oldest": r["lo"], "newest": r["hi"]}
    except Exception:  # noqa: BLE001
        return {"messages": 0, "oldest": None, "newest": None}


#: Rows one `page()` call returns at most (V2-808: the memory viewer never asks for a whole store).
PAGE_CAP = 200


def page(*, platform: str | None = None, q: str | None = None, before_ts: float | None = None,
         before_id: int | None = None, limit: int = 50) -> dict:
    """One page of the archive, newest first, for a viewer. The cursor is the last row's `(ts, id)`: ids follow
    insertion order and a backfill inserts old messages late, so `ts` orders and `id` breaks ties. `q` walks the
    FTS index. Returns `{items, more, next: {ts, id}}`; never raises."""
    n = max(1, min(int(limit or 50), PAGE_CAP))
    try:
        where, args = [], []
        if q and str(q).strip():
            where.append("id IN (SELECT rowid FROM messages_fts WHERE messages_fts MATCH ?)")
            args.append(" ".join(_fts_term(t) for t in str(q).split()))
        if platform:
            where.append("platform = ?"); args.append(str(platform))
        if before_ts is not None and before_id:
            where.append("(ts < ? OR (ts = ? AND id < ?))"); args += [float(before_ts), float(before_ts), int(before_id)]
        sql = ("SELECT id, platform, chat_name, is_group, sender, direction, ts, body, media_type FROM messages"
               + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY ts DESC, id DESC LIMIT ?")
        rows = [dict(r) for r in _conn().execute(sql, (*args, n + 1)).fetchall()]
    except Exception as e:  # noqa: BLE001
        logging.getLogger("zaelar.messaging.archive").warning("page failed: %s", e)
        return {"items": [], "more": False, "next": None}
    items = rows[:n]
    nxt = {"ts": items[-1]["ts"], "id": items[-1]["id"]} if items else None
    return {"items": items, "more": len(rows) > n, "next": nxt}


def totals(week_s: int = 7 * 86400) -> dict:
    """COUNTs for an overview: per platform, the last week, and the file's size on disk. Never raises."""
    try:
        conn = _conn()
        by = {r["platform"]: int(r["n"]) for r in
              conn.execute("SELECT platform, COUNT(*) n FROM messages GROUP BY platform").fetchall()}
        week = int(conn.execute("SELECT COUNT(*) FROM messages WHERE ts >= ?",
                                (time.time() - week_s,)).fetchone()[0])
    except Exception as e:  # noqa: BLE001
        logging.getLogger("zaelar.messaging.archive").warning("totals failed: %s", e)
        by, week = {}, 0
    size = 0
    for suffix in ("", "-wal"):
        p = _db_path() + suffix
        size += os.path.getsize(p) if os.path.exists(p) else 0
    return {"total": sum(by.values()), "by_platform": by, "week": week, "bytes": size}


def per_day(days: int = 30) -> list[dict]:
    """Messages per local day over the last `days`. Never raises."""
    try:
        rows = _conn().execute(
            "SELECT date(ts,'unixepoch','localtime') d, COUNT(*) n FROM messages WHERE ts >= ? GROUP BY d ORDER BY d",
            (time.time() - max(1, min(int(days or 30), 366)) * 86400,)).fetchall()
        return [{"day": r["d"], "messages": int(r["n"])} for r in rows]
    except Exception as e:  # noqa: BLE001
        logging.getLogger("zaelar.messaging.archive").warning("per-day count failed: %s", e)
        return list()
