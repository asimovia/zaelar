"""Fotos — a Google-Photos-style gallery fed by the Picker (V2-564).

The operator asked for a photo gallery «like Google Photos, browse by year, and ask by voice for last year's
Morocco trip photos». Google shut off third-party read access to a user's EXISTING library in March 2025 —
the old `photoslibrary.readonly` scope now answers every call with a 403 — so there is no "browse the whole
library" here: the operator picks a batch through Google's own Picker UI, and everything this widget shows
comes from OUR OWN local index of what has been picked (`connectors/photos/store.py`), never a live call to
Google. Apple Photos and Amazon Photos have no equivalent (no public API / no official API at all) and are
catalog-only entries, not connectors.

## Why the network never happens in `view_data`

Same split as `archivos` (V2-557): `view_data` serves the CACHE (the widget's own `state.json`, refreshed by
`apply_action` or by `tick`), never touches the connector directly, and stays stdlib-only itself. The
connector import is deferred and lives on the hand-reviewed `_STDLIB_EXEMPT` list next to `archivos`/`musica`
— somebody's Google account sits behind an OAuth token, and there is no stdlib equivalent of that.

## Background — deliberately narrow (V2-034 asks every widget this)

`tick()` runs every 20s but does real work ONLY while a Picker session is pending: it polls Google once, and
the moment the session resolves (imported or expired) there is nothing left to poll — the widget does not
have standing access to a library it could otherwise watch. A gallery with nothing pending costs nothing per
tick beyond a local-file check.

## Voice search — the honest v1 scope, stated so nobody assumes more

`search` matches a date range (parsed by `connectors.photos.service`, PAST-oriented — `nucleo/pulse/scheduler.py`'s
parser is FUTURE-only, built for reminders) and a trip label the operator gave a batch, or a filename. It does
NOT recognize what is IN a photo — no "this is Morocco" from pixels. The manifest's `usage` says so, so the
FlashBrain never claims a capability this widget does not have (V2-547's "an undeclared capability is invented
anyway" lesson, applied here in the opposite direction: a capability that IS declared but doesn't exist gets
narrated as real).
"""
from __future__ import annotations

import time

from .. import store
import logging

from i18n import langs as _langs   # V2-778 F3-30: hints are read back aloud, in the agent's language

logger = logging.getLogger("zaelar.widgets.fotos")

WIDGET_ID = "fotos"
DB_VERSION = 1
PAGE_SIZE = 120


def _seed() -> dict:
    return {
        "connected": False, "app_configured": False, "session_pending": False,
        "years": [], "items": [], "cursor": 0, "has_more": False, "total": 0,
        "active_filter": {}, "error": "", "reason": "", "updated": 0,
    }


def _load() -> dict:
    return store.load(WIDGET_ID, _seed(), version=DB_VERSION)


def _save(db: dict) -> dict:
    db["updated"] = int(time.time())
    store.save(WIDGET_ID, db)
    return db


def _svc():
    """The connector, imported here and not at module top — see the module docstring. Returns None if the
    connector package cannot be loaded, which callers report as a plain error instead of raising."""
    try:
        from connectors.photos import service
        return service
    except Exception:
        return None


def _text(raw, cap: int = 200) -> str:
    return " ".join(str(raw or "").split())[:cap]


def _err(msg: str, **extra) -> dict:
    out = {"ok": False, "error": _text(msg, 300)}
    out.update(extra)
    return out


def _sync_status(db: dict, svc) -> dict:
    st = svc.status()
    db["connected"] = bool(st.get("connected"))
    db["app_configured"] = bool(st.get("app_configured"))
    db["session_pending"] = bool(st.get("session_pending"))
    return db


def _load_page(db: dict, svc, offset: int = 0) -> dict:
    res = svc.list_page(offset, PAGE_SIZE)
    db["items"] = res.get("items") or []
    db["cursor"] = res.get("next_offset") or 0
    db["has_more"] = bool(res.get("has_more"))
    db["total"] = int(res.get("total") or 0)
    db["years"] = svc.years()
    db["active_filter"] = {}
    return db


