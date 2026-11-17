"""nucleo/self/snapshot.py — what is true about the agent NOW, one reader per truth (V2-932).

The catalogue (`catalog.json` + the `self` language pack) says what the agent IS and how each thing is done; this says
what holds this second: its name, when it listens, the face it wears, its voice, the accounts connected, the clusters,
the screens open and which of them has the camera on, the desktop app, where it runs and its build. Each field has ONE
reader, the same the rest of the engine reads, so the agent cannot describe itself differently from how it behaves.

Read only when asked (`about_self`, `fields`) — nothing here is paid by an idle turn. The two lines the live tail
carries (`live_lines`) exist only while they are true: a camera on, a face on a screen that is open.

The camera is a FLAG the screen sends with its beat (`voice/screens.beat(camera=)`, from `presence/look-state.js`): a
boolean per device, kept in process memory — never an image, never a box, never a number about a face.
"""
from __future__ import annotations

import json
import platform
import socket
import sys
from pathlib import Path

from loguru import logger

ENGINE = Path(__file__).resolve().parents[2]
DEFAULT_FACE = "c-porcelain"     # `frontend/app/presence/state.js::DEFAULT_FACE`: what {} in the settings means


def _state() -> dict:
    from memory import api as memory
    return memory.state() or {}


def name() -> str:
    from genome import persona
    return str(_state().get("assistant_name") or "").strip() or persona.default_name()


def wake_mode() -> str:
    from config import settings
    return str(settings.get("attention_mode") or "always")


def presence() -> dict:
    from config import settings
    p = settings.presence()
    return {"face": str(p.get("face") or DEFAULT_FACE), "on": p.get("on") is not False}


def face_name(fid: str) -> str:
    """The face's name in his language, as the picker writes it (`presence/catalog-api.js::faceName`)."""
    from i18n import runtime
    fid = str(fid or DEFAULT_FACE)
    if fid == "mine":
        return runtime.text("presence.mine_name", fid)
    if fid.startswith("c-"):
        return runtime.text(f"presence.face.{fid[2:]}", fid[2:])
    base, _, n = fid.rpartition("-")
    label = runtime.text(f"presence.face.{base or fid}", base or fid)
    return f"{label} {int(n) + 1}" if n.isdigit() and int(n) else label


def voice() -> str:
    from config import settings
    return str(settings.get("assistant_voice") or "")


def language() -> str:
    from i18n import langs
    spec = langs.current_language()
    return f"{spec.native} ({spec.code})"


def widgets() -> list[str]:
    from nucleo.flash import widget_read
    from widgets import runtime
    return [widget_read.title(str(w.get("id"))) for w in runtime.catalog() if w.get("id")]


def _descriptors() -> list[dict]:
    from connectors import registry
    return registry.descriptors()


def connectors() -> dict:
    """Connected accounts, and the ones that could be connected (built, not connected), by their labels."""
    rows = [d for d in _descriptors() if d.get("id") != "meshkore"]
    return {"connected": [d["label"] for d in rows if d.get("connected")],
            "not_connected": [d["label"] for d in rows if not d.get("connected")]}


def clusters() -> list[dict]:
    mesh = next((d for d in _descriptors() if d.get("id") == "meshkore"), {})
    return [{"name": c.get("name"), "connected": bool(c.get("connected"))} for c in mesh.get("clusters") or []]


def screens() -> list[dict]:
    """The screens open now, each named by the word he uses for it (`screens.on_*`, the chips' own words)."""
    from i18n import runtime
    from voice import screens as _screens
    return [{"screen": runtime.text(f"screens.on_{e.get('surface') or 'other'}", e.get("surface") or "other"),
             "voice": bool(e.get("holds_voice")), "visible": bool(e.get("visible")), "camera": bool(e.get("camera"))}
            for e in _screens.open_screens()]


def camera() -> list[str]:
    """The screens whose camera is running now («look at me»), by the word he uses for them."""
    return [s["screen"] for s in screens() if s["camera"]]


def hosted() -> bool:
    from nucleo.energy import account
    return account.is_cloud_account()


def host() -> dict:
    if hosted():
        return {"kind": "hosted"}
    return {"kind": "self-hosted", "computer": socket.gethostname(), "os": f"{platform.system()} {platform.release()}"}


def daemon() -> dict:
    """The desktop app: on a hosted engine, whether its tunnel reaches him; at home, whether it was ever installed here."""
    if hosted():
        from nucleo.daemon_egress import link
        s = link.status()
        return {"linked": bool(s.get("capable") or s.get("enabled")), "tunnel": bool(s.get("connected"))}
    from nucleo import workspace
    return {"installed": (Path(workspace.root()) / "config" / "daemon" / "daemon.json").is_file()}


def build() -> str:
    try:
        return (ENGINE / "update" / "BUILD").read_text(encoding="utf-8").strip()
    except OSError as e:
        logger.warning(f"self snapshot: update/BUILD unreadable ({e!r})")
        return ""


def face() -> str:
    return face_name(presence()["face"])


def face_on() -> bool:
    return presence()["on"]


def fields(names) -> dict:
    """The named live facts. A field is the reader of the same name in this module, and only a field the catalogue
    declares (`catalog.json` `needs`) is read. A reader that fails is ABSENT, never guessed: the answer pass says what
    it does not know."""
    from nucleo.self import about
    declared = about.declared_needs()
    out = {}
    for n in names or ():
        fn = getattr(sys.modules[__name__], str(n), None) if n in declared else None
        if not callable(fn):
            continue
        try:
            out[n] = fn()
        except Exception as e:  # noqa: BLE001 — one broken reader never costs the others
            logger.debug(f"self.snapshot: {n} unread ({e!r})")
    return out


def render(facts: dict) -> str:
    return json.dumps(facts, ensure_ascii=False, default=str)


def live_lines() -> list[str]:
    """The live tail's two self lines, only while true: the camera running on a screen, the face worn on an open one.
    A turn with neither reads nothing else (no pack, no settings file)."""
    out = []
    try:
        open_ = screens()
        cams = [s["screen"] for s in open_ if s["camera"]]
        worn = bool(open_) and face_on()
        if not (cams or worn):
            return out
        from nucleo.self import about
        words = about.words().get("live") or {}
        if cams and words.get("camera"):
            out.append(str(words["camera"]).format(screen=", ".join(cams)))
        if worn and words.get("face"):
            out.append(str(words["face"]).format(face=face()))
    except Exception as e:  # noqa: BLE001 — the tail never fails for a convenience
        logger.debug(f"self.snapshot: live lines unread ({e!r})")
    return out
