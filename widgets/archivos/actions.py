"""Archivos' action handlers — one function per action (or per family sharing one body), dispatched by
`data.ACTIONS`.

Every handler opens with `_begin` (load, seed the torrents section, bring the Biblioteca to the front for a library
verb). Shared helpers are read through `data`, so a test that patches one there (`_svc`) is honoured here.
"""
from __future__ import annotations

from . import data as _d
from . import torrents as _tor
from .cloud import _handle_cloud_nav, _relist_cloud, _sync_status
from .local import _handle_local_nav, _handle_local_write, _relist_local
from .save import _save_document


def _begin(act: str) -> dict:
    db = _d._load()
    _tor.state(db)                 # the torrents section is seeded on every action, as the torrent dispatch did
    # Any library verb brings the Biblioteca back in front: «abre la carpeta de vídeo» while looking at the
    # torrents means the library.
    if act in _d._LIBRARY_VERBS:
        db["section"] = "biblioteca"
    return db


def _torrent(act: str, payload: dict) -> dict:
    # V2-764 — the Torrents section (and the section switch itself) live in `torrents.py`.
    db = _d._load()
    res = _tor.handle(db, act, payload)
    if res is None:
        return _d._unknown(act)
    _d._save(db)
    return res


def _a_sync_providers(act: str, payload: dict) -> dict:
    # Refresh of the header's provider chips, so they show before the connect wizard is ever opened. The card asks
    # once when stale; `view_data` never touches the network (as `youtube`'s `sync_platforms`, V2-597).
    db = _begin(act)
    svc = _d._svc()
    if svc is None:
        return {"ok": True, "providers": []}
    db = _sync_status(db, svc)
    _d._save(db)
    return {"ok": True, "providers": db["providers"]}


def _a_set_view(act: str, payload: dict) -> dict:
    db = _begin(act)
    mode = _d._text(payload.get("mode"), 12).lower()
    if mode not in _d._MODES:
        return _d._err(f"vista desconocida: «{mode}». Usa list o grid")
    db["mode"] = mode
    _d._save(db)
    return {"ok": True, "mode": mode}


def _a_set_provider(act: str, payload: dict) -> dict:
    db = _begin(act)
    want = _d._text(payload.get("provider"), 40).lower() or "local"
    db.pop("preferred_provider", None)               # an explicit choice replaces any remembered one
    if want == "local":
        db["provider"] = "local"
        db = _relist_local(db, "")
        _d._save(db)
        return {"ok": True, "provider": "local", "count": len(db["entries"])}
    svc = _d._svc()
    if svc is None:
        return _d._err("el conector de archivos no está disponible en esta instalación")
    db = _sync_status(db, svc)
    connected = [p["id"] for p in (db.get("providers") or []) if p.get("connected")]
    if want not in connected:
        return _d._err(f"«{want}» no está conectado. Conectados ahora mismo: "
                       f"{', '.join(connected) or 'ninguno'}")
    db["provider"] = want
    db = _relist_cloud(db, svc, "")
    _d._save(db)
    return {"ok": True, "provider": want, "count": len(db["entries"])}


def _local_write(act: str, payload: dict) -> dict:
    db = _begin(act)
    provider = db.get("provider") or "local"
    if provider != "local":
        return _d._err(f"«{provider}» no permite modificar archivos desde aquí — solo se puede navegar, "
                       f"buscar y abrir")
    return _handle_local_write(db, act, payload)


def _a_save_document(act: str, payload: dict) -> dict:
    # A TEXT becomes a file ON A SHELF, whatever the provider on screen: the library is the one place a file the
    # operator asks for lands (V2-661).
    return _save_document(_begin(act), payload)


def _named_entry(db: dict, act: str, payload: dict) -> dict:
    """The row he NAMED on the list on screen — its number in the digest, its name or words of it — turned into the
    id the open takes (V2-861: the video and music cards pick a result this way; here «abre el tercero» or «abre el
    contrato» reached `open_file` with no id to open). An id already on the list, or a reference that names no single
    row of the right kind, is left as it came: the open answers it as before."""
    key = "folderId" if act == "open_folder" else "fileId"
    ref = payload.get(key) or payload.get("id") or payload.get("item")
    entries = db.get("entries") or []
    if ref is None or not entries or any(str(e.get("id")) == str(ref) for e in entries):
        return payload
    from widgets import result_refs as _rr
    i = _rr.resolve([{"title": str(e.get("name") or ""), "channel": ""} for e in entries], ref)
    if i is None or (str(entries[i].get("kind")) == "folder") != (act == "open_folder"):
        return payload
    return {**payload, key: str(entries[i].get("id") or "")}


def _nav(act: str, payload: dict) -> dict:
    db = _begin(act)
    if act in ("open_file", "open_folder"):
        payload = _named_entry(db, act, payload or {})
    pref = db.get("preferred_provider") or db.get("provider") or "local"   # his choice, even while it is unreachable
    if pref == "local":
        return _handle_local_nav(db, act, payload)
    svc = _d._svc()
    if svc is not None:
        db = _sync_status(db, svc)
        if db.get("connected"):
            db["provider"] = pref
            db.pop("preferred_provider", None)        # his choice is reachable again: it is what the card shows
            return _handle_cloud_nav(db, svc, act, payload)
    db["provider"] = pref
    # The saved cloud provider is a PREFERENCE, never a gate: with no connector (or nothing connected) the library is
    # the next option, and the reply says so instead of stopping.
    return _fall_back_to_local(db, act, payload)


def _fall_back_to_local(db: dict, act: str, payload: dict) -> dict:
    was = str(db.get("provider") or "")
    db["provider"] = "local"
    # A cloud folder id means nothing on the library's shelves: land at the library's root instead of refusing.
    if act == "open_folder" and not _is_local_folder(payload):
        act = "go_home"
    elif act in ("refresh", "clear_search", "go_up"):
        db["folder_id"] = ""
    # The card SHOWS the library, and his choice stays the cloud drive: the next move tries it again first.
    db["preferred_provider"] = was
    res = _handle_local_nav(db, act, payload)
    if isinstance(res, dict):
        res["provider"] = "local"
        res["fallback_from"] = was
        res["note"] = _note(was)
    return res


def _is_local_folder(payload: dict) -> bool:
    from library import paths as _paths
    fid = str((payload or {}).get("folderId") or (payload or {}).get("id") or "").strip()
    kind = fid.split(":", 1)[1] if fid.startswith("shelf:") else fid
    return kind in _paths.KINDS


def _note(provider: str) -> str:
    """Said beside a result served from the library because his cloud drive could not be reached (`voice` pack)."""
    from i18n import langs as _lg
    line = _lg.words("apps.files_cloud_fallback", default="") or _lg.words("apps.files_cloud_fallback", code="en",
                                                                          default="")
    return str(line or "").replace("{provider}", provider or "?")
