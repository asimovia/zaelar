#
# server/memory_viewer_api.py — the HTTP face of the memory viewer (V2-808): every store the agent keeps, counted
# and listed in pages, never loaded whole.
#
# The viewer is one screen with one tab per store. What this router guarantees, store by store:
#
#   * totals are COUNTs (or a directory walk, cached) — `GET /api/memory/viewer/stats`, cached a few seconds;
#   * every list has a server cap, a cursor and `more` — the client cannot ask for more than the cap;
#   * the graph is aggregated by `memory.viewer.graph` and bounded by the node budget the client sends.
#
# Each store is read through its owner where the owner has a read (memory, the message archive, the widget
# store); the tables with no read of their own (rules, learnt phrases, the event log, the vault) are COUNTED
# through a read-only connection — a number, never a row, and for the vault never anything but the number.
#
import asyncio
import json
import mimetypes
import os
import sqlite3
import threading
import time

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

from memory import api as memapi
from widgets.mensajeria import media as _media

router = APIRouter()

#: Files per page (thumbnails), and the other lists' cap.
FILES_CAP = 60
LIST_CAP = 200
#: What a connector writes into the messaging data dir — the same prefixes its media sweep owns.
# The stored-file prefixes are declared once, where the files are written (`widgets/mensajeria/media.py`).
_MEDIA_PREFIXES = _media.PREFIXES


def _is_image(name: str) -> bool:
    """A raster image by its declared type (never SVG: a thumbnail is served same-origin)."""
    kind = mimetypes.guess_type(name)[0] or ""
    return kind.startswith("image/") and "svg" not in kind
_STATS_TTL_S = 8.0
_DIRS_TTL_S = 600.0
_THUMB_PX = 240

_lock = threading.Lock()
_stats_cache: dict = {"at": 0.0, "body": None}
_dirs: dict = {"at": 0.0, "rows": None, "running": False}
_media: dict = {"at": 0.0, "rows": None}


def _note(what: str, e: Exception) -> None:
    from voice.observer import emit
    emit("memory", f"viewer: {what} failed", text=str(e)[:160], extra={"module": "server.memory_viewer_api"})


def _widgets_root() -> str:
    from widgets import store
    return store.DATA_DIR


def _clamp(v, cap: int, default: int) -> int:
    try:
        return max(1, min(int(v), cap))
    except (TypeError, ValueError):
        return default


# ── counts of the tables that have no read of their own ─────────────────────────────────────────────────────
def _table_counts() -> dict:
    from bus import log as buslog
    out = {"rules": 0, "phrases": 0, "paraphrases": 0, "events": 0, "events_week": 0, "vault": 0, "tasks": 0}
    path = str(buslog.db_path())
    if not os.path.exists(path):
        return out
    week_ms = (time.time() - 7 * 86400) * 1000
    queries = {"rules": ("SELECT COUNT(*) FROM rules", ()), "phrases": ("SELECT COUNT(*) FROM action_map", ()),
               "paraphrases": ("SELECT COUNT(*) FROM paraphrase_index", ()),
               "events": ("SELECT COUNT(*) FROM events", ()),
               "events_week": ("SELECT COUNT(*) FROM events WHERE ts_ms >= ?", (week_ms,)),
               "vault": ("SELECT COUNT(*) FROM vault_secrets", ()), "tasks": ("SELECT COUNT(*) FROM tasks", ())}
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
    try:
        have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for key, (sql, args) in queries.items():
            table = sql.split(" FROM ")[1].split()[0]
            if table in have:
                out[key] = int(conn.execute(sql, args).fetchone()[0] or 0)
    finally:
        conn.close()
    return out


# ── files: the media the connectors downloaded + what he dropped on the agent ──────────────────────────────
def _media_rows() -> list[dict]:
    """The media files, newest first. A directory listing (no content read), cached 30 s."""
    now = time.monotonic()
    with _lock:
        if _media["rows"] is not None and now - _media["at"] < 30:
            return _media["rows"]
    folder = os.path.join(_widgets_root(), "mensajeria")
    rows = []
    if os.path.isdir(folder):
        for e in os.scandir(folder):
            if e.is_file(follow_symlinks=False) and e.name.startswith(_MEDIA_PREFIXES):
                st = e.stat(follow_symlinks=False)
                kind = e.name.split("_", 1)[0]
                if _is_image(e.name):
                    kind = "img"
                rows.append({"name": e.name, "kind": kind, "bytes": st.st_size, "mtime": int(st.st_mtime)})
    rows.sort(key=lambda r: (-r["mtime"], r["name"]))
    with _lock:
        _media.update(at=now, rows=rows)
    return rows


