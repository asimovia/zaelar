"""«Sal de pantalla completa» has an obvious object, and the model could not see it (V2-609).

Measured live, session `4a492268`, 2026-09-07:

    18:54:02  OPERADOR  Ponme el video a pantalla completa.      → fullscreen_widget → maximize ✓
    18:54:27  OPERADOR  Sal de pantalla completa.
    18:54:29  ZAELAR    Hecho.                                   ← NO tool call at all
    18:54:36  OPERADOR  Quita la pantalla completa del vídeo.    → fullscreen_widget → exits ✓

The operator's reading is the correct one: one card was at full screen and practically nothing else was
open, so the target was not ambiguous — it was *obvious*. Three things were true at once and only the
third is a real defect:

  * `maximize()` IS a proper toggle, so the second phrasing left full screen correctly. Not the bug.
  * `attention.mentions_fullscreen` correctly stopped the close-backstop from closing the whole widget
    (V2-600). Not the bug.
  * `fullscreen_widget` REQUIRED `widget_id`, described as «the widget to ENLARGE», and the sentence names
    no widget. With nothing legal to pass — inventing an id is forbidden (V2-026) — the model called
    nothing and confabulated success. The engine's own friction detector logged «data-op fantasma» in the
    same second and was in cooldown, so nobody was told.

The fix is the V2-540/V2-603 lesson once more: the canvas KNEW which card was at full screen and never said
so. A verb whose object the system can see and the model cannot is a verb the model declines to use.
"""
import re
from pathlib import Path

import pytest

from memory import api as memory
from nucleo.acts import show_target
from widgets import brief

FRONTEND = Path(__file__).resolve().parents[4] / "frontend"


@pytest.fixture
def canvas(monkeypatch):
    """A canvas state we control: `state()` is the seam both channels and the prompt already read."""
    st = {"open_widgets": ["youtube", "agenda"], "recent_widgets": [], "maximized_widget": ""}
    monkeypatch.setattr(memory, "state", lambda: dict(st))
    return st


# ── the target resolves without a name ────────────────────────────────────────────────────────────────────

# ── the tool the model is offered ─────────────────────────────────────────────────────────────────────────

# ── the fact the model was never told ─────────────────────────────────────────────────────────────────────

def test_the_prompt_says_which_card_is_at_full_screen(canvas):
    canvas["maximized_widget"] = "youtube"
    out = brief.for_prompt(["youtube", "agenda"])
    row = next((l for l in out.split("\n") if l.startswith("- youtube ")), "")
    assert "PANTALLA COMPLETA ahora" in row, "el canvas lo sabe y el prompt no lo dice"
    assert "fullscreen_widget" in row, "decir el hecho sin nombrar la salida deja al modelo adivinando"


def test_the_prompt_says_nothing_when_nothing_is_at_full_screen(canvas):
    canvas["maximized_widget"] = ""
    assert "PANTALLA COMPLETA ahora" not in brief.for_prompt(["youtube", "agenda"])


def test_the_mark_lands_on_the_maximized_card_and_not_on_its_neighbour(canvas):
    canvas["maximized_widget"] = "agenda"
    out = brief.for_prompt(["youtube", "agenda"])
    assert "PANTALLA COMPLETA ahora" in next(l for l in out.split("\n") if l.startswith("- agenda "))
    assert "PANTALLA COMPLETA ahora" not in next(l for l in out.split("\n") if l.startswith("- youtube "))


# ── the canvas reports it, and the server keeps it ────────────────────────────────────────────────────────

def test_the_canvas_reports_which_card_is_maximized():
    """`_restore` is the maximize marker and it already rode nowhere. The report that travels on every
    `_persist()` carried `min` and not `max` — the one piece of canvas state the server could not see."""
    src = (FRONTEND / "app" / "widgets" / "desktop.js").read_text(encoding="utf-8")
    layout = src[src.index("_layout(){"):src.index("_persist(){")]
    layout = "\n".join(re.sub(r"//.*$", "", ln) for ln in layout.split("\n"))
    # either the maximize marker alone or with the browser's own full screen (4.561): `max:(r || …)?1:0`
    assert re.search(r"max\s*:\s*\(?\s*r\b[^?]*\?", layout), "el canvas no informa de cuál está a pantalla completa"


def test_the_server_stores_the_maximized_card_from_the_canvas_report(monkeypatch):
    from server import voice_api
    written = {}
    monkeypatch.setattr(memory, "set_state", lambda d: written.update(d))
    monkeypatch.setattr(memory, "state", lambda: {"open_widgets": []})
    monkeypatch.setattr(memory, "note_widgets_used", lambda *a, **k: None)
    monkeypatch.setattr(memory, "kv_set", lambda *a, **k: None)
    import asyncio
    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(voice_api.canvas_state({
        "open": ["youtube", "agenda"],
        "layout": [{"id": "agenda", "max": 0}, {"id": "youtube::t2", "max": 1}],
    }))
    assert written.get("maximized_widget") == "youtube", "la instancia se normaliza a su id base, como el resto"
    assert written.get("open_widgets") == ["youtube", "agenda"]


def test_nothing_maximized_is_reported_as_nothing(monkeypatch):
    from server import voice_api
    written = {}
    monkeypatch.setattr(memory, "set_state", lambda d: written.update(d))
    monkeypatch.setattr(memory, "state", lambda: {"open_widgets": []})
    monkeypatch.setattr(memory, "note_widgets_used", lambda *a, **k: None)
    monkeypatch.setattr(memory, "kv_set", lambda *a, **k: None)
    import asyncio
    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(voice_api.canvas_state({
        "open": ["youtube"], "layout": [{"id": "youtube", "max": 0}]}))
    assert written.get("maximized_widget") == ""


# ── one decision, one door ────────────────────────────────────────────────────────────────────────────────
