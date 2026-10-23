#
# media.py — how long the media this widget downloaded stays on this device.
#
# Every connector lands what it downloads (WhatsApp photos, videos and voice notes, Telegram media, mail
# attachments) flat in this widget's data dir, so the asset route can serve it. Kept forever, that is gigabytes
# of copies of files that are still on the phone and in the provider. So media is kept KEEP days (default 14,
# the operator's choice in Ajustes, «Siempre» = 0) and then deleted from this device; the message keeps its text,
# its media TYPE and a `mediaGone` mark, so the conversation still says «📷 Foto» where the picture was.
# Scrollback fetched from the past never downloads media in the first place (connectors/whatsapp/backfill.py,
# `_history_entry` in each connector): only its type travels.
#
# Same widget-package contract as data.py: stdlib plus the `widgets` package.
#
import logging
import os
import time

_log = logging.getLogger("zaelar.mensajeria.media")

DEFAULT_DAYS = 14
CHOICES = (7, 14, 30, 90, 0)          # 0 = keep forever
SWEEP_EVERY_S = 3600
#: The files connectors write here — and nothing else in the dir (state.json, the archive, …) is ever touched.
PREFIXES = ("img_", "vid_", "aud_", "doc_", "tg_", "eml_", "up_")


def days(db: dict) -> int:
    try:
        d = int(db.get("media_days", DEFAULT_DAYS))
    except (TypeError, ValueError):
        _log.warning("media window unreadable, using the default")
        return DEFAULT_DAYS
    return d if d in CHOICES else DEFAULT_DAYS


def set_days(db: dict, value) -> int | None:
    """Store the operator's choice; None when it is not one of CHOICES."""
    try:
        d = int(value)
    except (TypeError, ValueError):
        _log.info(f"media window: {value!r} is not a number of days")
        return None
    if d not in CHOICES:
        return None
    db["media_days"] = d
    db.pop("media_swept_at", None)        # a shorter window applies on the next beat, not in an hour
    return d


def due(db: dict, now: float | None = None) -> bool:
    try:
        return (now or time.time()) - float(db.get("media_swept_at") or 0) >= SWEEP_EVERY_S
    except (TypeError, ValueError):
        _log.warning("media sweep time unreadable, sweeping now")
        return True


def _strip(msg: dict, gone: set, folder: str) -> bool:
    media = msg.get("media")
    if not isinstance(media, list) or not media:
        return False
    keep = [m for m in media if isinstance(m, dict) and m.get("name") not in gone
            and os.path.isfile(os.path.join(folder, str(m.get("name") or "")))]
    if len(keep) == len(media):
        return False
    if keep:
        msg["media"] = keep
    else:
        msg.pop("media", None)
    msg["mediaGone"] = True
    return True


def sweep(db: dict, folder: str, now: float | None = None) -> dict:
    """Delete downloaded media older than the window and unhook it from the messages that showed it. Returns
    {files, bytes, messages}. With «Siempre» nothing is deleted, but references to files already missing are
    still unhooked (a broken picture is worse than a label)."""
    now = now or time.time()
    keep_days = days(db)
    gone: set = set()
    freed = 0
    if keep_days:
        cutoff = now - keep_days * 86400
        try:
            names = os.listdir(folder)
        except OSError as e:
            _log.warning(f"media sweep: cannot list the media folder: {e}")
            names = []
        for name in names:
            if not name.startswith(PREFIXES):
                continue
            path = os.path.join(folder, name)
            try:
                st = os.stat(path)
                if st.st_mtime < cutoff and os.path.isfile(path):
                    os.remove(path)
                    gone.add(name)
                    freed += st.st_size
            except OSError as e:
                _log.warning(f"media sweep: {name} not removed: {e}")
                continue
    touched = 0
    for it in db.get("items") or []:
        if isinstance(it, dict) and _strip(it, gone, folder):
            touched += 1
    for th in (db.get("threads") or {}).values():
        for m in (th or {}).get("msgs") or [] if isinstance(th, dict) else []:
            if isinstance(m, dict) and _strip(m, gone, folder):
                touched += 1
    db["media_swept_at"] = now
    return {"files": len(gone), "bytes": freed, "messages": touched}


def local_paths(folder: str, names) -> list[str]:
    """The files named in an action, as paths inside this widget's data dir — and ONLY there: a name is reduced
    to its basename and must be a connector download or an upload (PREFIXES) that exists. Anything else is
    dropped, so an action can never point a send at a file elsewhere on the machine."""
    out = []
    for n in names or []:
        base = os.path.basename(str(n or "")).strip()
        path = os.path.join(folder, base)
        if base and base.startswith(PREFIXES) and os.path.isfile(path) and path not in out:
            out.append(path)
    return out