# ── read ───────────────────────────────────────────────────────────────────────────────────────────────────
def view_data(q: str = ""):
    """The cached view. CHEAP by contract: no network, no credential store, no import of the connector."""
    db = _load()
    return {
        "connected": bool(db.get("connected")),
        "app_configured": bool(db.get("app_configured")),
        "session_pending": bool(db.get("session_pending")),
        "years": db.get("years") or [],
        "items": db.get("items") or [],
        "cursor": int(db.get("cursor") or 0),
        "has_more": bool(db.get("has_more")),
        "total": int(db.get("total") or 0),
        "active_filter": db.get("active_filter") or {},
        # The query on screen as a VALUE ("" when no search is applied): the `search` end state reads it, and a key
        # the view omitted would read «unverifiable», never unmet.
        "query": str((db.get("active_filter") or {}).get("query") or ""),
        "error": db.get("error") or "",
        "reason": db.get("reason") or "",
        "updated": int(db.get("updated") or 0),
    }


#: How many of a search's photos the brain reads by number.
DIGEST_FOUND = 12


def ref_index() -> list[dict]:
    """Photo ids currently on screen — the model NEVER invents a photo id (V2-026 precedent)."""
    out = []
    for it in (_load().get("items") or [])[:200]:
        iid = str(it.get("id") or "")
        if iid:
            out.append({"id": iid, "label": it.get("filename") or iid, "field": "id", "hint": _langs.words("hints.photo", default="")})
    return out


def prompt_digest() -> str:
    db = _load()
    if not db.get("connected"):
        return "FOTOS: Google Photos no está conectado todavía."
    total = int(db.get("total") or 0)
    if not total:
        return "FOTOS: sin ninguna foto importada todavía (usa pick para elegir una tanda)."
    years = db.get("years") or []
    by_year = ", ".join(f"{y['year']}: {y['count']}" for y in years[:6])
    head = f"FOTOS: {total} importadas — {by_year}"
    q = str((db.get("active_filter") or {}).get("query") or "").strip()
    items = db.get("items") or []
    if not q:
        return head
    # V2-861 — what a search FOUND, numbered as he says them («the third one», «the one from Marrakech»): the brain
    # answers «which ones?» from here instead of searching again.
    rows = [f"  {n}. {str(it.get('filename') or '')[:60]}" + (f" — {str(it.get('taken_at'))[:10]}" if it.get("taken_at") else "")
            for n, it in enumerate(items[:DIGEST_FOUND], 1)]
    more = len(items) - len(rows)
    return "\n".join([head, f"BÚSQUEDA EN PANTALLA («{q[:60]}», {len(items)} fotos):"] + rows
                      + ([f"  (y {more} más)"] if more > 0 else []))


# ── write ──────────────────────────────────────────────────────────────────────────────────────────────────
def apply_action(action: str, payload: dict | None = None):
    payload = payload or {}
    act = str(action or "").strip()
    svc = _svc()
    if svc is None:
        if act == "search":
            # The connector is a PREFERENCE for reading, never a gate: what was already imported is ours, so a search
            # still answers from the local index (or, failing that, from what the card already holds).
            return _search_offline(payload)
        return _err("el conector de fotos no está disponible en esta instalación")
    db = _load()
    db = _sync_status(db, svc)

    if act == "refresh":
        if db.get("session_pending"):
            res = svc.poll_session()
            if res.get("ready"):
                db["session_pending"] = False
                db = _load_page(db, svc, 0)
                _save(db)
                return {"ok": True, "imported": res.get("imported", 0), "total": db["total"]}
            if not res.get("pending"):
                db["session_pending"] = False
        db = _load_page(db, svc, 0)
        _save(db)
        return {"ok": True, "total": db["total"], "pending": db.get("session_pending")}

    if act == "pick":
        res = svc.start_session()
        if not res.get("ok"):
            out = _err(res.get("error") or "no pude abrir el selector de Google Photos",
                       needs_app=bool(res.get("needs_app")), needs_connect=bool(res.get("needs_connect")))
            if out["needs_app"] or out["needs_connect"]:
                # Not a dead stop: the connect path stays, and the reply OFFERS what works without Google.
                out["alternatives"] = [dict(a) for a in _PICK_ALTERNATIVES]
                out["message"] = _offer_text()
            return out
        db["session_pending"] = True
        _save(db)
        # `url` travels back so the CARD can open the picker window (widget.js never touches the network).
        return {"ok": True, "url": res.get("picker_uri")}

    if act == "more":
        if not db.get("has_more"):
            return _err("no hay más fotos que cargar")
        res = svc.list_page(int(db.get("cursor") or 0), PAGE_SIZE)
        db["items"] = (db.get("items") or []) + (res.get("items") or [])
        db["cursor"] = res.get("next_offset") or db["cursor"]
        db["has_more"] = bool(res.get("has_more"))
        db["total"] = int(res.get("total") or db.get("total") or 0)
        _save(db)
        return {"ok": True, "count": len(db["items"]), "has_more": db["has_more"]}

    if act == "search":
        q = _text(payload.get("query") or payload.get("q"), 200)
        if not q:
            return _err("dime qué fotos busco: una fecha, un viaje, o los dos")
        res = svc.search(q)
        db["items"] = res.get("items") or []
        db["has_more"] = False
        db["cursor"] = 0
        db["active_filter"] = {"date_from": res.get("date_from"), "date_to": res.get("date_to"),
                                "label": res.get("label"), "query": q}
        _save(db)
        # The matches TRAVEL BACK (V2-541): "do I have Morocco photos?" is a question.
        return {"ok": True, "query": q, "count": res.get("count", 0),
                "matches": (res.get("items") or [])[:20]}

    if act == "clear_search":
        db = _load_page(db, svc, 0)
        _save(db)
        return {"ok": True, "total": db["total"]}

    if act == "label_batch":
        label = _text(payload.get("label"), 120)
        if not label:
            return _err("dime qué nombre le pongo a la última tanda importada")
        res = svc.label_last_batch(label)
        if not res.get("ok"):
            return _err(res.get("error") or "no pude etiquetar la última tanda")
        return {"ok": True, "label": label}

    return _err(f"acción desconocida: «{act}». Las que hay: refresh, pick, more, search, clear_search, "
                f"label_batch")


