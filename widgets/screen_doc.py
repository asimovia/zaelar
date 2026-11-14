"""widgets/screen_doc.py — ONE document per screen: what its host says it shows now (V2-907 §3.1).

A screen (`dev`: one browser or app install; a MOUNT of it speaks) reports one small document of HOST facts only —
which layout it is, which app is in front, every app mounted with its layer and visibility, what its own resting
screen holds and which native panel is open. An app's inside stays in its own store (`widgets/state.py`, V2-884) and is
joined at render time by `(app, instance, dev)`.

  · THE WRITER (`write`) — called by the screen's report door alone (a structural test keeps it so). `n` only goes
    forward within a mount; a new mount's report replaces the old mount, which never speaks again; the server assigns
    `v` (it moves when the stored content differs). A malformed document is refused whole, never stored half.
  · THE READER (`read`, `open_ids`, `front`, `vis`, `screens_of`) — validity is judged when READING: a document counts
    only while its screen is open (`voice.screens.is_open`). No document is UNKNOWN (`None`), never an empty screen:
    every caller must tell «nothing is open» from «I don't know». A host still bringing its saved apps back (a reload's
    restore) reports `{layout, unknown: true}`: its new mount is registered and its screen reads UNKNOWN until the
    restore settles, never as the empty screen it shows for that instant.
  · `closed` — the apps a report took off the screen, each with when and who, kept `CLOSED_S`.

Process memory: a restart empties it and every screen is unknown until its mount's first report.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field, replace

from loguru import logger

LAYOUTS = ("windows", "deck")
#: front (focused, on top, in view) · visible (in view, not front: windows) · behind (covered) · min → rank in view
VIS = {"front": 0, "visible": 1, "behind": 2, "min": 3}
CLOSED_S = 60.0
#: A bound on what one screen may report (a crowd of windows is cut, never stored whole).
MAX_OPEN = 24
MAX_HOLDS = 8
_ID_MAX = 80


@dataclass(frozen=True)
class Doc:
    dev: str
    layout: str
    mount: str
    n: int
    v: int
    at: float
    front: str = ""
    home: dict = field(default_factory=dict)
    panel: str = ""
    open: tuple = ()
    closed: tuple = ()
    unknown: bool = False


_LOCK = threading.Lock()
_DOCS: dict[str, Doc] = {}
#: dev → the mounts a newer one replaced: they never write again (a reload, a second tab)
_GONE: dict[str, list] = {}


def _clean_id(v) -> str:
    return str(v or "").strip()[:_ID_MAX]


def _shape(doc) -> tuple[dict | None, str]:
    """The host facts of `doc`, normalised, or `(None, why)` — a document is taken whole or not at all."""
    if not isinstance(doc, dict):
        return None, "not_a_document"
    layout = doc.get("layout")
    if layout not in LAYOUTS:
        return None, "layout"
    if doc.get("unknown") is True:          # the host does not know yet what it shows (its restore is running)
        return {"layout": layout, "front": "", "home": {}, "panel": "", "open": (), "unknown": True}, ""
    rows = doc.get("open")
    if not isinstance(rows, list) or len(rows) > MAX_OPEN:
        return None, "open"
    open_, seen = [], set()
    for i, r in enumerate(rows):
        if not isinstance(r, dict):
            return None, "open"
        cid, vis = _clean_id(r.get("id")), r.get("vis")
        layer = r.get("layer", i)
        if not cid or cid in seen or vis not in VIS or not isinstance(layer, int) or isinstance(layer, bool):
            return None, "open"
        seen.add(cid)
        row = {"id": cid, "layer": layer, "vis": vis}
        row.update({k: True for k in ("max", "fs") if r.get(k) is True})
        open_.append(row)
    open_.sort(key=lambda r: r["layer"])
    fronts = [r["id"] for r in open_ if r["vis"] == "front"]
    if len(fronts) > 1:
        return None, "two_fronts"
    said = doc.get("front")
    if said not in (None, "") and fronts != [_clean_id(said)]:
        return None, "front"
    if layout == "deck" and any(r["vis"] == "visible" for r in open_):
        return None, "visible_on_deck"      # a deck shows one app at a time: the rest are behind
    home = doc.get("home") if isinstance(doc.get("home"), dict) else {}
    holds = home.get("holds") if isinstance(home.get("holds"), list) else []
    return {"layout": layout, "front": fronts[0] if fronts else "",
            "home": {"shown": home.get("shown") is True,
                     "holds": [h for h in (_clean_id(x) for x in holds[:MAX_HOLDS]) if h]},
            "panel": _clean_id(doc.get("panel")), "open": tuple(open_), "unknown": False}, ""


def write(dev, mount, n, doc, *, by: str = "") -> tuple[bool, str]:
    """Store screen `dev`'s report. `(stored, why)`: `why` is "" when stored, else the reason it was refused
    (`n_back`, `replaced`, `names`, or what was malformed)."""
    from voice import screens
    dev, mount = screens.clean(dev), str(mount or "")[:40]
    if not dev or not mount or not isinstance(n, int) or isinstance(n, bool):
        return False, "names"
    facts, why = _shape(doc)
    if facts is None:
        return False, why
    now = time.time()
    with _LOCK:
        cur = _DOCS.get(dev)
        if mount in _GONE.get(dev, ()):
            return False, "replaced"
        if cur and cur.mount == mount and n <= cur.n:
            return False, "n_back"
        if cur and cur.mount != mount:
            _GONE[dev] = (_GONE.get(dev, []) + [cur.mount])[-8:]
        before = {r["id"] for r in cur.open} if cur else set()
        after = {r["id"] for r in facts["open"]}
        closed = [c for c in (cur.closed if cur else ()) if now - c["at"] < CLOSED_S and c["id"] not in after]
        if not facts["unknown"]:             # an unknown report closes nothing: it does not say what left
            closed += [{"id": cid, "at": now, "by": str(by or "")[:20]} for cid in sorted(before - after)]
        same = bool(cur) and all(getattr(cur, k) == v for k, v in facts.items())
        v = (cur.v if cur else 0) + (0 if same else 1)
        _DOCS[dev] = Doc(dev=dev, mount=mount, n=n, v=v, at=now, closed=tuple(closed), **facts)
    if not same:
        logger.debug(f"screen_doc: {dev} v{v} front={facts['front'] or '-'} open={len(facts['open'])}")
    return True, ""


def version(dev) -> int:
    """The stored `v` of screen `dev` (0 = never reported), valid or not — the report door's change detector, never a
    reader of what is on screen (that is `read`)."""
    from voice import screens
    with _LOCK:
        d = _DOCS.get(screens.clean(dev))
    return d.v if d else 0


def _valid(d: Doc | None) -> Doc | None:
    from voice import screens
    if d is None or d.unknown or not screens.is_open(d.dev):
        return None
    now = time.time()
    closed = tuple(c for c in d.closed if now - c["at"] < CLOSED_S)
    return d if closed == d.closed else replace(d, closed=closed)


def read(dev=None) -> Doc | None:
    """The document of screen `dev` (`None` → the screen of the turn, else the voice holder). `None` = UNKNOWN: never
    reported, or the screen is no longer open — never read it as an empty screen."""
    from voice import screens
    d = screens.clean(dev) if dev else (screens.current() or screens.holder())
    if not d:
        return None
    with _LOCK:
        doc = _DOCS.get(d)
    return _valid(doc)


def open_ids(dev=None) -> list[str] | None:
    """Every app mounted on the screen, top layer first; `None` = unknown, `[]` = nothing open."""
    d = read(dev)
    return None if d is None else [r["id"] for r in d.open]


def front(dev=None) -> str | None:
    """The app in front; `""` = the home (deck) or the bare desk (windows); `None` = unknown."""
    d = read(dev)
    return None if d is None else d.front


def vis(cid, dev=None) -> str | None:
    """`front` · `visible` · `behind` · `min` for an app on the screen, `""` when it is not open; `None` = unknown."""
    d = read(dev)
    if d is None:
        return None
    cid = _clean_id(cid)
    return next((r["vis"] for r in d.open if r["id"] == cid), "")


def screens_of(cid) -> list[str]:
    """The open screens whose document lists `cid`."""
    cid = _clean_id(cid)
    with _LOCK:
        docs = list(_DOCS.values())
    return [d.dev for d in docs if (v := _valid(d)) and any(r["id"] == cid for r in v.open)]


def _base(cid) -> str:
    return str(cid or "").split("::", 1)[0].strip().lower()


def drift(dev, legacy: dict) -> list[dict]:
    """Where the LEGACY canvas state (`memory.state()`: `open_widgets`, `maximized_widget`, `minimized_widgets`,
    `front_reported`) differs from screen `dev`'s document, in the legacy store's own terms (base ids): one row
    `{what, legacy, doc}` per fact that differs — `open`, `front` (a deck's app in front), `max` (a desk's maximised
    card — `max` only: the legacy store never knew the browser's own full screen, `fs`), `min` (a desk's minimised
    cards; a deck's cards behind). `[]` when they agree or the document is unknown
    (no document is not a drift: there is nothing to compare). Shadow (V2-907 T10): a measure, read by no decision."""
    d = read(dev)
    if d is None or not isinstance(legacy, dict):
        return []
    rows: list[dict] = []

    def _cmp(what: str, old, new) -> None:
        if old != new:
            rows.append({"what": what, "legacy": old, "doc": new})

    _cmp("open", sorted({_base(w) for w in legacy.get("open_widgets") or [] if _base(w)}),
         sorted({_base(r["id"]) for r in d.open}))
    if d.layout == "deck":
        _cmp("front", _base(legacy.get("maximized_widget")) if legacy.get("front_reported") else None, _base(d.front))
        _cmp("min", sorted({_base(w) for w in legacy.get("minimized_widgets") or []}),
             sorted({_base(r["id"]) for r in d.open if r["vis"] != "front"} - {_base(d.front)}))
    else:
        _cmp("max", _base(legacy.get("maximized_widget")),
             next((_base(r["id"]) for r in d.open if r.get("max")), ""))   # the browser's full screen is no legacy fact
        _cmp("min", sorted({_base(w) for w in legacy.get("minimized_widgets") or []}),
             sorted({_base(r["id"]) for r in d.open if r["vis"] == "min"}))
    return rows


def _reset_for_tests() -> None:
    with _LOCK:
        _DOCS.clear()
        _GONE.clear()