# ── apps: each widget's own data dir, walked in the background (a browser profile is 100k+ files) ──────────
def _walk(path: str) -> tuple[int, int, int]:
    files = size = newest = 0
    stack = [path]
    while stack:
        d = stack.pop()
        try:
            it = list(os.scandir(d))
        except OSError as e:
            _note("walking a data dir", e)
            continue
        for e in it:
            if e.is_dir(follow_symlinks=False):
                stack.append(e.path)
            elif e.is_file(follow_symlinks=False):
                st = e.stat(follow_symlinks=False)
                files += 1; size += st.st_size; newest = max(newest, int(st.st_mtime))
    return files, size, newest


def _measure_dirs() -> None:
    try:
        root = _widgets_root()
        groups: dict[str, dict] = {}
        for e in (os.scandir(root) if os.path.isdir(root) else []):
            if not e.is_dir(follow_symlinks=False) or e.name.startswith((".", "_")) or e.name == "mensajeria":
                continue
            base = "results" if e.name.startswith("results") else e.name.split("--")[0]
            f, b, m = _walk(e.path)
            g = groups.setdefault(base, {"key": base, "files": 0, "bytes": 0, "mtime": 0, "sheets": 0})
            g["files"] += f; g["bytes"] += b; g["mtime"] = max(g["mtime"], m); g["sheets"] += 1
        for g in groups.values():
            g["title"] = _widget_title(g["key"])
            if g["key"] != "results":
                g.pop("sheets")
        rows = sorted(groups.values(), key=lambda g: -g["bytes"])
        with _lock:
            _dirs.update(at=time.monotonic(), rows=rows)
    except Exception as e:  # noqa: BLE001
        _note("measuring the app folders", e)
    finally:
        with _lock:
            _dirs["running"] = False


