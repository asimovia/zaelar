"""voice/screens.py — one agent, one voice, many screens (V2-792).

The operator opens the same agent on the desktop and on the phone at once. It is ONE agent and ONE conversation,
so the chat, the transcript and the progress of every errand belong on every screen. What must NOT be everywhere is
what a request does to a screen: a video asked for on the desktop opened, and played, on the phone as well, because
every SSE event reached every surface and nothing said which one had asked.

This module is the server's knowledge of the screens, and the one place that answers «which screen is this for?»:

  · THE REGISTRY — which surfaces are open (`attach`/`detach` from the event stream), whether each is visible, when
    it was last touched, and which one holds the voice (written by `server/livekit_api.py`, the lock's owner).
    Process memory only: a restart forgets it and every surface re-registers on its next connect.
  · THE ORIGIN — every event of a turn is stamped `origin_dev`, the surface that asked. A typed turn carries the
    device that typed it; a spoken turn comes from the voice holder; a background errand inherits the origin of the
    turn that commissioned it (`note_task`), so a report finishing two minutes later opens where it was asked for,
    not on whichever screen moved last. The frontend decides what to do with the stamp (`event-scope.js`); this
    module only says where things came from.
  · THE TYPED DOOR — a surface without the voice has no LiveKit room, so the data channel that carries a typed line
    does not exist for it. The live session registers how to receive a typed turn (`register_typed`), and
    `POST /api/chat` delivers through it, so either screen can type into the one conversation.

The device id is the frontend's `api.js::DEVICE`: `<desktop|mobile>:<id>`, stable per browser.
"""
from __future__ import annotations

import contextvars
import os
import threading
import time
from collections import OrderedDict

from loguru import logger

#: The voice lock's own TTL (`server/livekit_api.py`): a holder that has not beaten in this long holds nothing.
HOLDER_TTL_S = float(os.getenv("ZAELAR_SESSION_TTL", "12"))
#: A surface whose stream dropped stays «open» this long. A phone on the metro loses its stream for seconds at a
#: time, and a registry that forgot it on every gap would re-route its results to the other screen mid-errand.
GONE_AFTER_S = float(os.getenv("ZAELAR_SCREEN_GONE_S", "90"))
#: Every kind carries an origin except the two that fire many times a second. The frontend scopes `widget` and
#: `panel`; the rest are stamped for the audit («what did the agent do, and from which screen was it asked?»).
_UNSTAMPED = ("interim", "pulse")

_mx = threading.Lock()
_screens: dict[str, dict] = {}
_holder = {"dev": "", "ts": 0.0}
_last = {"dev": ""}
_traces: "OrderedDict[str, str]" = OrderedDict()
_tasks: "OrderedDict[str, str]" = OrderedDict()
_CAP = 256

#: The origin of the turn running in THIS context. Set by the typed door around the injection, so the reply task the
#: session spawns inherits it (asyncio copies the context at task creation). A spoken turn never sets it: it falls
#: through to the trace map or the last turn.
ORIGIN: contextvars.ContextVar[str] = contextvars.ContextVar("zaelar_screen_origin", default="")

#: True while the running turn was SENT to another screen («ponlo en el ordenador»): its `show` is a move.
ROUTED: contextvars.ContextVar[bool] = contextvars.ContextVar("zaelar_screen_routed", default=False)

_typed = {"fn": None}

#: Where each one-screen card plays right now (`youtube` → its screen) and how to tell which cards are one-screen.
#: The policy is the WIDGET's (`widgets/screen_policy.py`); this module only asks, through a registered predicate,
#: so the voice layer imports nothing from the widgets.
_playing: dict[str, str] = {}
_policy = {"single": None}


def register_policy(fn) -> None:
    """`fn(card_id) -> bool`: True when the card takes the device's sound or picture (`"screens": "single"`)."""
    _policy["single"] = fn


def _is_single(card_id: str) -> bool:
    fn = _policy["single"]
    try:
        return bool(fn and fn(card_id))
    except Exception as e:  # noqa: BLE001
        logger.debug(f"screens: policy unreadable for {card_id}: {e!r}")
        return False


def note_playing(card_id, dev) -> str:
    """A card now lives on `dev` (opened there by hand, or moved there). Returns where it lived before."""
    b, d = str(card_id or "").split("::", 1)[0].strip().lower(), clean(dev)
    if not (b and d):
        return ""
    with _mx:
        prev = _playing.get(b, "")
        _playing[b] = d
    return prev


def _canvas_report(src) -> bool:
    from voice import canvas_src
    return canvas_src.is_report(src)


def _move_if_single(ev: dict, dev: str) -> None:
    """A `show` of a one-screen card, asked from `dev`: it MOVES here. The move is announced BEFORE the show goes
    out (this runs inside the show's own stamp), so the screen that had it stops and closes its copy before it can
    load what the new order put in the card — «ponme un vídeo» said to the phone does not start it on the desktop."""
    cid = str(ev.get("id") or "")
    if not cid or _canvas_report(ev.get("src")) or not _is_single(cid):
        return
    b = cid.split("::", 1)[0].strip().lower()
    with _mx:
        prev = _playing.get(b, "")
        _playing[b] = dev
    ev["moved"] = True
    if prev == dev:
        return
    try:
        from voice.observer import emit
        emit("screens", "moved", extra={"id": cid, "to": dev, "origin_dev": dev, "from": prev})
    except Exception as e:  # noqa: BLE001
        logger.debug(f"screens: move of {cid} not announced: {e!r}")