# ── without the connector / without a connection ──────────────────────────────────────────────────────────
#: What the operator can use instead of Google's picker: images saved on this machine, and the files card. Each is a
#: real action of another card (or the connect panel's tool), so the reply can offer it by name instead of stopping.
_PICK_ALTERNATIVES = (
    {"tool": "show_panel", "args": {"panel": "conectores", "connector": "google-photos"}},
    {"widget": "imagenes", "action": "local", "payload": {}},
    {"widget": "archivos", "action": "open_folder", "payload": {"folderId": "images"}},
)

def _offer_text() -> str:
    """The offer when Google Photos is not connected — the `voice` pack's `apps.photos_offer`, English floor."""
    try:
        return _langs.words("apps.photos_offer", default="") or _langs.words("apps.photos_offer", code="en", default="")
    except Exception as e:  # noqa: BLE001 — no pack: the offer keeps its alternatives, without words
        logger.debug(f"fotos: offer line unreadable: {e!r}")
        return ""


def _search_offline(payload: dict) -> dict:
    """`search` with the connector package unavailable: the local index first, then the card's own cached items.
    Filename / batch-label matching only (the date parser lives in the connector)."""
    q = _text(payload.get("query") or payload.get("q"), 200)
    if not q:
        return _err("dime qué fotos busco: una fecha, un viaje, o los dos")
    db = _load()
    try:
        from connectors.photos import store as _pstore
        hits = [{"id": str(it.get("id") or ""), "filename": it.get("filename") or "",
                 "taken_at": it.get("taken_at") or "", "provider": it.get("provider") or "", "thumb": ""}
                for it in _pstore.filter_items("", "", q)[:60]]
    except Exception:  # noqa: BLE001 — not even the local index: what the card already shows
        needle = q.lower()
        hits = [it for it in (db.get("items") or []) if needle in str(it.get("filename") or "").lower()][:60]
    db["items"] = hits
    db["has_more"] = False
    db["cursor"] = 0
    db["active_filter"] = {"date_from": "", "date_to": "", "label": q, "query": q}
    _save(db)
    return {"ok": True, "query": q, "count": len(hits), "matches": hits[:20], "source": "local"}


# ── background (V2-034) ───────────────────────────────────────────────────────────────────────────────────
def tick(ctx) -> None:
    """Only does real work while a picker session is PENDING — see the module docstring. Imports the
    connector lazily (background runs off-thread, but this file stays stdlib-only at import time)."""
    db = _load()
    if not db.get("session_pending"):
        return
    svc = _svc()
    if svc is None:
        return
    res = svc.poll_session()
    if res.get("ready"):
        db["session_pending"] = False
        db = _load_page(db, svc, 0)
        _save(db)
    elif not res.get("pending"):
        db["session_pending"] = False
        _save(db)