def _widget_title(wid: str) -> str:
    """The manifest's title — the client prefers its own translated name and falls back to this."""
    import widgets
    p = os.path.join(os.path.dirname(widgets.__file__), wid, "manifest.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as fh:
            return str(json.load(fh).get("title") or "")
    return ""


def _dir_rows() -> list[dict] | None:
    """The measured app folders, or None while the first walk is still running (it starts here)."""
    with _lock:
        fresh = _dirs["rows"] is not None and time.monotonic() - _dirs["at"] < _DIRS_TTL_S
        if not fresh and not _dirs["running"]:
            _dirs["running"] = True
            threading.Thread(target=_measure_dirs, name="memory-viewer-dirs", daemon=True).start()
        return _dirs["rows"]


# ── stats ───────────────────────────────────────────────────────────────────────────────────────────────────
def _contacts_and_agenda() -> dict:
    from widgets import store
    c = store.load("contactos", {}) if store.exists("contactos") else {}
    a = store.load("agenda", {}) if store.exists("agenda") else {}
    return {"contacts": len(c.get("contacts") or []), "meetings": len(a.get("meetings") or []),
            "todo": len(a.get("tasks") or []) + len(a.get("recurring") or [])}


def _growth(days: int = 30) -> list[dict]:
    from connectors.messaging import archive
    out: dict[str, dict] = {}
    for r in memapi.viewer.per_day(days):
        out.setdefault(r["day"], {"day": r["day"], "memories": 0, "messages": 0})["memories"] = r["own"]
    for r in archive.per_day(days):
        out.setdefault(r["day"], {"day": r["day"], "memories": 0, "messages": 0})["messages"] = r["messages"]
    return [out[k] for k in sorted(out)]


def _stats() -> dict:
    from connectors.messaging import archive
    mem = memapi.viewer.counts()
    msgs = archive.totals()
    tables = _table_counts()
    media = _media_rows()
    week = time.time() - 7 * 86400
    eps = memapi.list_episodes()
    ca = _contacts_and_agenda()
    dirs = _dir_rows()
    rules = tables["rules"] or len((memapi.state() or {}).get("rules") or [])
    stores = [
        {"key": "facts", "total": mem["facts"], "week": mem["facts_week"],
         "parts": {"concepts": mem["concepts"], "relations": mem["relations"], "short": mem["facts_short"]}},
        {"key": "conversation", "total": mem["conversation"], "since": mem["conversation_oldest"]},
        {"key": "messages", "total": msgs["total"], "bytes": msgs["bytes"], "week": msgs["week"],
         "parts": msgs["by_platform"]},
        {"key": "files", "total": len(media) + len(eps),
         "bytes": sum(r["bytes"] for r in media) + sum(int(e.get("bytes") or 0) for e in eps),
         "week": sum(1 for r in media if r["mtime"] >= week),
         "parts": {"images": sum(1 for r in media if r["kind"] in ("img", "tg")),
                   "videos": sum(1 for r in media if r["kind"] == "vid"),
                   "audio": sum(1 for r in media if r["kind"] == "aud"),
                   "documents": sum(1 for r in media if r["kind"] in ("doc", "eml", "up")) + len(eps)}},
        {"key": "contacts", "total": ca["contacts"]},
        {"key": "agenda", "total": ca["meetings"] + ca["todo"] + tables["tasks"],
         "parts": {"meetings": ca["meetings"], "todo": ca["todo"], "errands": tables["tasks"]}},
        {"key": "apps", "total": None if dirs is None else sum(g["bytes"] for g in dirs), "unit": "bytes",
         "pending": dirs is None,
         "parts": {} if dirs is None else {g["key"]: g["bytes"] for g in dirs[:2]},
         "sheets": 0 if dirs is None else next((g.get("sheets", 0) for g in dirs if g["key"] == "results"), 0)},
        {"key": "rules", "total": rules},
        {"key": "phrases", "total": tables["phrases"], "parts": {"paraphrases": tables["paraphrases"]}},
        {"key": "events", "total": tables["events"], "week": tables["events_week"]},
        {"key": "vault", "total": tables["vault"]},
    ]
    return {"stores": stores, "growth": _growth(30), "counted_at": int(time.time())}


@router.get("/api/memory/viewer/stats")
async def viewer_stats():
    """Every store, totalled. Cached a few seconds: the overview and a live refresh share one count."""
    now = time.monotonic()
    body = _stats_cache["body"]
    stale = body is None or now - _stats_cache["at"] >= _STATS_TTL_S
    if stale or (_apps_pending(body) and _dirs["rows"] is not None):
        body = await asyncio.to_thread(_stats)
        _stats_cache.update(at=now, body=body)
    return JSONResponse(body, headers={"Cache-Control": "no-cache"})


def _apps_pending(body: dict | None) -> bool:
    return bool(body) and any(s.get("pending") for s in body.get("stores") or [])


# ── memory: graph, concept page, timeline, facts, conversation ─────────────────────────────────────────────
@router.get("/api/memory/viewer/graph")
async def viewer_graph(days: int = 30, layers: str = "short,long", lanes: str = "own", budget: int = 300):
    body = await asyncio.to_thread(memapi.viewer.graph, days=days, layers=layers, lanes=lanes, budget=budget)
    body["layer_counts"] = await asyncio.to_thread(memapi.viewer.layer_counts, days=days)
    return JSONResponse(body, headers={"Cache-Control": "no-cache"})


@router.get("/api/memory/viewer/concept")
async def viewer_concept(key: str, days: int = 30, layers: str = "short,long", lanes: str = "own",
                         before_id: int = 0, limit: int = 20):
    return await asyncio.to_thread(memapi.viewer.concept, key, days=days, layers=layers, lanes=lanes,
                                   before_id=before_id, limit=limit)


@router.get("/api/memory/viewer/timeline")
async def viewer_timeline(days: int = 30):
    return {"days": await asyncio.to_thread(memapi.viewer.per_day, days)}


@router.get("/api/memory/viewer/facts")
async def viewer_facts(layer: str = "all", q: str = "", before_id: int = 0, limit: int = 50):
    return await asyncio.to_thread(memapi.viewer.facts, layer=layer, q=q, before_id=before_id, limit=limit)


@router.get("/api/memory/viewer/conversation")
async def viewer_conversation(q: str = "", before_id: int = 0, limit: int = 50):
    return await asyncio.to_thread(memapi.viewer.conversation, q=q, before_id=before_id, limit=limit)


# ── messages, files, apps, system ──────────────────────────────────────────────────────────────────────────
@router.get("/api/memory/viewer/messages")
async def viewer_messages(platform: str = "", q: str = "", before_ts: float = 0, before_id: int = 0,
                          limit: int = 50):
    from connectors.messaging import archive
    return await asyncio.to_thread(archive.page, platform=platform or None, q=q or None,
                                   before_ts=before_ts if before_id else None, before_id=before_id or None,
                                   limit=limit)


@router.get("/api/memory/viewer/files")
async def viewer_files(offset: int = 0, limit: int = FILES_CAP, kind: str = ""):
    rows = await asyncio.to_thread(_media_rows)
    groups = {"img": ("img", "tg"), "vid": ("vid",), "aud": ("aud",), "doc": ("doc", "eml", "up")}
    if kind in groups:
        rows = [r for r in rows if r["kind"] in groups[kind]]
    n = _clamp(limit, FILES_CAP, FILES_CAP)
    off = max(0, int(offset or 0))
    page = rows[off:off + n]
    return {"items": [dict(r, thumb=_is_image(r["name"])) for r in page],
            "more": off + n < len(rows), "next": off + n, "total": len(rows)}


def _thumb(name: str) -> str | None:
    """A cached thumbnail of one image (generated once). None when it cannot be made."""
    safe = "".join(c for c in os.path.basename(name or "") if c.isalnum() or c in "._-")
    if not safe.startswith(_MEDIA_PREFIXES) or not _is_image(safe):
        return None
    src = os.path.join(_widgets_root(), "mensajeria", safe)
    if not os.path.isfile(src):
        return None
    from widgets import store
    out = os.path.join(store.data_dir("_system"), "thumbs", safe.rsplit(".", 1)[0] + ".webp")
    if os.path.exists(out) and os.path.getmtime(out) >= os.path.getmtime(src):
        return out
    try:
        from PIL import Image
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with Image.open(src) as im:
            im.thumbnail((_THUMB_PX, _THUMB_PX))
            im.convert("RGB").save(out, "WEBP", quality=72)
        return out
    except Exception as e:  # noqa: BLE001
        _note("making a thumbnail", e)
        return None


@router.get("/api/memory/viewer/thumb/{name}")
async def viewer_thumb(name: str):
    p = await asyncio.to_thread(_thumb, name)
    if not p:
        return JSONResponse({"error": "no thumbnail"}, status_code=404)
    return FileResponse(p, media_type="image/webp", headers={"Cache-Control": "max-age=86400"})


@router.get("/api/memory/viewer/apps")
async def viewer_apps(offset: int = 0, limit: int = 50):
    rows = _dir_rows()
    if rows is None:
        return {"items": [], "more": False, "next": 0, "pending": True}
    n = _clamp(limit, LIST_CAP, 50)
    off = max(0, int(offset or 0))
    return {"items": rows[off:off + n], "more": off + n < len(rows), "next": off + n, "pending": False}


def _events(before_id: int, limit: int) -> dict:
    from bus import log as buslog
    n = _clamp(limit, LIST_CAP, 50)
    path = str(buslog.db_path())
    if not os.path.exists(path):
        return {"items": [], "more": False, "next": 0}
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
    try:
        # Only the rows that carry a human line: a topic name or a payload is the engine's, not his.
        sql = "SELECT id, ts_ms, topic, cat, kind, label FROM events WHERE label IS NOT NULL AND label != ''"
        args: tuple = ()
        if before_id:
            sql += " AND id < ?"; args = (int(before_id),)
        rows = conn.execute(sql + " ORDER BY id DESC LIMIT ?", (*args, n + 1)).fetchall()
    finally:
        conn.close()
    items = [{"id": r[0], "ts": int((r[1] or 0) / 1000), "topic": r[2], "cat": r[3] or "", "kind": r[4] or "",
              "label": (r[5] or "")[:200]} for r in rows[:n]]
    return {"items": items, "more": len(rows) > n, "next": items[-1]["id"] if items else 0}


@router.get("/api/memory/viewer/system")
async def viewer_system(before_id: int = 0, limit: int = 50):
    return await asyncio.to_thread(_events, before_id, limit)