def clean(dev) -> str:
    """A device id as it may be stored and compared: short, lowercase, no characters a header or a log would mangle."""
    return "".join(c for c in str(dev or "").strip().lower() if c.isascii() and (c.isalnum() or c in ":_-"))[:40]


def surface(dev: str) -> str:
    """`phone` or `computer` — the word the operator uses for it. Empty for an id without a known prefix."""
    d = clean(dev)
    if d.startswith("mobile:"):
        return "phone"
    if d.startswith("desktop:"):
        return "computer"
    return ""


def _entry(dev: str, now: float) -> dict:
    e = _screens.get(dev)
    if e is None:
        e = _screens[dev] = {"dev": dev, "streams": 0, "visible": True, "seen_at": now, "input_at": 0.0,
                             "opened_at": now}
    return e


def attach(dev) -> None:
    """A surface opened its event stream."""
    d = clean(dev)
    if not d:
        return
    now = time.time()
    with _mx:
        e = _entry(d, now)
        e["streams"] += 1
        e["seen_at"] = now


def detach(dev) -> None:
    """…and closed it. The entry stays for `GONE_AFTER_S`: see that constant."""
    d = clean(dev)
    if not d:
        return
    now = time.time()
    with _mx:
        e = _screens.get(d)
        if e:
            e["streams"] = max(0, e["streams"] - 1)
            e["seen_at"] = now


def beat(dev, *, visible=None) -> None:
    """A surface says whether it is on screen. Sent on every `visibilitychange`."""
    d = clean(dev)
    if not d:
        return
    now = time.time()
    with _mx:
        e = _entry(d, now)
        e["seen_at"] = now
        if isinstance(visible, bool):
            e["visible"] = visible


def touched(dev) -> None:
    """The operator did something on this surface (typed, tapped a card, opened the mic)."""
    d = clean(dev)
    if not d:
        return
    now = time.time()
    with _mx:
        e = _entry(d, now)
        e["input_at"] = now
        e["seen_at"] = now
        e["visible"] = True


def holder_beat(dev) -> None:
    """`server/livekit_api.py` writes the lock's owner here on every acquire, beat and steal."""
    with _mx:
        _holder["dev"], _holder["ts"] = clean(dev), time.time()


def holder_released() -> None:
    with _mx:
        _holder["dev"], _holder["ts"] = "", 0.0


def holder() -> str:
    """The surface holding the voice, or "" when nobody does (or its beat has lapsed)."""
    with _mx:
        if _holder["dev"] and time.time() - _holder["ts"] <= HOLDER_TTL_S:
            return _holder["dev"]
    return ""


def _is_open(e: dict, now: float) -> bool:
    return e["streams"] > 0 or (now - e["seen_at"]) <= GONE_AFTER_S


def is_open(dev) -> bool:
    d = clean(dev)
    now = time.time()
    with _mx:
        e = _screens.get(d)
        return bool(e) and _is_open(e, now)


def open_screens() -> list[dict]:
    """The surfaces open right now, as plain dicts (a copy: the caller may keep it)."""
    now = time.time()
    hold = holder()
    with _mx:
        out = [dict(e) for e in _screens.values() if _is_open(e, now)]
        for d in [k for k, e in _screens.items() if not _is_open(e, now) and now - e["seen_at"] > 6 * GONE_AFTER_S]:
            _screens.pop(d, None)          # a surface gone for many minutes is forgotten, not kept forever
    for e in out:
        e["holds_voice"] = e["dev"] == hold
        e["surface"] = surface(e["dev"])
    out.sort(key=lambda e: e["opened_at"])
    return out


_listeners: list = []


def on_active_change(fn) -> None:
    """`fn(dev)` runs when a turn starts on a different screen than the last one (the canvas adopts that screen's)."""
    if fn not in _listeners:
        _listeners.append(fn)


def begin_turn(dev, trace: str = "") -> None:
    """A turn started from this surface. The last one wins for events that carry nothing better (see `origin_of`)."""
    d = clean(dev)
    if not d:
        return
    with _mx:
        moved = _last["dev"] != d
        _last["dev"] = d
        if trace:
            _traces[str(trace)] = d
            _traces.move_to_end(str(trace))
            while len(_traces) > _CAP:
                _traces.popitem(last=False)
    if moved:
        for fn in list(_listeners):
            try:
                fn(d)
            except Exception as e:  # noqa: BLE001 — a listener never stops the turn from starting
                logger.debug(f"screens: active-change listener failed: {e!r}")


def note_task(task_id, dev) -> None:
    """A background errand was commissioned from this surface: whatever it opens later goes back there."""
    d = clean(dev)
    if not d or not task_id:
        return
    with _mx:
        _tasks[str(task_id)] = d
        _tasks.move_to_end(str(task_id))
        while len(_tasks) > _CAP:
            _tasks.popitem(last=False)


def task_origin(task_id) -> str:
    with _mx:
        return _tasks.get(str(task_id or ""), "")


def current() -> str:
    """The origin of the turn running now: this context's typed turn, else the last turn that began, else the voice."""
    return ORIGIN.get() or _last["dev"] or holder()


def origin_of(ev: dict) -> str:
    """Where an event belongs. The most specific evidence wins: what the event already says, the errand it comes
    from, the turn it belongs to (by trace), this context's typed turn, the last turn, the voice holder."""
    o = clean(ev.get("origin_dev"))
    if o:
        return o
    src = str(ev.get("src") or "")
    if src.startswith("worker:"):
        o = task_origin(src.split(":", 1)[1])
        if o:
            return o
    tr = str(ev.get("trace") or "")
    if tr:
        with _mx:
            o = _traces.get(tr, "")
        if o:
            return o
    return current()


def stamp(ev: dict) -> dict:
    """Called on every event at the stream's single gate (`voice/observer.stamp_identity`). Cheap: dict reads."""
    try:
        kind = ev.get("kind")
        if kind in _UNSTAMPED:
            return ev
        if kind == "transcript" and ev.get("role") == "user":
            # A spoken final comes from the voice holder; a typed one names its device (the typed door).
            begin_turn(ev.get("dev") or ORIGIN.get() or holder(), str(ev.get("trace") or ""))
        o = origin_of(ev)
        if o:
            ev["origin_dev"] = o
        if kind == "widget" and ev.get("label") == "show":
            if ROUTED.get():
                ev["moved"] = True        # the screen that opens it takes it from the others (`/api/screens/bring`)
            if o:
                _move_if_single(ev, o)
    except Exception as e:  # noqa: BLE001 — a stamp never breaks the stream
        logger.debug(f"screens: stamp failed: {e!r}")
    return ev


def resolve(word: str, *, asking: str = "") -> str:
    """The device a screen word points at: `computer`, `phone` or `here` (the values `show_widget(screen=…)` declares).
    Empty when nothing open matches — the caller then keeps the default (the asking screen)."""
    w = str(word or "").strip().lower()
    if w == "here":
        return clean(asking) or current()
    cands = [e for e in open_screens() if w and e["surface"] == w]
    if not cands:
        return ""
    cands.sort(key=lambda e: (e["input_at"], e["seen_at"]), reverse=True)
    return cands[0]["dev"]


def send_turn_to(word: str) -> str:
    """The operator asked for this turn's result on ANOTHER screen («ponlo en el ordenador», «tráelo aquí»). What the
    turn opens from here on goes there, and opening it there takes it from the screen that had it. Returns the device,
    or "" when no open screen answers to that word (the turn then opens where it was asked, as always)."""
    dev = resolve(word, asking=current())
    if not dev:
        return ""
    ORIGIN.set(dev)
    ROUTED.set(True)
    try:
        from voice import trace as _trace
        tr = _trace.current()
    except Exception:  # noqa: BLE001
        tr = ""
    if tr:
        with _mx:
            _traces[str(tr)] = dev
    return dev


def slot_line() -> str:
    """The turn context's view of the screens — ONLY with two or more open, so the common case costs nothing.
    A slot, not prose: `phone (voice, active) · computer (open, idle 40 min)`."""
    scr = open_screens()
    if len(scr) < 2:
        return ""
    now = time.time()
    act = current()
    parts = []
    for e in scr:
        tags = []
        if e["holds_voice"]:
            tags.append("voice")
        if e["dev"] == act:
            tags.append("active")
        if not e["visible"]:
            tags.append("hidden")
        idle = now - max(e["input_at"], e["opened_at"])
        if e["dev"] != act and idle > 120:
            tags.append(f"idle {int(idle // 60)} min")
        parts.append(f"{e['surface'] or e['dev']} ({', '.join(tags) or 'open'})")
    return "screens: " + " · ".join(parts) + " — one conversation; show_widget(screen=…) opens a card on another one."


# ── the typed door ──────────────────────────────────────────────────────────────────────────────────────────────

def register_typed(fn) -> None:
    """The live voice session registers how to receive a typed turn: `async fn(text, dev) -> None`."""
    _typed["fn"] = fn


def clear_typed(fn=None) -> None:
    if fn is None or _typed["fn"] is fn:
        _typed["fn"] = None


def has_session() -> bool:
    return _typed["fn"] is not None


async def deliver_typed(text: str, dev) -> bool:
    """Hand a typed line to the live session. False when there is none — the caller then brings one up."""
    fn = _typed["fn"]
    t = str(text or "").strip()
    if fn is None or not t:
        return False   # not a failure: nobody holds a session, and the caller brings one up
    touched(dev)
    await fn(t, clean(dev))
    return True


def _reset_for_tests() -> None:
    with _mx:
        _screens.clear()
        _playing.clear()
        _traces.clear()
        _tasks.clear()
        _holder["dev"], _holder["ts"] = "", 0.0
        _last["dev"] = ""
    _typed["fn"] = None
